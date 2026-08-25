"""Read Chrome / Edge omnibox (+ accessible UI text) via UI Automation.

Does **not** screenshot the page. Chrome often hides web-page DOM text from
accessibility; we still harvest window title / Document / Text / Button names
and cross-check them with the URL.

Optional dependency: ``uiautomation`` (soft-fail if missing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Visible PAT on GitHub "copy your token now" page (Name / Value via UIA)
_VISIBLE_PAT_RE = re.compile(
    r"\b(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
    re.IGNORECASE,
)

# Localized / English omnibox names observed on Windows Chrome/Edge
_ADDRESS_NAMES = (
    "주소창 및 검색창",
    "Address and search bar",
    "Address and search box",
    "Search or type a URL",
    "주소 표시줄 및 검색창",
)

_BROWSER_CLASS = "Chrome_WidgetWin_1"  # Chrome + Chromium Edge

_APPLE_HOSTS = frozenset(
    {
        "appleid.apple.com",
        "idmsa.apple.com",
        "appleid.cdn-apple.com",
    }
)

# Phrases from Google's insecure-browser interstitial (EN + KO)
_BLOCK_TEXT_NEEDLES = (
    "couldn't sign you in",
    "could not sign you in",
    "couldn’t sign you in",
    "may not be secure",
    "try using a different browser",
    "browser or app may not be secure",
    "this browser or app may not be secure",
    "지원되는 브라우저로 로그인",
    "안전한 브라우저가 아닐",
    "다른 브라우저를 사용",
    "브라우저나 앱이 안전하지",
    "로그인할 수 없음",
    "로그인하지 못했습니다",
)


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


def _ctrl_value(ctrl) -> str:
    """Best-effort ValuePattern / LegacyIAccessible value (PAT often here)."""
    try:
        vp = ctrl.GetValuePattern()
        if vp is not None:
            val = (getattr(vp, "Value", None) or "").strip()
            if val:
                return val
    except Exception:
        pass
    try:
        leg = ctrl.GetLegacyIAccessiblePattern()
        if leg is not None:
            val = (getattr(leg, "Value", None) or "").strip()
            if val:
                return val
    except Exception:
        pass
    return ""


def _harvest_ui_text(win, *, max_depth: int = 14, max_names: int = 120) -> str:
    """Collect accessible Name (+ Value) strings for cross-checks / PAT extract."""
    parts: list[str] = []

    def walk(ctrl, depth: int = 0) -> None:
        if depth > max_depth or len(parts) >= max_names:
            return
        try:
            name = (ctrl.Name or "").strip()
            ctype = ctrl.ControlTypeName or ""
            value = _ctrl_value(ctrl)
            # Always keep token-shaped strings (even odd control types)
            for candidate in (name, value):
                if candidate and _VISIBLE_PAT_RE.search(candidate):
                    parts.append(candidate)
            if name and len(name) > 1:
                # Prefer content-ish controls; still keep short button labels
                # that match Google's CTA ("Try using a different browser").
                if ctype in (
                    "TextControl",
                    "DocumentControl",
                    "HyperlinkControl",
                    "ButtonControl",
                    "GroupControl",
                    "AlertControl",
                    "StatusBarControl",
                    "ToolTipControl",
                    "EditControl",
                ):
                    parts.append(name)
                elif len(name) > 20:
                    parts.append(name)
            if value and value != name and len(value) > 1:
                if ctype in ("EditControl", "DocumentControl", "TextControl"):
                    parts.append(value)
                elif _VISIBLE_PAT_RE.search(value):
                    parts.append(value)
        except Exception:
            pass
        try:
            for ch in ctrl.GetChildren():
                walk(ch, depth + 1)
        except Exception:
            pass

    try:
        walk(win)
    except Exception:
        pass
    # De-dupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return "\n".join(out)


def extract_visible_pat(*texts: str) -> str | None:
    """
    If a classic/fine-grained PAT appears in accessible text, return it.

    Used on ``/settings/tokens`` right after Generate token (value shown once).
    """
    blob = "\n".join(t for t in texts if t)
    if not blob.strip():
        return None
    m = _VISIBLE_PAT_RE.search(blob)
    if not m:
        return None
    tok = m.group(1).strip()
    # Reject masked placeholders
    if set(tok) <= {"•", "*", "·", ".", " "}:
        return None
    if len(tok) < 24:
        return None
    return tok


def looks_like_token_issued_banner(
    window_title: str = "",
    ui_text: str = "",
) -> bool:
    """True if GitHub 'copy your personal access token now' banner is visible."""
    blob = f"{window_title or ''}\n{ui_text or ''}".lower()
    if "make sure to copy your personal access token now" in blob:
        return True
    if "copy your personal access token" in blob and "now" in blob:
        return True
    if "개인용 액세스 토큰을 지금 복사" in blob or "지금 복사해 두세요" in blob:
        return True
    return False


@dataclass
class BrowserPageSample:
    """One poll of a Chromium window."""

    url: str = ""
    window_title: str = ""
    ui_text: str = ""
    source: str = ""  # foreground | scan


@dataclass
class GoogleBlockAnalysis:
    """Cross-check result for Google insecure-browser / rejected sign-in."""

    blocked: bool
    url_hit: bool
    text_hit: bool
    title_hit: bool
    reasons: list[str] = field(default_factory=list)
    matched_snippets: list[str] = field(default_factory=list)


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _host_is_google_accounts(url: str) -> bool:
    host = _hostname(url)
    if not host:
        return "accounts.google.com" in (url or "").lower()
    return host == "accounts.google.com" or (
        host.endswith(".google.com") and host.startswith("accounts.")
    )


def is_apple_signin_url(url: str) -> bool:
    """True if URL is Apple ID sign-in (GitHub 「Apple로 계속하기」)."""
    host = _hostname(url)
    if host in _APPLE_HOSTS:
        return True
    u = (url or "").lower()
    return "appleid.apple.com" in u or "idmsa.apple.com" in u


def is_github_flow_family_url(
    url: str,
    *,
    window_title: str = "",
    ui_text: str = "",
) -> bool:
    """
    True if the page belongs to the GitHub connect flow "family".

    Family (parent) hosts: github.com, Google accounts sign-in, Apple ID.
    Also Windows Security passkey sheet (often no useful omnibox URL).
    """
    if looks_like_passkey_os_prompt(window_title, ui_text):
        return True
    u = (url or "").strip()
    if not u:
        return False
    host = _hostname(u)
    if host == "github.com" or host.endswith(".github.com"):
        return True
    if _host_is_google_accounts(u):
        return True
    if is_apple_signin_url(u):
        return True
    return False


def looks_like_passkey_os_prompt(window_title: str, ui_text: str = "") -> bool:
    """True if foreground looks like Windows Security passkey sheet."""
    blob = f"{window_title or ''}\n{ui_text or ''}".lower()
    if not blob.strip():
        return False
    win_sec = (
        "windows 보안" in blob
        or "windows security" in blob
        or "windows hello" in blob
    )
    passkey = (
        "패스키" in blob
        or "passkey" in blob
        or "보안 키" in blob
        or "security key" in blob
        or "qr 코드" in blob
        or "qr code" in blob
    )
    return win_sec and passkey


# Logged-out GitHub marketing/home exposes these via UI Automation
_GITHUB_LOGGED_OUT_UI_NEEDLES = (
    "sign up for github",
    "sign in to github",
    "sign in\nto github",
    "github에 가입",
    "github에 로그인",
    "sign up",  # paired with github context below
)


def looks_like_github_logged_out_ui(
    window_title: str = "",
    ui_text: str = "",
    *,
    url: str = "",
) -> bool:
    """
    True if accessible UI shows Sign in / Sign up (user is logged out).

    ``github.com`` alone is ambiguous — logged-in dashboard and logged-out
    marketing home share that URL. Cross-check visible Sign in/Sign up.
    """
    blob = f"{window_title or ''}\n{ui_text or ''}".lower()
    blob = blob.replace("\xa0", " ").replace("\u00a0", " ")
    if not blob.strip():
        return False
    # Strong phrases first
    strong = (
        "sign up for github",
        "sign in to github",
        "github에 가입",
        "github에 로그인",
    )
    if any(s in blob for s in strong):
        return True
    # Weaker: both Sign in and Sign up appear near GitHub chrome
    has_sign_in = "sign in" in blob or "로그인" in blob
    has_sign_up = "sign up" in blob or "가입" in blob
    on_github = "github" in blob or "github.com" in (url or "").lower()
    if on_github and has_sign_in and has_sign_up:
        return True
    return False


# GitHub classic PAT form flash errors (UIA Name harvest)
_TOKEN_NOTE_TAKEN_NEEDLES = (
    "note has already been taken",
    "note already been taken",
    "has already been taken",
)


def looks_like_token_note_taken(
    window_title: str = "",
    ui_text: str = "",
    *,
    url: str = "",
) -> bool:
    """
    True if PAT create form shows Note-name collision flash.

    Screenshot/UIA: ``Validation failed: Note has already been taken``
    (common when ``description=CloneUp`` is reused across attempts).
    """
    blob = f"{window_title or ''}\n{ui_text or ''}".lower()
    blob = blob.replace("\xa0", " ").replace("\u00a0", " ")
    if not blob.strip():
        return False
    if "note has already been taken" in blob:
        return True
    if "has already been taken" in blob and (
        "note" in blob or "validation failed" in blob
    ):
        return True
    # On token settings pages, bare "already been taken" is still strong
    path_hint = (url or "").lower()
    on_token_page = "settings/tokens" in path_hint or "personal-access-token" in path_hint
    if on_token_page and any(n in blob for n in _TOKEN_NOTE_TAKEN_NEEDLES):
        return True
    return False


def token_create_error_snippets(
    window_title: str = "",
    ui_text: str = "",
) -> list[str]:
    """Return matched flash/error lines for verify UI (order preserved)."""
    blob = f"{window_title or ''}\n{ui_text or ''}"
    lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
    out: list[str] = []
    for ln in lines:
        low = ln.lower()
        if (
            "already been taken" in low
            or "validation failed" in low
            or (low.startswith("note ") and "taken" in low)
        ):
            if ln not in out:
                out.append(ln)
    return out[:5]


def detect_signin_method(
    url: str,
    *,
    window_title: str = "",
    ui_text: str = "",
) -> str:
    """
    Which sign-in path the user appears to be on.

    Returns one of: ``google_blocked``, ``google``, ``apple``, ``passkey``,
    ``github_login``, ``github_logout``, ``github_logged_out``, ``github``,
    ``other``.
    """
    analysis = analyze_google_signin_block(
        url, window_title=window_title, ui_text=ui_text
    )
    if analysis.blocked:
        return "google_blocked"
    if looks_like_passkey_os_prompt(window_title, ui_text):
        return "passkey"
    if is_apple_signin_url(url):
        return "apple"
    if _host_is_google_accounts(url):
        return "google"
    host = _hostname(url)
    if host == "github.com" or host.endswith(".github.com"):
        path = ""
        try:
            path = (urlparse(url).path or "").lower()
        except Exception:
            pass
        if path == "/logout" or path.startswith("/logout"):
            return "github_logout"
        if path.startswith("/login") or path.startswith("/sessions/"):
            return "github_login"
        # Same URL ``github.com`` when logged out vs in — use Sign in/up UI
        if looks_like_github_logged_out_ui(
            window_title, ui_text, url=url
        ):
            return "github_logged_out"
        return "github"
    return "other"


def _url_has_signin_rejected(url: str) -> bool:
    raw = (url or "").strip().lower()
    if not raw or not _host_is_google_accounts(raw):
        return False
    try:
        path = (urlparse(raw).path or "").lower()
        query = (urlparse(raw).query or "").lower()
    except Exception:
        path, query = raw, raw
    if "/signin/rejected" in path or path.endswith("/rejected"):
        return True
    if "rejected" in path and "signin" in path:
        return True
    if "flowname=glifwebsignin" in query and "rejected" in raw:
        return True
    return False


def analyze_google_signin_block(
    url: str,
    *,
    window_title: str = "",
    ui_text: str = "",
) -> GoogleBlockAnalysis:
    """
    Cross-verify Google sign-in failure from URL + accessible text.

    URL path ``/signin/rejected`` is the strongest signal when Chrome hides
    page DOM from UI Automation. Text/title hits raise confidence when present.
    """
    reasons: list[str] = []
    snippets: list[str] = []
    url_hit = _url_has_signin_rejected(url)
    if url_hit:
        reasons.append("URL에 signin/rejected 확인")

    title = window_title or ""
    body = ui_text or ""
    blob = f"{title}\n{body}".lower()
    text_hit = False
    title_hit = False
    for needle in _BLOCK_TEXT_NEEDLES:
        if needle in title.lower():
            title_hit = True
            text_hit = True
            reasons.append(f"창 제목 일치: {needle}")
            snippets.append(title[:80])
            break
    if not text_hit:
        for needle in _BLOCK_TEXT_NEEDLES:
            if needle in blob:
                text_hit = True
                reasons.append(f"UI 텍스트 일치: {needle}")
                for line in body.splitlines():
                    if needle in line.lower():
                        snippets.append(line.strip()[:100])
                        break
                if not snippets and title:
                    snippets.append(title[:80])
                break

    on_google = _host_is_google_accounts(url)
    # Prefer requiring Google context for text-only hits (avoid false positives)
    blocked = bool(url_hit or (on_google and text_hit))
    if blocked and not reasons:
        reasons.append("Google 차단 감지")
    if on_google and not blocked:
        reasons.append("Google 주소 · 거절 URL/차단 문구 없음 (진행 중)")
    if on_google and url_hit and not text_hit:
        reasons.append(
            "본문 텍스트는 접근성으로 안 읽힘 — URL 교차검증만으로 거절 확정"
        )

    return GoogleBlockAnalysis(
        blocked=blocked,
        url_hit=url_hit,
        text_hit=text_hit,
        title_hit=title_hit,
        reasons=reasons,
        matched_snippets=snippets[:3],
    )


def read_browser_page_sample() -> BrowserPageSample | None:
    """
    Best-effort sample: omnibox URL + window title + accessible UI names.

    Prefers foreground Chromium, then Apple/Google/GitHub tabs, then any
    Chromium window. Also samples a foreground Windows Security sheet
    (passkey) which has no omnibox.
    """
    if not browser_address_available():
        return None
    try:
        import uiautomation as auto
    except Exception:
        return None

    def _sample_win(win, source: str, *, need_url: bool = False) -> BrowserPageSample | None:
        try:
            url = _read_edit_url(win) if (win.ClassName or "") == _BROWSER_CLASS else ""
            title = (win.Name or "").strip()
            ui_text = _harvest_ui_text(win)
            if need_url and not url:
                return None
            if not url and not title and not ui_text:
                return None
            return BrowserPageSample(
                url=url or "",
                window_title=title,
                ui_text=ui_text,
                source=source,
            )
        except Exception:
            return None

    try:
        fg = auto.GetForegroundControl()
        win = fg
        top = None
        for _ in range(10):
            if win is None:
                break
            top = win
            try:
                parent = win.GetParentControl()
            except Exception:
                parent = None
            if parent is None:
                break
            win = parent

        if top is not None:
            title = (top.Name or "").strip()
            ui_text = _harvest_ui_text(top)
            if looks_like_passkey_os_prompt(title, ui_text):
                return BrowserPageSample(
                    url="",
                    window_title=title,
                    ui_text=ui_text,
                    source="foreground-os",
                )
            if (top.ClassName or "") == _BROWSER_CLASS:
                sample = _sample_win(top, "foreground")
                if sample and (sample.url or sample.window_title):
                    return sample

        # Prefer sign-in related tabs (Google / Apple / GitHub)
        root = auto.GetRootControl()
        fallback: BrowserPageSample | None = None
        for w in root.GetChildren():
            try:
                if (w.ClassName or "") != _BROWSER_CLASS:
                    continue
                sample = _sample_win(w, "scan")
                if sample is None:
                    continue
                u = (sample.url or "").lower()
                if (
                    "accounts.google.com" in u
                    or "appleid.apple.com" in u
                    or "idmsa.apple.com" in u
                    or "github.com" in u
                ):
                    return sample
                if fallback is None and sample.url:
                    fallback = sample
            except Exception:
                continue
        return fallback
    except Exception:
        return None


def read_browser_address_bar() -> str | None:
    """Return https URL from Chrome/Edge omnibox, or None."""
    sample = read_browser_page_sample()
    if sample is None:
        return None
    return sample.url or None
