"""Browser address helpers + checklist mapping (no live browser required)."""

from __future__ import annotations

from app.ui.connect_webview import is_google_signin_rejected
from app.ui.external_pat_guide import checklist_index_for_url, classify_browser_url
from app.util.browser_address import _normalize_url, browser_address_available


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


def test_browser_address_available_is_bool() -> None:
    assert isinstance(browser_address_available(), bool)
