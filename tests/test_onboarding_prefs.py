"""Onboarding preference flags (QSettings)."""

from __future__ import annotations

from app.ui.settings_dialog import (
    SECRET_SCAN_OFF_PHRASE,
    phrase_matches_secret_scan_off,
)
from app.ui.settings_store import (
    clear_recent_folders,
    load_onboarding_done,
    load_recent_folders,
    load_secret_pii_scan_enabled,
    save_onboarding_done,
    save_secret_pii_scan_enabled,
    _settings,
)


def test_onboarding_done_roundtrip() -> None:
    s = _settings()
    key = "onboarding_done"
    prev = s.value(key)
    try:
        s.remove(key)
        assert load_onboarding_done() is False
        save_onboarding_done(True)
        assert load_onboarding_done() is True
        save_onboarding_done(False)
        assert load_onboarding_done() is False
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)


def test_onboarding_steps_count() -> None:
    from app.ui.onboarding_dialog import _STEPS

    assert len(_STEPS) == 5
    keys = [st.key for st in _STEPS]
    assert keys == ["folders", "commits", "cost", "undo", "safety"]


def test_clear_recent_folders() -> None:
    s = _settings()
    key = "recent_folders"
    prev = s.value(key)
    try:
        s.setValue(key, [r"C:\fake\a", r"C:\fake\b"])
        assert len(load_recent_folders()) >= 1
        clear_recent_folders()
        assert load_recent_folders() == []
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)


def test_secret_pii_scan_default_on() -> None:
    s = _settings()
    key = "secret_pii_scan_enabled"
    prev = s.value(key)
    try:
        s.remove(key)
        assert load_secret_pii_scan_enabled() is True
        save_secret_pii_scan_enabled(False)
        assert load_secret_pii_scan_enabled() is False
        save_secret_pii_scan_enabled(True)
        assert load_secret_pii_scan_enabled() is True
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)


def test_secret_scan_off_phrase_exact() -> None:
    assert phrase_matches_secret_scan_off(SECRET_SCAN_OFF_PHRASE)
    assert phrase_matches_secret_scan_off(f"  {SECRET_SCAN_OFF_PHRASE}  ")
    assert not phrase_matches_secret_scan_off("")
    assert not phrase_matches_secret_scan_off("이해했습니다")
    assert not phrase_matches_secret_scan_off(SECRET_SCAN_OFF_PHRASE + ".")
