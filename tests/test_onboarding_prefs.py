"""Onboarding preference flags (QSettings)."""

from __future__ import annotations

from app.ui.settings_store import (
    load_onboarding_done,
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
