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
