"""Onboarding preference flags (QSettings)."""

from __future__ import annotations

from app.ui.settings_store import (
    clear_recent_folders,
    load_onboarding_done,
    load_recent_folders,
    save_onboarding_done,
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
