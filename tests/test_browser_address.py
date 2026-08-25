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
    detect_signin_method,
    is_apple_signin_url,
    looks_like_passkey_os_prompt,
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

    b = analyze_google_signin_block(
        "https://accounts.google.com/v3/signin/identifier",
        window_title="Sign in - Google Accounts",
        ui_text="Couldn't sign you in\nThis browser or app may not be secure.",
    )
    assert b.blocked and b.text_hit

    c = analyze_google_signin_block(
        "https://accounts.google.com/v3/signin/identifier?flowName=GlifWebSignIn",
        window_title="Sign in - Google Accounts",
        ui_text="Email or phone\nForgot email?",
    )
    assert not c.blocked


def test_apple_and_passkey_detection() -> None:
    apple = "https://appleid.apple.com/auth/authorize?client_id=xxx&redirect_uri=https://github.com"
    assert is_apple_signin_url(apple)
    assert detect_signin_method(apple) == "apple"
    kind, idx = classify_browser_url(apple)
    assert kind == "current" and idx == 0

    assert looks_like_passkey_os_prompt(
        "Windows 보안",
        "패스키로 github.com에 로그인 QR 코드",
    )
    assert (
        detect_signin_method(
            "",
            window_title="Windows 보안",
            ui_text="패스키로 github.com에 로그인",
        )
        == "passkey"
    )
    kind_p, idx_p, _m = classify_browser_sample(
        "",
        window_title="Windows 보안",
        ui_text="패스키로 로그인",
    )
    assert kind_p == "current" and idx_p == 0


def test_checklist_index_for_url() -> None:
    assert checklist_index_for_url("https://accounts.google.com/signin") == 0
    rejected = (
        "https://accounts.google.com/v3/signin/rejected"
        "?continue=https://github.com&flowName=GlifWebSignIn"
    )
    assert checklist_index_for_url(rejected) is None
    kind, idx = classify_browser_url(rejected)
    assert kind == "rejected" and idx == 0
    kind_s, idx_s, meta = classify_browser_sample(
        rejected, ui_text="Try using a different browser"
    )
    assert kind_s == "rejected"
    assert meta.get("method") == "google_blocked"

    kind2, idx2 = classify_browser_url(
        "https://accounts.google.com/v3/signin/identifier"
    )
    assert kind2 == "current" and idx2 == 0

    # github.com/login = NOT logged in
    kind_login, idx_login = classify_browser_url(
        "https://github.com/login?client_id=Ov23liuwynj1IgDmz8Tj"
    )
    assert kind_login == "current" and idx_login == 0
    assert checklist_index_for_url("https://github.com/login") == 0
    row0 = checklist_row_label(
        0, reached=-1, current=0, google_rejected=False
    )
    assert row0.startswith("→"), row0
    assert not row0.startswith("✓")

    assert checklist_index_for_url("https://github.com/settings/tokens") == 2
    assert (
        checklist_index_for_url(
            "https://github.com/settings/tokens/new?scopes=repo"
        )
        == 2
    )
    assert checklist_index_for_url("https://example.com/") is None

    # Logout must be detected (not "unknown") and reset progress semantics
    kind_out, idx_out = classify_browser_url("https://github.com/logout")
    assert kind_out == "logged_out" and idx_out == 0
    assert detect_signin_method("https://github.com/logout") == "github_logout"
    assert checklist_index_for_url("https://github.com/logout") == 0


def test_checklist_row_reflects_google_rejected() -> None:
    """Rejected Google must show on row 0 — not stay as empty ○."""
    row0 = checklist_row_label(
        0, reached=-1, current=None, google_rejected=True
    )
    assert row0.startswith("!")
    assert "막힘" in row0
    row0b = checklist_row_label(
        0, reached=-1, current=0, google_rejected=True
    )
    assert row0b.startswith("!")
    assert not row0b.startswith("→")
    assert not row0b.startswith("○")
    assert checklist_row_label(
        1, reached=-1, current=None, google_rejected=True
    ).startswith("○")


def test_browser_address_available_is_bool() -> None:
    assert isinstance(browser_address_available(), bool)
