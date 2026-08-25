"""Browser address helpers + checklist mapping (no live browser required)."""

from __future__ import annotations

from app.ui.external_pat_guide import checklist_index_for_url
from app.util.browser_address import _normalize_url, browser_address_available


def test_normalize_url() -> None:
    assert _normalize_url("github.com/settings/tokens").startswith("https://")
    assert _normalize_url("https://accounts.google.com/x").startswith("https://")
    assert _normalize_url("javascript:alert(1)") == ""
    assert _normalize_url("") == ""


def test_checklist_index_for_url() -> None:
    assert checklist_index_for_url("https://accounts.google.com/signin") == 0
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
