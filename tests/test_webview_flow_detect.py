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


def test_away_return_pre_and_post_login_rules() -> None:
    from app.ui.webview_flow_detect import (
        looks_like_github_token_flow_url,
        looks_like_github_user_profile_url,
        should_start_away_return_countdown,
    )

    assert looks_like_github_user_profile_url("https://github.com/octocat")
    assert looks_like_github_token_flow_url(
        "https://github.com/settings/tokens/new?scopes=repo"
    )
    assert looks_like_github_token_flow_url("https://github.com/settings/tokens")
    assert not looks_like_github_token_flow_url("https://github.com/settings/profile")

    lo = "Sign up for GitHub\nSign in to GitHub"
    li = "Dashboard\nPull requests"

    # Pre-login: any github sub-URL rolls back (login/sessions excluded via kind)
    for url in (
        "https://github.com/",
        "https://github.com/explore",
        "https://github.com/octocat",
        "https://github.com/octocat/Hello-World",
        "https://github.com/features",
        "https://github.com/logout",
        "https://github.com/notifications",
    ):
        kind, _i, _m = classify_webview_sample(url, html=lo)
        assert kind == "logged_out", url
        assert should_start_away_return_countdown(kind, url), url

    # Login / sessions stay (current)
    for url in (
        "https://github.com/login",
        "https://github.com/sessions/two-factor",
    ):
        kind, _i, _m = classify_webview_sample(url, html="")
        assert kind == "current", url
        assert not should_start_away_return_countdown(kind, url), url

    # Post-login: non-token pages roll back; token pages stay
    for url in (
        "https://github.com/",
        "https://github.com/notifications",
        "https://github.com/octocat",
        "https://github.com/octocat/Hello-World",
        "https://github.com/settings/profile",
        "https://github.com/pulls",
    ):
        kind, _i, _m = classify_webview_sample(url, html=li)
        assert kind == "reached", url
        assert should_start_away_return_countdown(kind, url), url

    for url in (
        "https://github.com/settings/tokens",
        "https://github.com/settings/tokens/new?scopes=repo",
        "https://github.com/settings/personal-access-tokens/new",
    ):
        kind, _i, _m = classify_webview_sample(url, html=li)
        assert kind == "reached", url
        assert not should_start_away_return_countdown(kind, url), url

    assert should_start_away_return_countdown(
        "away", "https://www.youtube.com/watch?v=1"
    )


def test_off_family_away_helpers() -> None:
    from app.ui.webview_flow_detect import (
        away_return_countdown_seconds,
        away_return_target_url,
        format_away_return_banner,
        is_off_github_flow_family,
    )

    assert away_return_countdown_seconds() == 5
    target = away_return_target_url()
    assert "github.com/settings/tokens/new" in target
    assert "scopes=repo" in target
    assert format_away_return_banner(5) == (
        "5초 후 Github 키 발급 페이지로 다시 이동합니다."
    )
    assert format_away_return_banner(1).startswith("1초 후")

    assert not is_off_github_flow_family("https://github.com/settings/tokens")
    assert not is_off_github_flow_family("https://github.com/login")
    assert not is_off_github_flow_family(
        "https://accounts.google.com/o/oauth2/v2/auth?client_id=x"
    )
    assert not is_off_github_flow_family(
        "https://appleid.apple.com/auth/authorize?client_id=x"
    )
    assert not is_off_github_flow_family("")
    assert not is_off_github_flow_family("about:blank")

    assert is_off_github_flow_family("https://www.youtube.com/watch?v=1")
    assert is_off_github_flow_family("https://news.naver.com/")

    kind, idx, meta = classify_webview_sample(
        "https://www.youtube.com/watch?v=1", title="YouTube", html="watch"
    )
    assert kind == "away" and idx is None
    assert meta.get("method") == "away"


def test_logged_in_home_should_auto_open_token_page() -> None:
    from app.ui.webview_flow_detect import (
        is_github_main_home_url,
        should_auto_open_token_page,
    )

    assert is_github_main_home_url("https://github.com/")
    assert is_github_main_home_url("https://github.com")
    assert is_github_main_home_url("https://github.com/dashboard")
    assert not is_github_main_home_url("https://github.com/settings/tokens")
    assert not is_github_main_home_url("https://github.com/login")

    kind, idx, _m = classify_webview_sample(
        "https://github.com/",
        title="GitHub",
        html="Dashboard\nPull requests",
    )
    assert kind == "reached" and idx == 1
    assert should_auto_open_token_page(
        kind=kind,
        idx=idx,
        already_opened=False,
        url="https://github.com/",
        title="GitHub",
        page_text="Dashboard\nPull requests",
    )
    assert not should_auto_open_token_page(
        kind=kind,
        idx=idx,
        already_opened=True,
        url="https://github.com/",
        title="GitHub",
        page_text="Dashboard\nPull requests",
    )


def test_guide_copy_leads_short() -> None:
    from app.ui.connect_webview import GUIDE_LEAD_MAX_CHARS, guide_lead

    for kind in ("rejected", "logged_out", "token_error", "away"):
        pair = guide_copy_for_webview_kind(kind)
        assert pair is not None
        guide_lead(pair[1])
        assert len(pair[1]) <= GUIDE_LEAD_MAX_CHARS
