"""Connect WebView helpers (no live WebEngine required for these)."""

from __future__ import annotations

import pytest

from app.auth.github_page_stage import GitHubPageStage
from app.ui.connect_webview import (
    GUIDE_LEAD_MAX_CHARS,
    checklist_text,
    guide_lead,
    guide_line_for_stage,
    guide_overlay_for_stage,
    step_copy,
    webengine_available,
)


def test_guide_line_for_login() -> None:
    line = guide_line_for_stage(GitHubPageStage.LOGIN)
    assert "로그인" in line


def test_checklist_marks_reached() -> None:
    text = checklist_text(
        {GitHubPageStage.LOGIN, GitHubPageStage.AUTH_2FA},
        GitHubPageStage.AUTH_2FA,
    )
    assert "✓ 로그인" in text
    assert "● 인증 코드" in text
    assert "○ 키 만들기" in text
    assert "○ 키 복사" in text
    assert "→" in text


def test_step_copy_four_steps() -> None:
    from app.ui.connect_webview import UI_STEP_NAMES

    assert len(UI_STEP_NAMES) == 4
    assert step_copy(0)["showKey"] is False
    assert step_copy(3)["showKey"] is True
    assert "패스키" not in str(step_copy(0)["title"])


def test_ui_index_for_stage() -> None:
    from app.ui.connect_webview import ui_index_for_stage

    assert ui_index_for_stage(GitHubPageStage.LOGIN) == 0
    assert ui_index_for_stage(GitHubPageStage.AUTH_2FA) == 1
    assert ui_index_for_stage(GitHubPageStage.TOKEN_CLASSIC_NEW) == 2
    assert ui_index_for_stage(GitHubPageStage.TOKEN_CLASSIC_LIST) == 2
    assert ui_index_for_stage(GitHubPageStage.TOKEN_FINE_LIST) == 2
    assert ui_index_for_stage(GitHubPageStage.TOKEN_ISSUED) == 3


def test_guide_overlay_tokens_list() -> None:
    ov = guide_overlay_for_stage(GitHubPageStage.TOKEN_CLASSIC_LIST)
    assert ov is not None
    assert "Generate new token" in ov["title"]
    assert "목록" in ov["lead"]
    assert "Generate new token" in ov["lead"]
    assert ov.get("stepName") == "키 목록"
    assert len(ov["lead"]) <= GUIDE_LEAD_MAX_CHARS
    assert "Generate new token" in guide_line_for_stage(GitHubPageStage.TOKEN_CLASSIC_LIST)

    ov_fine = guide_overlay_for_stage(GitHubPageStage.TOKEN_FINE_LIST)
    assert ov_fine is not None
    assert "Generate new token" in ov_fine["lead"]
    assert ov_fine.get("stepName") == "키 목록"
    assert len(ov_fine["lead"]) <= GUIDE_LEAD_MAX_CHARS

    # Exact create form has no overlay — uses step_copy title
    assert guide_overlay_for_stage(GitHubPageStage.TOKEN_CLASSIC_NEW) is None


def test_settings_tokens_url_maps_to_list_stage() -> None:
    from app.auth.github_page_stage import PageSnapshot, detect_github_page_stage

    st = detect_github_page_stage(
        PageSnapshot(url="https://github.com/settings/tokens")
    )
    assert st == GitHubPageStage.TOKEN_CLASSIC_LIST
    ov = guide_overlay_for_stage(st)
    assert ov is not None
    assert ov["title"].startswith("Generate new token")


def test_guide_lead_max_chars_rule() -> None:
    """Rule: connect wizard lead (title 아래 설명) ≤ 60 Unicode chars."""
    assert GUIDE_LEAD_MAX_CHARS == 60
    assert guide_lead("가" * 60) == "가" * 60
    with pytest.raises(ValueError, match="max 60"):
        guide_lead("가" * 61)

    for i in range(4):
        lead = str(step_copy(i)["lead"])
        assert len(lead) <= GUIDE_LEAD_MAX_CHARS, (i, len(lead), lead)

    for st in GitHubPageStage:
        ov = guide_overlay_for_stage(st)
        if ov is None:
            continue
        assert len(ov["lead"]) <= GUIDE_LEAD_MAX_CHARS, (st, len(ov["lead"]), ov["lead"])


def test_webengine_available_is_bool() -> None:
    assert isinstance(webengine_available(), bool)
