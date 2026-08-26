"""Settings master-protection helpers (no full GUI exec)."""

from __future__ import annotations

from app.ui.settings_dialog import (
    _MASTER_PW_MIN_LEN,
    _master_pw_ok,
)


def test_master_pw_min_len_constant() -> None:
    assert _MASTER_PW_MIN_LEN >= 8


def test_master_pw_ok() -> None:
    assert not _master_pw_ok("")
    assert not _master_pw_ok("   ")
    assert not _master_pw_ok("short")
    assert not _master_pw_ok("1234567")
    assert _master_pw_ok("12345678")
    assert _master_pw_ok("CloneUp-Master-1")
