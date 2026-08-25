"""Browser address helpers + checklist mapping (no live browser required)."""

from __future__ import annotations

from app.ui.connect_webview import is_google_signin_rejected
from app.ui.external_pat_guide import (
    away_from_flow_guide_copy,
    build_pat_create_url,
    checklist_index_for_url,
    checklist_row_label,
    classify_browser_sample,
    classify_browser_url,
    fallback_return_url,
    progress_guide_for_reached,
    should_auto_open_token_page,
    token_note_error_guide_copy,
)
from app.util.browser_address import (
    _normalize_url,
    analyze_google_signin_block,
    browser_address_available,
    detect_signin_method,
    extract_visible_pat,
    is_apple_signin_url,
    is_github_flow_family_url,
    looks_like_github_logged_out_ui,
    looks_like_passkey_os_prompt,
    looks_like_token_issued_banner,
    looks_like_token_note_taken,
    token_create_error_snippets,
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


def test_github_logged_out_via_sign_in_sign_up_ui() -> None:
    """github.com URL is ambiguous — Sign in/Sign up UI means logged out."""
    # Without UI text, bare github.com looks like post-login (reached)
    kind_bare, idx_bare = classify_browser_url("https://github.com/")
    assert kind_bare == "reached" and idx_bare == 1

    # Strong UIA phrases from Chrome (GroupControl / TabItem names)
    ui_logged_out = (
        "Sign up for GitHub\n"
        "Sign in to GitHub\n"
        "GitHub\n"
        "Product\n"
    )
    assert looks_like_github_logged_out_ui(
        "GitHub", ui_logged_out, url="https://github.com/"
    )
    assert (
        detect_signin_method(
            "https://github.com/",
            window_title="GitHub",
            ui_text=ui_logged_out,
        )
        == "github_logged_out"
    )
    kind, idx, meta = classify_browser_sample(
        "https://github.com/",
        window_title="GitHub",
        ui_text=ui_logged_out,
    )
    assert kind == "logged_out" and idx == 0
    assert meta.get("method") == "github_logged_out"

    # Weaker: both Sign in + Sign up on github.com
    assert looks_like_github_logged_out_ui(
        "GitHub · Build and ship software on a single, collaborative platform",
        "Sign in\nSign up\nFeatures",
        url="https://github.com",
    )
    kind2, idx2, meta2 = classify_browser_sample(
        "https://github.com",
        window_title="GitHub",
        ui_text="Sign in\nSign up\nFeatures",
    )
    assert kind2 == "logged_out" and idx2 == 0
    assert meta2.get("method") == "github_logged_out"

    # Logged-in dashboard chrome must NOT look logged out
    assert not looks_like_github_logged_out_ui(
        "GitHub",
        "Dashboard\nPull requests\nIssues\nCodespaces\nMarketplace",
        url="https://github.com/",
    )
    assert (
        detect_signin_method(
            "https://github.com/",
            window_title="GitHub",
            ui_text="Dashboard\nPull requests\nIssues",
        )
        == "github"
    )


def test_away_from_github_flow_family() -> None:
    """Off-family URLs get soft away copy — never treated as progress."""
    assert is_github_flow_family_url("https://github.com/settings/tokens")
    assert is_github_flow_family_url(
        "https://accounts.google.com/v3/signin/identifier"
    )
    assert is_github_flow_family_url(
        "https://appleid.apple.com/auth/authorize?client_id=x"
    )
    assert not is_github_flow_family_url("https://www.youtube.com/watch?v=1")
    assert not is_github_flow_family_url("https://news.naver.com/")

    kind, idx = classify_browser_url("https://www.youtube.com/watch?v=abc")
    assert kind == "away" and idx is None
    kind2, idx2, meta = classify_browser_sample(
        "https://news.naver.com/",
        window_title="네이버 뉴스",
        ui_text="속보",
    )
    assert kind2 == "away" and idx2 is None
    assert meta.get("method") == "away"

    # Family pages still classified normally
    assert classify_browser_url("https://github.com/login")[0] == "current"
    assert (
        classify_browser_url(
            "https://accounts.google.com/v3/signin/identifier"
        )[0]
        == "current"
    )

    title, lead, verify = away_from_flow_guide_copy()
    assert "GitHub" in title
    assert lead == "원하시면 마지막 페이지로 돌아가도 됩니다."
    assert "연계" in verify or "아님" in verify

    assert fallback_return_url(reached=-1).endswith("/login")
    assert fallback_return_url(reached=1) == "https://github.com/"
    assert "tokens/new" in fallback_return_url(reached=2)


def test_extract_visible_pat_from_settings_tokens_uia() -> None:
    """After Generate token, /settings/tokens may show ghp_… in accessible text."""
    fake = (
        "ghp_" + ("A" * 36)
    )  # classic-shaped; length satisfies extract_visible_pat
    ui = (
        "Make sure to copy your personal access token now.\n"
        "You won’t be able to see it again!\n"
        f"{fake}\n"
        "Copy token\n"
    )
    assert looks_like_token_issued_banner("", ui)
    assert extract_visible_pat(ui) == fake
    assert extract_visible_pat("no secret here") is None

    kind, idx, meta = classify_browser_sample(
        "https://github.com/settings/tokens",
        window_title="Personal Access Tokens (Classic)",
        ui_text=ui,
    )
    assert kind == "reached" and idx == 3
    assert meta.get("method") == "token_visible"
    assert meta.get("visible_pat") == fake

    # List page without secret stays at key-create step
    kind2, idx2, _m2 = classify_browser_sample(
        "https://github.com/settings/tokens",
        window_title="Personal Access Tokens (Classic)",
        ui_text="Generate new token (classic)\nTokens (classic)",
    )
    assert kind2 == "reached" and idx2 == 2


def test_token_note_already_taken_uia() -> None:
    """Duplicate Note flash must be read from UIA text, not treated as success."""
    ui = (
        "New personal access token\n"
        "Dismiss this message\n"
        "Validation failed: Note has already been taken\n"
        "Note has already been taken\n"
        "Generate token\n"
    )
    assert looks_like_token_note_taken(
        "New Personal Access Token (classic)",
        ui,
        url="https://github.com/settings/tokens",
    )
    snippets = token_create_error_snippets(
        "New Personal Access Token (classic)", ui
    )
    assert any("already been taken" in s.lower() for s in snippets)

    kind, idx, meta = classify_browser_sample(
        "https://github.com/settings/tokens",
        window_title="New Personal Access Token (classic)",
        ui_text=ui,
    )
    assert kind == "token_error" and idx == 2
    assert meta.get("method") == "token_note_taken"
    assert meta.get("token_error") == "note_taken"

    # Without error text, same URL is normal token list progress
    kind_ok, idx_ok, _m = classify_browser_sample(
        "https://github.com/settings/tokens",
        window_title="Personal Access Tokens (Classic)",
        ui_text="Generate new token (classic)\nTokens (classic)",
    )
    assert kind_ok == "reached" and idx_ok == 2

    row = checklist_row_label(
        2, reached=1, current=2, google_rejected=False, token_note_taken=True
    )
    assert row.startswith("!")
    assert "중복" in row

    title, lead, verify = token_note_error_guide_copy()
    assert "Note" in title
    assert "이름" in lead or "열기" in lead
    assert "already been taken" in verify.lower() or "Note" in verify

    url = build_pat_create_url()
    assert "settings/tokens/new" in url
    assert "scopes=repo" in url
    assert "description=CloneUp-" in url  # unique suffix, not bare CloneUp


def test_progress_guide_after_login_confirmed() -> None:
    """After github.com login, guide nudges toward token create (auto-open once)."""
    kind, idx = classify_browser_url("https://github.com/")
    assert kind == "reached" and idx == 1

    title, lead, verify = progress_guide_for_reached(1)
    assert "로그인" in title or "키" in title
    assert "Generate" in lead or "키" in lead
    assert "로그인" in verify or "키" in verify

    title2, lead2, _v2 = progress_guide_for_reached(2)
    assert "키" in title2
    assert "Generate" in lead2

    title3, lead3, _v3 = progress_guide_for_reached(3)
    assert "복사" in title3 or "키" in title3
    assert "연결" in lead3 or "복사" in lead3

    assert should_auto_open_token_page(
        kind="reached", idx=1, already_opened=False
    )
    assert not should_auto_open_token_page(
        kind="reached", idx=1, already_opened=True
    )
    assert not should_auto_open_token_page(
        kind="reached", idx=2, already_opened=False
    )
    assert not should_auto_open_token_page(
        kind="logged_out", idx=0, already_opened=False
    )

    # Checklist: login done → next row is "make key"
    row2 = checklist_row_label(2, reached=1, current=2, google_rejected=False)
    assert row2.startswith("→")
    row1 = checklist_row_label(1, reached=1, current=2, google_rejected=False)
    assert row1.startswith("✓")


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
