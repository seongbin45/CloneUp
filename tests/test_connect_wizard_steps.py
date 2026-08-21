"""Connect wizard step list stays in sync with the guided PAT path."""

from __future__ import annotations


def test_connect_wizard_has_seven_classic_steps() -> None:
    from app.ui.login_dialog import _STEPS, _STEP_PASTE

    assert len(_STEPS) == 7
    assert _STEP_PASTE == 6
    titles = [t for t, _b in _STEPS]
    assert titles[0] == "시작"
    assert titles[-1] == "붙여넣기"
    assert "브라우저" in titles[1]
    assert "repo" in _STEPS[3][1]
