"""UM machine_status ACL must allow Users to write status runs."""

from __future__ import annotations

from pathlib import Path

from update_manager.acl_win import acl_grant_args
from update_manager.paths import UM_VBS_NAME, manager_task_tr


def test_machine_status_grants_users_modify() -> None:
    grants = acl_grant_args("machine_status")
    assert any(g.startswith("BUILTIN\\Users:") and g.endswith("M") for g in grants)
    assert not any(g.startswith("BUILTIN\\Users:") and g.endswith("R") for g in grants)


def test_machine_pending_still_excludes_users_write() -> None:
    grants = acl_grant_args("machine")
    assert not any(g.startswith("BUILTIN\\Users:") for g in grants)
    assert any("SYSTEM" in g for g in grants)


def test_user_mode_includes_username(monkeypatch) -> None:
    monkeypatch.setenv("USERNAME", "TestUser")
    grants = acl_grant_args("user")
    assert any(g.startswith("TestUser:") for g in grants)


def test_manager_task_tr_prefers_hidden_vbs(
    monkeypatch, tmp_path: Path
) -> None:
    um_dir = tmp_path / "UpdateManager"
    um_dir.mkdir()
    (um_dir / "CloneUp_update_manager.exe").write_bytes(b"MZ")
    (um_dir / UM_VBS_NAME).write_text("' hidden\n", encoding="utf-8")
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    # manager_install_dir looks under PROGRAMDATA\CloneUp\UpdateManager
    clone = tmp_path / "CloneUp" / "UpdateManager"
    clone.mkdir(parents=True)
    (clone / "CloneUp_update_manager.exe").write_bytes(b"MZ")
    (clone / UM_VBS_NAME).write_text("' hidden\n", encoding="utf-8")
    tr = manager_task_tr()
    assert "wscript" in tr.lower()
    assert UM_VBS_NAME in tr
    assert "//B" in tr
