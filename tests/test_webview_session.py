"""Unit tests for GitHub WebEngine session cookie helpers."""

from __future__ import annotations


class _FakeCookie:
    def __init__(self, name: str, domain: str) -> None:
        self._name = name.encode("utf-8") if isinstance(name, str) else name
        self._domain = domain

    def name(self):
        return self._name

    def domain(self):
        return self._domain


def test_github_session_cookie_detection() -> None:
    from app.ui.webview_session import (
        is_github_related_cookie,
        is_github_session_cookie,
    )

    assert is_github_session_cookie(
        _FakeCookie("user_session", ".github.com")
    )
    assert is_github_session_cookie(
        _FakeCookie("logged_in", "github.com")
    )
    assert is_github_session_cookie(
        _FakeCookie("__Host-user_session_same_site", "github.com")
    )
    assert not is_github_session_cookie(
        _FakeCookie("_ga", ".github.com")
    )
    assert not is_github_session_cookie(
        _FakeCookie("user_session", ".example.com")
    )
    assert is_github_related_cookie(_FakeCookie("_gh_sess", ".github.com"))
    assert is_github_related_cookie(_FakeCookie("_ga", ".github.com"))
    assert not is_github_related_cookie(_FakeCookie("sid", ".google.com"))

    from app.ui.webview_session import (
        GITHUB_LOGOUT_URL,
        cookie_suggests_github_session,
    )

    # Login cookies only — analytics must not trigger the keep/logout UI
    assert not cookie_suggests_github_session(_FakeCookie("_octo", ".github.com"))
    assert not cookie_suggests_github_session(_FakeCookie("_ga", ".github.com"))
    assert cookie_suggests_github_session(
        _FakeCookie("user_session", ".github.com")
    )
    assert cookie_suggests_github_session(
        _FakeCookie("logged_in", "github.com")
    )
    assert not cookie_suggests_github_session(_FakeCookie("sid", ".google.com"))
    assert GITHUB_LOGOUT_URL.endswith("/logout")
