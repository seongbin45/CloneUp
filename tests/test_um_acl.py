"""UM machine_status ACL must allow Users to write status runs."""

from __future__ import annotations

from update_manager.acl_win import acl_grant_args


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
