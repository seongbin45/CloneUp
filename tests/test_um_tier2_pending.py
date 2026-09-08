"""Tier 2: pending lock, status per-run, sticky root, prune, Parallel identity."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest


@pytest.fixture()
def um_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    lad = tmp_path / "lad"
    pd = tmp_path / "pd"
    lad.mkdir()
    pd.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(lad))
    monkeypatch.setenv("PROGRAMDATA", str(pd))
    monkeypatch.delenv("CLONEUP_UM_PENDING_DIR", raising=False)
    # Fake machine-mode install so pending/status land under ProgramData.
    mgr = pd / "CloneUp" / "UpdateManager"
    mgr.mkdir(parents=True)
    (mgr / "CloneUp_update_manager.exe").write_bytes(b"MZ")
    return {"lad": lad, "pd": pd, "mgr": mgr}


def test_pending_root_sticky(um_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from update_manager import paths as paths_mod

    root1 = paths_mod.pending_root()
    assert "pending" in str(root1).lower()
    sticky = um_env["mgr"] / "pending_root_choice.txt"
    assert sticky.is_file()
    # Flip mode env would not matter — sticky wins
    root2 = paths_mod.pending_root()
    assert root2 == root1


def test_status_per_run_no_overwrite_race(um_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from update_manager import status_io

    monkeypatch.setattr(status_io, "status_root", lambda: um_env["pd"] / "CloneUp" / "UpdateManager" / "status")

    a = status_io.start_run(pid=1)
    b = status_io.start_run(pid=2)
    assert a != b
    status_io.update_run(a, phase="downloading", bytes=10)
    status_io.finish_run(b, "pending_busy")
    # A's file must still be downloading — B must not clobber it
    da = status_io.read_run(a)
    db = status_io.read_run(b)
    assert da is not None and da["phase"] == "downloading"
    assert db is not None and db["phase"] == "pending_busy"
    assert db.get("finished_at")
    # current points at latest publish (B)
    assert status_io.read_current_run_id() == b


def test_status_prune_keeps_current(um_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from update_manager import status_io

    root = um_env["pd"] / "CloneUp" / "UpdateManager" / "status"
    runs = root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(status_io, "status_root", lambda: root)
    monkeypatch.setattr(status_io, "_STATUS_KEEP", 2)
    monkeypatch.setattr(status_io, "_STATUS_MAX_AGE_SEC", 10_000)

    # Seed files with staggered mtimes (no start_run side effects).
    names = [f"run-{i}" for i in range(5)]
    for i, name in enumerate(names):
        p = runs / f"{name}.json"
        p.write_text(json.dumps({"run_id": name, "phase": "up_to_date"}), encoding="utf-8")
        os.utime(p, (time.time() - (5 - i) * 10, time.time() - (5 - i) * 10))
    current = names[-1]  # newest
    (root / "current.json").write_text(
        json.dumps({"run_id": current}), encoding="utf-8"
    )
    status_io.prune_old_runs(keep_current=current)
    left = {p.stem for p in runs.glob("*.json")}
    assert current in left
    assert len(left) <= 2


def test_pending_lock_exclusive(um_env, tmp_path: Path) -> None:
    from update_manager.lock_win import PendingLock

    lock_path = tmp_path / "download.lock"
    a = PendingLock(lock_path)
    b = PendingLock(lock_path)
    assert a.acquire() is True
    assert b.acquire() is False
    a.release()
    assert b.acquire() is True
    b.release()


def test_safe_remove_reparse_uses_rmdir(um_env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from update_manager import pending as pend_mod

    target = tmp_path / "extract"
    target.mkdir()
    calls: list[str] = []

    monkeypatch.setattr(pend_mod, "is_reparse_point", lambda _p: True)

    def fake_rmdir(p):  # noqa: ANN001
        calls.append(str(p))

    monkeypatch.setattr(pend_mod.os, "rmdir", fake_rmdir)
    # Must not call rmtree
    def boom(*_a, **_k):
        raise AssertionError("rmtree must not follow junction")

    monkeypatch.setattr(pend_mod.shutil, "rmtree", boom)
    pend_mod.safe_remove_tree(target)
    assert calls and calls[0] == str(target)


def test_zip_ok_idle_and_apply_gate(um_env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib

    from update_manager.github_release import LatestRelease
    from update_manager import pending as pend_mod

    pend = tmp_path / "0.1.99"
    pend.mkdir()
    payload = b"MZHELLO"
    digest_hex = hashlib.sha256(payload).hexdigest()
    zp = pend / "CloneUp-win64.zip"
    zp.write_bytes(payload)
    rel = LatestRelease(
        tag="v0.1.99",
        version=(0, 1, 99),
        asset_name="CloneUp-win64.zip",
        download_url="https://objects.githubusercontent.com/x",
        digest=f"sha256:{digest_hex}",
    )
    pend_mod.record_zip_verified(pend, rel, digest_hex)
    assert pend_mod.zip_ok_idle(pend, rel) is True
    assert pend_mod.verify_zip_full(pend, rel) == digest_hex

    # Corrupt → wipe + raise
    zp.write_bytes(b"BAD")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        pend_mod.verify_zip_full(pend, rel)
    assert not zp.exists()


def test_task_split_command_args() -> None:
    from update_manager.task_migrate import _split_command_args

    cmd, args = _split_command_args(
        r'"C:\ProgramData\CloneUp\UpdateManager\CloneUp_update_manager.exe"'
    )
    assert cmd.endswith("CloneUp_update_manager.exe")
    assert args == ""
    cmd2, args2 = _split_command_args(r"C:\um\CloneUp_update_manager.exe --once")
    assert args2 == "--once"
    assert "CloneUp_update_manager.exe" in cmd2


def test_health_status_readers(um_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.util import update_manager_health as umh
    from update_manager import status_io

    root = um_env["pd"] / "CloneUp" / "UpdateManager" / "status"
    monkeypatch.setattr(status_io, "status_root", lambda: root)
    monkeypatch.setattr(umh, "status_root", lambda: root)

    rid = status_io.start_run(pid=42)
    status_io.update_run(rid, phase="downloading", local="0.1.1", remote="0.1.2")
    assert umh.read_current_run_id() == rid
    data = umh.read_run_status(rid)
    assert data is not None
    assert data["phase"] == "downloading"
    assert data["pid"] == 42
