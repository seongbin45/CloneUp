"""Browser address helpers + checklist mapping (no live browser required)."""

from __future__ import annotations

from app.ui.connect_webview import is_google_signin_rejected
from app.ui.external_pat_guide import (
    checklist_index_for_url,
    checklist_row_label,
    classify_browser_sample,
    classify_browser_url,
)
from app.util.browser_address import (
    _normalize_url,
    analyze_google_signin_block,
    browser_address_available,
)


def test_normalize_url() -> None:
    assert _normalize_url("github.com/settings/tokens").startswith("https://")
    assert _normalize_url("https://accounts.google.com/x").startswith("https://")
    assert _normalize_url("javascript:alert(1)") == ""
    assert _normalize_url("") == ""


def test_google_signin_rejected_url() -> None:
    rejected = (
        "https://accounts.google.com/v3/signin/rejected"
        "?continue=https://github.com&flowName=GlifWebSignIn"
    )
    assert is_google_signin_rejected(rejected)
    assert not is_google_signin_rejected(
        "https://accounts.google.com/v3/signin/identifier?flowName=GlifWebSignIn"
    )
    assert not is_google_signin_rejected("https://github.com/login")


def test_analyze_google_block_cross_check() -> None:
    rejected = (
        "https://accounts.google.com/v3/signin/rejected"
        "?continue=https://github.com&flowName=GlifWebSignIn"
    )
    a = analyze_google_signin_block(rejected)
    assert a.blocked and a.url_hit
    assert any("rejected" in r.lower() or "URL" in r for r in a.reasons)

    # Text-only hit on Google host (when UIA exposes the interstitial copy)
    b = analyze_google_signin_block(
        "https://accounts.google.com/v3/signin/identifier",
        window_title="Sign in - Google Accounts",
        ui_text="Couldn't sign you in\nThis browser or app may not be secure.",
    )
    assert b.blocked and b.text_hit
    assert any("텍스트" in r or "제목" in r for r in b.reasons)

    # Progressing Google page without block text
    c = analyze_google_signin_block(
        "https://accounts.google.com/v3/signin/identifier?flowName=GlifWebSignIn",
        window_title="Sign in - Google Accounts",
        ui_text="Email or phone\nForgot email?",
    )
    assert not c.blocked


def test_checklist_index_for_url() -> None:
    # In-progress Google — index 0 via classify, but rejected must NOT count as done
    assert checklist_index_for_url("https://accounts.google.com/signin") == 0
    rejected = (
        "https://accounts.google.com/v3/signin/rejected"
        "?continue=https://github.com&flowName=GlifWebSignIn"
    )
    assert checklist_index_for_url(rejected) is None
    kind, idx = classify_browser_url(rejected)
    assert kind == "rejected" and idx == 0
    kind_s, idx_s, analysis = classify_browser_sample(
        rejected, ui_text="Try using a different browser"
    )
    assert kind_s == "rejected" and analysis is not None and analysis.blocked
    kind2, idx2 = classify_browser_url(
        "https://accounts.google.com/v3/signin/identifier"
    )
    assert kind2 == "current" and idx2 == 0
    assert checklist_index_for_url("https://github.com/login") == 1
    assert checklist_index_for_url("https://github.com/settings/tokens") == 2
    assert (
        checklist_index_for_url(
            "https://github.com/settings/tokens/new?scopes=repo"
        )
        == 2
    )
    assert checklist_index_for_url("https://example.com/") is None


def test_checklist_row_reflects_google_rejected() -> None:
    """Rejected Google must show on row 0 — not stay as empty ○."""
    row0 = checklist_row_label(
        0, reached=-1, current=None, google_rejected=True
    )
    assert row0.startswith("!")
    assert "막힘" in row0
    # Even if current was wrongly set to 0, rejected wins
    row0b = checklist_row_label(
        0, reached=-1, current=0, google_rejected=True
    )
    assert row0b.startswith("!")
    assert not row0b.startswith("→")
    assert not row0b.startswith("○")
    # Other rows stay empty
    assert checklist_row_label(
        1, reached=-1, current=None, google_rejected=True
    ).startswith("○")


def test_browser_address_available_is_bool() -> None:
    assert isinstance(browser_address_available(), bool)
