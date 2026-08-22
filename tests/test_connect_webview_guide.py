"""Connect WebView helpers (no live WebEngine required for these)."""

from __future__ import annotations

from app.auth.github_page_stage import GitHubPageStage
from app.ui.connect_webview import checklist_text, guide_line_for_stage, webengine_available


def test_guide_line_for_login() -> None:
    line = guide_line_for_stage(GitHubPageStage.LOGIN)
    assert "로그인" in line


def test_checklist_marks_reached() -> None:
    text = checklist_text(
        {GitHubPageStage.LOGIN, GitHubPageStage.AUTH_2FA},
        GitHubPageStage.AUTH_2FA,
    )
    assert "✓ 로그인" in text
    assert "【인증 코드】" in text
    assert "→" in text


def test_webengine_available_is_bool() -> None:
    assert isinstance(webengine_available(), bool)
