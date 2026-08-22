"""Connect wizard step list stays in sync with the guided PAT path."""

from __future__ import annotations


def test_connect_wizard_step_order() -> None:
    from app.ui.login_dialog import _STEP_PASTE, _STEP_WORK, _STEPS

    assert len(_STEPS) == 4
    assert _STEP_WORK == 2
    assert _STEP_PASTE == 3
    titles = [t for t, _b in _STEPS]
    assert titles == ["시작", "브라우저 열기", "브라우저에서 진행", "붙여넣기"]
    work = _STEPS[_STEP_WORK][1]
    assert "따라 한 칸씩" in work or "자동" in work
    assert "repo" in work
    assert "처음" in work
    assert "패스키" in work


def test_looks_like_github_token() -> None:
    from app.ui.login_dialog import _looks_like_github_token

    assert _looks_like_github_token("ghp_" + "a" * 36)
    assert _looks_like_github_token("github_pat_" + "x" * 40)
    assert not _looks_like_github_token("short")
    assert not _looks_like_github_token("ghp_ has spaces here_xxxxx")
    assert not _looks_like_github_token("not_a_token_at_all_xxxxxxxxxx")
