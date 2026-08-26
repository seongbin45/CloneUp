"""Detect / clear GitHub login cookies in Qt WebEngine profiles.

Used before Path A WebView load so the user can keep or discard a prior
in-app browser session. Independent of app keyring PAT storage.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Chromium / GitHub auth cookies that imply a logged-in browser session.
_GITHUB_SESSION_COOKIE_NAMES = frozenset(
    {
        "user_session",
        "__host-user_session_same_site",
        "logged_in",
        "_gh_sess",
        "dotcom_user",
    }
)

_PROBE_TIMEOUT_MS = 800
_CLEAR_SETTLE_MS = 500

GITHUB_LOGOUT_URL = "https://github.com/logout"


def cookie_domain_str(cookie: Any) -> str:
    try:
        d = cookie.domain()
        if callable(d):
            d = d()
        return str(d or "").lower().lstrip(".")
    except Exception:
        return ""


def cookie_name_str(cookie: Any) -> str:
    try:
        n = cookie.name()
        if callable(n):
            n = n()
        if isinstance(n, (bytes, bytearray)):
            return bytes(n).decode("utf-8", errors="replace").lower()
        return str(n or "").lower()
    except Exception:
        return ""


def is_github_cookie_domain(domain: str) -> bool:
    d = (domain or "").lower().lstrip(".")
    return d == "github.com" or d.endswith(".github.com")


def is_github_session_cookie(cookie: Any) -> bool:
    """True if this cookie is strong evidence of a GitHub logged-in session."""
    if not is_github_cookie_domain(cookie_domain_str(cookie)):
        return False
    name = cookie_name_str(cookie)
    if name in _GITHUB_SESSION_COOKIE_NAMES:
        return True
    # __Host- prefix variants
    if "user_session" in name:
        return True
    return False


def is_github_related_cookie(cookie: Any) -> bool:
    return is_github_cookie_domain(cookie_domain_str(cookie))


def cookie_suggests_github_session(cookie: Any) -> bool:
    """
    Signal for the keep/logout gate — **login** cookies only.

    Do not treat analytics (``_ga``, ``_octo``, …) as a session; that caused
    a false "기존 세션" flash for logged-out profiles.
    """
    return is_github_session_cookie(cookie)


def probe_github_webengine_session(
    profile: Any,
    on_done: Callable[[bool], None],
    *,
    parent: Any = None,
    timeout_ms: int = _PROBE_TIMEOUT_MS,
) -> None:
    """
    Async: load cookies from ``profile`` and call ``on_done(has_session)``.

    On missing store / errors / timeout → ``on_done(False)``.
    """
    from PySide6.QtCore import QTimer

    finished = {"done": False}

    def _finish(has: bool) -> None:
        if finished["done"]:
            return
        finished["done"] = True
        try:
            store.cookieAdded.disconnect(_on_added)
        except Exception:
            pass
        try:
            on_done(bool(has))
        except Exception:
            pass

    try:
        store = profile.cookieStore()
    except Exception:
        on_done(False)
        return
    if store is None:
        on_done(False)
        return

    found = {"session": False}

    def _on_added(cookie: Any) -> None:
        if cookie_suggests_github_session(cookie):
            found["session"] = True
            QTimer.singleShot(0, lambda: _finish(True))

    try:
        store.cookieAdded.connect(_on_added)
        store.loadAllCookies()
    except Exception:
        _finish(False)
        return

    QTimer.singleShot(
        max(50, int(timeout_ms)),
        lambda: _finish(found["session"]),
    )


def clear_github_webengine_cookies(
    profile: Any,
    on_done: Callable[[], None] | None = None,
    *,
    settle_ms: int = _CLEAR_SETTLE_MS,
) -> None:
    """
    Aggressively wipe WebEngine cookies for this profile, then ``on_done()``.

    GitHub ``user_session`` is often a *persistent* cookie, so
    ``deleteSessionCookies`` alone is not enough. We:

    1. deleteCookie each github.com cookie (with origin URL)
    2. ``deleteSessionCookies`` + ``deleteAllCookies`` (belt and suspenders)
    3. ``clearHttpCache`` when available
    """
    from PySide6.QtCore import QTimer, QUrl

    finished = {"done": False}

    def _finish() -> None:
        if finished["done"]:
            return
        finished["done"] = True
        try:
            store.cookieAdded.disconnect(_on_added)
        except Exception:
            pass
        if on_done is not None:
            try:
                on_done()
            except Exception:
                pass

    try:
        store = profile.cookieStore()
    except Exception:
        if on_done:
            on_done()
        return
    if store is None:
        if on_done:
            on_done()
        return

    collected: list[Any] = []

    def _on_added(cookie: Any) -> None:
        if is_github_related_cookie(cookie):
            collected.append(cookie)

    try:
        store.cookieAdded.connect(_on_added)
        store.loadAllCookies()
    except Exception:
        collected = []

    def _wipe() -> None:
        try:
            store.cookieAdded.disconnect(_on_added)
        except Exception:
            pass

        origin = QUrl("https://github.com/")
        for c in list(collected):
            try:
                store.deleteCookie(c, origin)
            except TypeError:
                try:
                    store.deleteCookie(c)
                except Exception:
                    pass
            except Exception:
                try:
                    store.deleteCookie(c)
                except Exception:
                    pass

        # Persistent login cookies are NOT session cookies — wipe everything
        # on this profile (CloneUp connect WebView).
        try:
            store.deleteSessionCookies()
        except Exception:
            pass
        try:
            store.deleteAllCookies()
        except Exception:
            pass

        try:
            clear_cache = getattr(profile, "clearHttpCache", None)
            if callable(clear_cache):
                clear_cache()
        except Exception:
            pass

        QTimer.singleShot(max(200, int(settle_ms)), _finish)

    # Give loadAllCookies a moment to emit, then wipe regardless
    QTimer.singleShot(max(80, min(400, _PROBE_TIMEOUT_MS)), _wipe)
