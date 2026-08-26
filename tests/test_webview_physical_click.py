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


def test_expiry_then_generate_chain_exists() -> None:
    from app.ui.connect_webview import GitHubConnectWebPane, _JS_SET_EXPIRATION, _JS_FIND_TOKEN

    assert hasattr(GitHubConnectWebPane, "apply_expiration_choice")
    assert hasattr(GitHubConnectWebPane, "_schedule_expiry_then_generate")
    assert hasattr(GitHubConnectWebPane, "_try_click_generate_token")
    # Physical path module is imported by apply_expiration_choice
    assert "getBoundingClientRect" in __import__(
        "app.ui.webview_physical_click", fromlist=["_JS_FIND_TARGET_RECT"]
    )._JS_FIND_TARGET_RECT
    assert "oauth_access_expires_at" in _JS_SET_EXPIRATION or "expire" in _JS_SET_EXPIRATION


def test_generate_js_skips_list_button() -> None:
    from app.ui.connect_webview import _JS_CLICK_GENERATE_TOKEN

    assert "Generate new token" in _JS_CLICK_GENERATE_TOKEN
    assert "Generate token" in _JS_CLICK_GENERATE_TOKEN
