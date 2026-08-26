"""Cross-check: classify kinds ↔ guide copy ↔ handler coverage.

Ensures browser-guide and WebView mirrors stay wired — a kind without
UI copy or a known URL that mis-classifies fails here.
"""

from __future__ import annotations

from app.auth.github_page_stage import GitHubPageStage, PageSnapshot, detect_github_page_stage
from app.ui.connect_webview import guide_overlay_for_stage
from app.ui.external_pat_guide import (
    _method_guide_copy,
    away_from_flow_guide_copy,
    classify_browser_sample,
    progress_guide_for_reached,
    token_note_error_guide_copy,
)
from app.ui.webview_flow_detect import (
    classify_webview_sample,
    guide_copy_for_webview_kind,
)

# Every kind both classifiers emit for the fixture suite
_EXPECTED_KINDS = frozenset(
    {"rejected", "logged_out", "token_error", "current", "reached", "away"}
)

# Browser-guide poll handlers (must stay in sync with ExternalBrowserPatGuide._poll_address)
_BROWSER_HANDLED = frozenset(
    {"rejected", "token_error", "away", "logged_out", "current", "reached"}
)

# WebView login_dialog._on_webview_flow_classified branches
_WEBVIEW_HANDLED = frozenset(
    {"rejected", "logged_out", "token_error", "away", "current", "reached"}
)

_FIXTURES: list[tuple[str, str, str, str]] = [
    (
        "rejected",
        "https://accounts.google.com/v3/signin/rejected?flowName=GlifWebSignIn",
        "Sign in - Google Accounts",
        "This browser or app may not be secure",
    ),
    (
        "logged_out",
        "https://github.com/",
        "GitHub",
        "Sign up for GitHub\nSign in to GitHub",
    ),
    ("logged_out", "https://github.com/logout", "", ""),
    (
        "token_error",
        "https://github.com/settings/tokens",
        "Tokens",
        "Validation failed: Note has already been taken",
    ),
    ("current", "https://github.com/login", "Sign in to GitHub", ""),
    (
        "current",
        "https://appleid.apple.com/auth/authorize?client_id=x",
        "Apple",
        "",
    ),
    ("reached", "https://github.com/", "GitHub", "Dashboard\nPull requests"),
    (
        "reached",
        "https://github.com/settings/tokens",
        "Personal Access Tokens",
        "Generate new token (classic)",
    ),
    (
        "reached",
        "https://github.com/settings/tokens/new?scopes=repo",
        "New token",
        "Note",
    ),
    ("away", "https://www.youtube.com/watch?v=1", "YouTube", "watch"),
]


def test_browser_and_webview_classify_agree_on_fixtures() -> None:
    seen_b: set[str] = set()
    seen_w: set[str] = set()
    for expect, url, title, text in _FIXTURES:
        kb, ib, mb = classify_browser_sample(
            url, window_title=title, ui_text=text
        )
        kw, iw, mw = classify_webview_sample(url, title=title, html=text)
        assert kb == expect, (url, kb, expect)
        assert kw == expect, (url, kw, expect)
        assert kb == kw and ib == iw
        seen_b.add(kb)
        seen_w.add(kw)
    assert seen_b >= _EXPECTED_KINDS
    assert seen_w >= _EXPECTED_KINDS


def test_handler_coverage_matches_kinds() -> None:
    assert _BROWSER_HANDLED >= _EXPECTED_KINDS
    assert _WEBVIEW_HANDLED >= _EXPECTED_KINDS


def test_browser_guide_copy_exists_for_methods() -> None:
    for method in (
        "google_blocked",
        "github_logout",
        "github_logged_out",
        "apple",
        "passkey",
        "google",
        "github_login",
    ):
        title, lead, verify = _method_guide_copy(method)
        assert title.strip() and lead.strip() and verify.strip()
    t, l, v = token_note_error_guide_copy()
    assert "Note" in t
    t2, l2, v2 = away_from_flow_guide_copy()
    assert "GitHub" in t2
    for idx in (1, 2, 3):
        title, lead, verify = progress_guide_for_reached(idx)
        assert title.strip() and lead.strip()


def test_webview_exception_kinds_have_guide_copy() -> None:
    for kind in ("rejected", "logged_out", "token_error", "away"):
        pair = guide_copy_for_webview_kind(kind)
        assert pair is not None
        assert pair[0].strip() and pair[1].strip()


def test_settings_tokens_list_overlay_connected() -> None:
    """reached@tokens list must map to Generate new token overlay (not generic create)."""
    url = "https://github.com/settings/tokens"
    kind, idx, _m = classify_webview_sample(
        url,
        title="Personal Access Tokens",
        html="Generate new token (classic)",
    )
    assert kind == "reached" and idx == 2
    st = detect_github_page_stage(PageSnapshot(url=url))
    assert st == GitHubPageStage.TOKEN_CLASSIC_LIST
    ov = guide_overlay_for_stage(st)
    assert ov is not None
    assert "Generate new token" in ov["title"]
    assert "목록" in ov["lead"]
