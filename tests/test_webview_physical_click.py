"""Physical click helpers + cross-check of expiry→generate chain wiring."""

from __future__ import annotations

from app.ui.webview_physical_click import parse_target_rect


def test_parse_target_rect_ok() -> None:
    raw = '{"ok": true, "x": 10, "y": 20, "w": 100, "h": 30, "label": "90 days", "method": "expiry-option"}'
    d = parse_target_rect(raw)
    assert d["ok"] is True
    assert d["w"] == 100
    assert "90" in d["label"]


def test_parse_target_rect_bad() -> None:
    assert parse_target_rect(None) == {}
    assert parse_target_rect("not-json") == {}


def test_classic_pat_fixture_uses_action_menu_not_select() -> None:
    """Cross-check: saved GitHub form HTML matches what our JS targets."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    fixture = root / "temp" / "Github_Classic_Key_만들기.html"
    if not fixture.is_file():
        return  # optional local capture
    html = fixture.read_text(encoding="utf-8", errors="replace")
    assert "oauth_access[default_expires_at]" in html
    assert "js-new-default-token-expiration-select" in html
    assert "data-value=\"90\"" in html or "data-value='90'" in html
    assert "No expiration" in html
    assert "Generate token" in html
    assert 'type="submit"' in html
    # Old selector must not be required
    assert "oauth_access_expires_at" not in html or html.count("oauth_access_expires_at") == 0
    from app.ui.connect_webview import (
        _JS_PAT_FORM_READY,
        _JS_READ_EXPIRATION,
        _JS_SET_EXPIRATION,
    )

    assert "default_expires_at" in _JS_SET_EXPIRATION
    assert "default_expires_at" in _JS_READ_EXPIRATION
    assert "new_oauth_access" in _JS_PAT_FORM_READY
    assert "hasGenerate" in _JS_PAT_FORM_READY


def test_expiry_then_generate_chain_exists() -> None:
    from app.ui.connect_webview import (
        GitHubConnectWebPane,
        _JS_CLICK_GENERATE_TOKEN,
        _JS_SET_EXPIRATION,
    )

    assert hasattr(GitHubConnectWebPane, "apply_expiration_choice")
    assert hasattr(GitHubConnectWebPane, "_schedule_expiry_then_generate")
    assert hasattr(GitHubConnectWebPane, "_try_click_generate_token")
    assert "getBoundingClientRect" in __import__(
        "app.ui.webview_physical_click", fromlist=["_JS_FIND_TARGET_RECT"]
    )._JS_FIND_TARGET_RECT
    assert "default_expires_at" in _JS_SET_EXPIRATION or "expire" in _JS_SET_EXPIRATION
    # Prefer requestSubmit — .click() is ignored by Primer/GitHub often
    assert "requestSubmit" in _JS_CLICK_GENERATE_TOKEN


def test_generate_js_skips_list_button() -> None:
    from app.ui.connect_webview import _JS_CLICK_GENERATE_TOKEN

    assert "Generate new token" in _JS_CLICK_GENERATE_TOKEN
    assert "Generate token" in _JS_CLICK_GENERATE_TOKEN
    assert "requestSubmit" in _JS_CLICK_GENERATE_TOKEN
