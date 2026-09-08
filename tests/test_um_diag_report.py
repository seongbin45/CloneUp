"""Unit tests for update-manager health probe + diag gating (no live GitHub)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.util import um_diag_report as umr
from app.util.update_manager_health import (
    UpdateManagerHealth,
    build_diagnostic_markdown,
    issue_title,
)


def test_health_ok_when_no_problems() -> None:
    h = UpdateManagerHealth(exe_present=True, process_running=True)
    assert h.ok
    assert h.signature


def test_should_consider_skips_healthy() -> None:
    h = UpdateManagerHealth(exe_present=True, process_running=True, run_key_present=True)
    assert umr.should_consider_report(h) is False


def test_should_consider_exe_missing() -> None:
    h = UpdateManagerHealth(problems=["exe_missing"])
    assert umr.should_consider_report(h) is True


def test_should_consider_soft_run_key_only() -> None:
    h = UpdateManagerHealth(
        exe_present=True,
        process_running=True,
        problems=["run_key_missing"],
    )
    assert umr.should_consider_report(h) is False


def test_should_consider_skips_log_network_only() -> None:
    h = UpdateManagerHealth(
        exe_present=True,
        process_running=False,
        problems=["log_network"],
    )
    assert umr.should_consider_report(h) is False


def test_probe_soft_network_not_problem_when_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SSL timeout lines must not scare a user when the manager is running."""
    from app.util import update_manager_health as umh

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "update_manager.log"
    log_path.write_text(
        "2026-09-09 01:00:00,000 WARNING github latest failed: ssl timeout\n"
        "2026-09-09 01:00:01,000 INFO no usable release / network — skip\n",
        encoding="utf-8",
    )
    exe = tmp_path / "CloneUp_update_manager.exe"
    exe.write_bytes(b"MZ")

    monkeypatch.setattr(umh, "manager_exe_path", lambda: exe)
    monkeypatch.setattr(umh, "manager_log_path", lambda: log_path)
    monkeypatch.setattr(umh, "_process_running", lambda: True)
    monkeypatch.setattr(umh, "_read_run_key", lambda: str(exe))
    monkeypatch.setattr(umh, "_guess_app_install", lambda: str(tmp_path))

    h = umh.probe_update_manager(attempt_restart=False)
    assert h.ok
    assert "log_errors" not in h.problems
    assert "log_network" not in h.problems
    assert h.log_error_hits  # still visible in UI log panel


def test_probe_hard_apply_failed_is_problem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.util import update_manager_health as umh

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "update_manager.log"
    log_path.write_text(
        "2026-09-09 03:11:55,041 ERROR apply failed: boom\n",
        encoding="utf-8",
    )
    exe = tmp_path / "CloneUp_update_manager.exe"
    exe.write_bytes(b"MZ")

    monkeypatch.setattr(umh, "manager_exe_path", lambda: exe)
    monkeypatch.setattr(umh, "manager_log_path", lambda: log_path)
    monkeypatch.setattr(umh, "_process_running", lambda: True)
    monkeypatch.setattr(umh, "_read_run_key", lambda: str(exe))
    monkeypatch.setattr(umh, "_guess_app_install", lambda: str(tmp_path))

    h = umh.probe_update_manager(attempt_restart=False)
    assert not h.ok
    assert "log_errors" in h.problems


def test_probe_apply_timeout_is_soft_when_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """GitHub #1/#2: download timed out then often retries — not auto-issue spam."""
    from app.util import update_manager_health as umh
    from app.util.um_diag_report import should_consider_report

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "update_manager.log"
    log_path.write_text(
        "2026-09-09 04:05:54,259 ERROR apply failed: The read operation timed out\n"
        "2026-09-08 20:48:20,548 WARNING github latest failed: ssl timeout\n",
        encoding="utf-8",
    )
    exe = tmp_path / "CloneUp_update_manager.exe"
    exe.write_bytes(b"MZ")

    monkeypatch.setattr(umh, "manager_exe_path", lambda: exe)
    monkeypatch.setattr(umh, "manager_log_path", lambda: log_path)
    monkeypatch.setattr(umh, "_process_running", lambda: True)
    monkeypatch.setattr(umh, "_read_run_key", lambda: str(exe))
    monkeypatch.setattr(umh, "_guess_app_install", lambda: str(tmp_path))

    h = umh.probe_update_manager(attempt_restart=False)
    assert h.ok
    assert "log_errors" not in h.problems
    assert should_consider_report(h) is False


def test_probe_apply_failed_superseded_by_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.util import update_manager_health as umh

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "update_manager.log"
    log_path.write_text(
        "2026-09-03 12:19:19,696 ERROR apply failed: disk full somehow\n"
        "2026-09-03 12:32:10,259 INFO success 0.1.9 → 0.1.10\n",
        encoding="utf-8",
    )
    exe = tmp_path / "CloneUp_update_manager.exe"
    exe.write_bytes(b"MZ")

    monkeypatch.setattr(umh, "manager_exe_path", lambda: exe)
    monkeypatch.setattr(umh, "manager_log_path", lambda: log_path)
    monkeypatch.setattr(umh, "_process_running", lambda: True)
    monkeypatch.setattr(umh, "_read_run_key", lambda: str(exe))
    monkeypatch.setattr(umh, "_guess_app_install", lambda: str(tmp_path))

    h = umh.probe_update_manager(attempt_restart=False)
    assert h.ok
    assert "log_errors" not in h.problems


def test_build_markdown_contains_probe() -> None:
    h = UpdateManagerHealth(
        exe_present=False,
        exe_path=r"C:\Users\x\AppData\Local\CloneUp\UpdateManager\CloneUp_update_manager.exe",
        problems=["exe_missing"],
        log_error_hits=["install dir not found — skip"],
        extended_diag="=== Extended probe (Python) ===\nSTATUS: MISSING\n",
    )
    body = build_diagnostic_markdown(h)
    assert "exe_missing" in body
    assert "install dir not found" in body
    assert "Full PC diagnosis" in body
    assert "Extended probe" in body
    assert issue_title(h).startswith("[auto] update-manager")


def test_collect_extended_diag_mentions_layers() -> None:
    from app.util.update_manager_health import collect_extended_diag_text

    h = UpdateManagerHealth(
        exe_present=False,
        exe_path=r"C:\missing\CloneUp_update_manager.exe",
        problems=["exe_missing"],
    )
    text = collect_extended_diag_text(h)
    assert "Layer 1" in text
    assert "Layer 2" in text
    assert "exe_missing" in text


def test_process_running_hides_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """tasklist must use CREATE_NO_WINDOW so GUI CloneUp does not flash a terminal."""
    import subprocess

    from app.util import update_manager_health as umh

    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        pytest.skip("CREATE_NO_WINDOW not on this platform")

    seen: dict = {}

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(umh.subprocess, "run", fake_run)
    umh._process_running()
    flags = int(seen["kwargs"].get("creationflags") or 0)
    assert flags & subprocess.CREATE_NO_WINDOW
    assert "startupinfo" in seen["kwargs"]


def test_try_start_manager_hides_console(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import subprocess

    from app.util import update_manager_health as umh

    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        pytest.skip("CREATE_NO_WINDOW not on this platform")

    exe = tmp_path / "CloneUp_update_manager.exe"
    exe.write_bytes(b"MZ")
    seen: dict = {}

    def fake_popen(cmd, **kwargs):  # noqa: ANN001
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(umh.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(umh.sys, "platform", "win32")
    assert umh.try_start_manager(exe, once=True) is True
    assert seen["cmd"][-1] == "--once"
    flags = int(seen["kwargs"].get("creationflags") or 0)
    assert flags & subprocess.CREATE_NO_WINDOW
    assert "startupinfo" in seen["kwargs"]


def test_run_cycle_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(umr, "load_um_diag_report_enabled", lambda: False)
    r = umr.run_um_diag_cycle(attempt_restart=False)
    assert r.status == "skipped_disabled"


def test_run_cycle_healthy_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(umr, "load_um_diag_report_enabled", lambda: True)
    healthy = UpdateManagerHealth(
        exe_present=True,
        process_running=True,
        run_key_present=True,
    )
    monkeypatch.setattr(umr, "probe_update_manager", lambda **_k: healthy)
    r = umr.run_um_diag_cycle(attempt_restart=False)
    assert r.status == "skipped_ok"


def test_run_cycle_saves_local_without_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(umr, "load_um_diag_report_enabled", lambda: True)
    monkeypatch.setattr(umr, "load_um_diag_last_signature", lambda: None)
    monkeypatch.setattr(umr, "load_um_diag_last_sent_epoch", lambda: 0)
    monkeypatch.setattr(umr, "load_token", lambda: "")
    bad = UpdateManagerHealth(
        exe_present=False,
        problems=["exe_missing"],
        exe_path=str(tmp_path / "missing.exe"),
    )
    monkeypatch.setattr(umr, "probe_update_manager", lambda **_k: bad)
    pending = tmp_path / "um_diag_pending.md"
    monkeypatch.setattr(umr, "pending_diag_path", lambda: pending)

    r = umr.run_um_diag_cycle(attempt_restart=False)
    assert r.status == "saved_local"
    assert pending.is_file()
    assert "exe_missing" in pending.read_text(encoding="utf-8")
    assert "github.com/seongbin45/CloneUp/issues/new" in r.issue_url


def test_run_cycle_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    monkeypatch.setattr(umr, "load_um_diag_report_enabled", lambda: True)
    bad = UpdateManagerHealth(problems=["exe_missing", "process_not_running"])
    monkeypatch.setattr(umr, "probe_update_manager", lambda **_k: bad)
    monkeypatch.setattr(umr, "load_um_diag_last_signature", lambda: bad.signature)
    now = time.time()
    monkeypatch.setattr(umr, "load_um_diag_last_sent_epoch", lambda: int(now))
    r = umr.run_um_diag_cycle(attempt_restart=False)
    assert r.status == "skipped_rate"
