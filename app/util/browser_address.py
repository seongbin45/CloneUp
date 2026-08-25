"""Read the address bar of Chrome / Edge via UI Automation (Windows).

Does **not** capture the full screen or page content — only the omnibox value.
Requires optional dependency ``uiautomation`` (soft-fail if missing).
"""

from __future__ import annotations

from urllib.parse import urlparse

# Localized / English omnibox names observed on Windows Chrome/Edge
_ADDRESS_NAMES = (
    "주소창 및 검색창",
    "Address and search bar",
    "Address and search box",
    "Search or type a URL",
    "주소 표시줄 및 검색창",
)

_BROWSER_CLASS = "Chrome_WidgetWin_1"  # Chrome + Chromium Edge


def browser_address_available() -> bool:
    try:
        import uiautomation  # noqa: F401

        return True
    except Exception:
        return False


def _normalize_url(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    # Omnibox often omits the scheme
    if "://" not in text and text.startswith(("www.", "github.", "accounts.")):
        text = "https://" + text
    elif "://" not in text and "." in text and " " not in text:
        text = "https://" + text
    try:
        p = urlparse(text)
        if p.scheme not in ("http", "https"):
            return ""
        return text
    except Exception:
        return ""


def _read_edit_url(win) -> str:
    for nm in _ADDRESS_NAMES:
        try:
            edit = win.EditControl(Name=nm, searchDepth=14)
            if not edit.Exists(0, 0):
                continue
            val = edit.GetValuePattern().Value
            url = _normalize_url(val or "")
            if url:
                return url
        except Exception:
            continue
    return ""


def read_browser_address_bar() -> str | None:
    """
    Return the best-effort https URL from a Chrome/Edge window, or None.

    Prefers the foreground browser window, then any top-level Chromium window
    whose omnibox looks like an http(s) URL.
    """
    if not browser_address_available():
        return None
    try:
        import uiautomation as auto
    except Exception:
        return None

    try:
        fg = auto.GetForegroundControl()
        # Walk up to a top-level window
        win = fg
        for _ in range(8):
            if win is None:
                break
            try:
                if (win.ClassName or "") == _BROWSER_CLASS:
                    url = _read_edit_url(win)
                    if url:
                        return url
                win = win.GetParentControl()
            except Exception:
                break

        root = auto.GetRootControl()
        for w in root.GetChildren():
            try:
                if (w.ClassName or "") != _BROWSER_CLASS:
                    continue
                url = _read_edit_url(w)
                if url:
                    return url
            except Exception:
                continue
    except Exception:
        return None
    return None
