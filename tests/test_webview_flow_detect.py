"""Independent WebView classify (mirror of browser-guide, HTML-based)."""

from __future__ import annotations

from app.ui.webview_flow_detect import (
    classify_webview_sample,
    detect_webview_method,
    extract_pat_from_html,
    guide_copy_for_webview_kind,
    looks_like_github_logged_out_html,
    looks_like_token_note_taken_html,
)


def test_note_taken_html() -> None:
    html = "<div>Validation failed: Note has already been taken</div>"
    assert looks_like_token_note_taken_html(
        "https://github.com/settings/tokens", html=html
    )
    kind, idx, meta = classify_webview_sample(
        "https://github.com/settings/tokens",
        title="Tokens",
        html=html,
    )
    assert kind == "token_error" and idx == 2
    assert meta.get("token_error") == "note_taken"


def test_logged_out_sign_in_sign_up_html() -> None:
    html = "Sign up for GitHub\nSign in to GitHub\nProduct"
    assert looks_like_github_logged_out_html("https://github.com/", html=html)
    assert (
        detect_webview_method("https://github.com/", html=html) == "github_logged_out"
    )
    kind, idx, meta = classify_webview_sample(
        "https://github.com/", title="GitHub", html=html
    )
    assert kind == "logged_out" and idx == 0


def test_google_blocked_rejected_url() -> None:
    kind, idx, meta = classify_webview_sample(
        "https://accounts.google.com/v3/signin/rejected?flowName=GlifWebSignIn",
        title="Sign in - Google Accounts",
        html="Couldn't sign you in",
    )
    assert kind == "rejected" and meta.get("method") == "google_blocked"


def test_visible_pat_reached() -> None:
    fake = "ghp_" + ("Z" * 36)
    html = f"Make sure to copy your personal access token now.\n{fake}\n"
    assert extract_pat_from_html(html=html) == fake
    kind, idx, meta = classify_webview_sample(
        "https://github.com/settings/tokens",
        html=html,
    )
    assert kind == "reached" and idx == 3
    assert meta.get("visible_pat") == fake


def test_tokens_list_reached() -> None:
    kind, idx, _m = classify_webview_sample(
        "https://github.com/settings/tokens",
        title="Personal Access Tokens",
        html="Generate new token (classic)",
    )
    assert kind == "reached" and idx == 2


def test_guide_copy_leads_short() -> None:
    from app.ui.connect_webview import GUIDE_LEAD_MAX_CHARS, guide_lead

    for kind in ("rejected", "logged_out", "token_error", "away"):
        pair = guide_copy_for_webview_kind(kind)
        assert pair is not None
        guide_lead(pair[1])
        assert len(pair[1]) <= GUIDE_LEAD_MAX_CHARS
