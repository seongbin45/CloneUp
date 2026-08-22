"""Connect wizard step list stays in sync with the guided PAT path."""

from __future__ import annotations


def test_connect_wizard_step_order() -> None:
    from app.ui.login_dialog import (
        _STEP_PASTE,
        _STEP_REPO,
        _STEP_SIGNIN,
        _STEPS,
    )

    assert len(_STEPS) == 8
    assert _STEP_SIGNIN == 2
    assert _STEP_REPO == 4
    assert _STEP_PASTE == 7
    titles = [t for t, _b in _STEPS]
    assert titles[0] == "시작"
    assert "브라우저" in titles[1]
    assert "로그인" in titles[2]
    assert titles[-1] == "붙여넣기"
    assert "repo" in _STEPS[_STEP_REPO][1]
    # New vs returning accounts both mentioned before classic key fields
    signin_body = _STEPS[_STEP_SIGNIN][1]
    assert "처음" in signin_body
    assert "이미" in signin_body
    assert "패스키" in signin_body or "암호" in signin_body


def test_looks_like_github_token() -> None:
    from app.ui.login_dialog import _looks_like_github_token

    assert _looks_like_github_token("ghp_" + "a" * 36)
    assert _looks_like_github_token("github_pat_" + "x" * 40)
    assert not _looks_like_github_token("short")
    assert not _looks_like_github_token("ghp_ has spaces here_xxxxx")
    assert not _looks_like_github_token("not_a_token_at_all_xxxxxxxxxx")
