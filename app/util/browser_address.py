"""Read Chrome / Edge omnibox (+ accessible UI text) via UI Automation.

Does **not** screenshot the page. Chrome often hides web-page DOM text from
accessibility; we still harvest window title / Document / Text / Button names
and cross-check them with the URL.

Optional dependency: ``uiautomation`` (soft-fail if missing).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Optional sink → main window textLog (Path B). See docs/DEV_LOGGING_GUIDE.md.
_path_b_log_sink: Callable[[str], None] | None = None

# Visible PAT on GitHub "copy your token now" page (Name / Value via UIA)
_VISIBLE_PAT_RE = re.compile(
    r"\b(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
    re.IGNORECASE,
)


def set_path_b_log_sink(sink: Callable[[str], None] | None) -> None:
    """Attach/detach Path B logs to the app log window (tee with print)."""
    global _path_b_log_sink
    _path_b_log_sink = sink


def path_b_log(message: str) -> None:
    """
    Logging-first line for Path B browser assist.

    Always prints (terminal / redirected worker sinks) after secret masking.
    If :func:`set_path_b_log_sink` was set (ExternalBrowserPatGuide), also
    forwards to the main ``textLog``.
    """
    from app.util.log_mask import mask_secrets_in_text

    line = mask_secrets_in_text(message or "")
    if not line.strip():
        return
    try:
        print(line)
    except Exception:
        pass
    sink = _path_b_log_sink
    if sink is not None:
        try:
            sink(line)
        except Exception:
            pass


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
    """
    True if foreground looks like Windows Security passkey sheet.

    Screenshot (ko): title 「Windows 보안」, heading 「패스키로 로그인」,
    options 「iPhone, iPad 또는 Android…」(QR) / 「이 디바이스」.
    Also PIN confirm: 「이 디바이스에서 로그인하시겠습니까?」.
    """
    blob = f"{window_title or ''}\n{ui_text or ''}".lower()
    if not blob.strip():
        return False
    win_sec = (
        "windows 보안" in blob
        or "windows security" in blob
        or "windows hello" in blob
    )
    passkey = (
        "패스키로 로그인" in blob
        or "패스키" in blob
        or "passkey" in blob
        or "보안 키" in blob
        or "security key" in blob
        or "qr 코드" in blob
        or "qr code" in blob
        or "이 디바이스" in blob
        or "this device" in blob
        or "로그인하시겠습니까" in blob
        or "sign in on this device" in blob
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

# Logged-in dashboard / feed signals (override weak Sign in/up noise)
_GITHUB_LOGGED_IN_UI_NEEDLES = (
    "for you",
    "dashboard",
    "your repositories",
    "your teams",
    "your profile",
    "signed in as",
    "홈",
    "대시보드",
    "알림",
    "notifications",
    "create repository",
    "new repository",
    "repositories",
)


def looks_like_github_logged_in_ui(
    window_title: str = "",
    ui_text: str = "",
) -> bool:
    """True if accessible UI looks like a logged-in GitHub dashboard/feed."""
    blob = f"{window_title or ''}\n{ui_text or ''}".lower()
    blob = blob.replace("\xa0", " ").replace("\u00a0", " ")
    if not blob.strip():
        return False
    return any(n in blob for n in _GITHUB_LOGGED_IN_UI_NEEDLES)


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
    Dashboard signals win over weak Sign in/up noise in the a11y tree.
    """
    blob = f"{window_title or ''}\n{ui_text or ''}".lower()
    blob = blob.replace("\xa0", " ").replace("\u00a0", " ")
    if not blob.strip():
        return False
    # Logged-in dashboard must not be treated as logged-out
    if looks_like_github_logged_in_ui(window_title, ui_text):
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
    ``github_2fa``, ``github_login``, ``github_logout``, ``github_logged_out``,
    ``github``, ``other``.
    """
    analysis = analyze_google_signin_block(
        url, window_title=window_title, ui_text=ui_text
    )
    if analysis.blocked:
        return "google_blocked"
    if looks_like_passkey_os_prompt(window_title, ui_text):
        return "passkey"
    # Omnibox may be empty while StayOnTop guide is up — title/UIA/OCR still work.
    try:
        from app.util.auth_ocr import (
            looks_like_device_email_verify,
            looks_like_github_sudo_passkey,
        )

        if looks_like_github_sudo_passkey(window_title, ui_text):
            return "passkey"
        if looks_like_device_email_verify(window_title, ui_text):
            return "github_2fa"
    except Exception:
        pass
    early_blob = f"{window_title or ''}\n{ui_text or ''}".lower()
    if "verify your device" in early_blob or (
        "verification code" in early_blob
        and ("email" in early_blob or "we just sent" in early_blob)
    ):
        return "github_2fa"
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
        # Device / email verification (before treating /sessions as plain login).
        blob = f"{window_title or ''}\n{ui_text or ''}".lower()
        if (
            "verify your device" in blob
            or "device verification" in blob
            or (
                "verification code" in blob
                and ("email" in blob or "we just sent" in blob)
            )
            or (
                "authentication code" in blob
                and ("email" in blob or "we just sent" in blob)
            )
            or ("verify with a passkey" in blob and "verification" in blob)
            or "/sessions/verified-device" in path
            or "/sessions/two-factor" in path
            or "/sessions/email-verification" in path
        ):
            return "github_2fa"
        # Confirm access + Use passkey can share tokens/new URL — still auth.
        if "confirm access" in blob and (
            "passkey" in blob or "use passkey" in blob
        ):
            return "passkey"
        if path.startswith("/login") or path.startswith("/sessions/"):
            return "github_login"
        # Same URL ``github.com`` when logged out vs in — use Sign in/up UI
        if looks_like_github_logged_out_ui(
            window_title, ui_text, url=url
        ):
            return "github_logged_out"
        # Title-only: Verify your device · GitHub (omnibox may lag)
        title_l = (window_title or "").lower()
        if "verify your device" in title_l or "device verification" in title_l:
            return "github_2fa"
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


# Chromium-family image names for tasklist / PID scoping (Windows).
_CHROMIUM_IMAGE_NAMES: tuple[str, ...] = (
    "chrome.exe",
    "msedge.exe",
    "brave.exe",
    "chromium.exe",
    "opera.exe",
    "vivaldi.exe",
)
_CHROMIUM_IMAGE_SET = frozenset(n.lower() for n in _CHROMIUM_IMAGE_NAMES)

# Path B polls every ~3s — spawning 6× tasklist froze the UI (~12s). Cache.
_PID_CACHE: tuple[float, frozenset[int]] | None = None
_PID_CACHE_TTL_S = 5.0


def list_chromium_browser_pids(*, force: bool = False) -> set[int]:
    """
    Collect PIDs for Chrome / Edge / Brave / … via ``tasklist`` (no window flash).

    Chrome is multi-process — callers should treat the set as \"any PID that
    belongs to a Chromium-family browser\", then match top-level UIA windows
    whose ``ProcessId`` is in this set.

    Results are cached for a few seconds so Path B address polls stay snappy.
    """
    import sys
    import time

    if sys.platform != "win32":
        return set()
    global _PID_CACHE
    now = time.monotonic()
    if not force and _PID_CACHE is not None:
        ts, cached = _PID_CACHE
        if now - ts < _PID_CACHE_TTL_S:
            return set(cached)

    pids = _list_chromium_browser_pids_uncached()
    _PID_CACHE = (now, frozenset(pids))
    return pids


def _list_chromium_browser_pids_uncached() -> set[int]:
    """One ``tasklist`` pass filtered to Chromium image names."""
    import csv
    import io
    import subprocess

    try:
        from app.util.winproc import run_hidden
    except Exception:
        run_hidden = None  # type: ignore[assignment]

    cmd = ["tasklist", "/FO", "CSV", "/NH"]
    try:
        if run_hidden is not None:
            proc = run_hidden(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
            )
        else:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
            )
        raw = proc.stdout or ""
    except Exception:
        return set()

    if not (raw or "").strip() or not raw.lstrip().startswith('"'):
        return set()
    out: set[int] = set()
    try:
        for row in csv.reader(io.StringIO(raw)):
            if len(row) < 2:
                continue
            image = str(row[0]).strip().strip('"').lower()
            if image not in _CHROMIUM_IMAGE_SET:
                continue
            try:
                out.add(int(str(row[1]).strip().strip('"')))
            except ValueError:
                continue
    except Exception:
        return out
    return out


def parse_tasklist_csv_pids(raw: str) -> set[int]:
    """Parse ``tasklist /FO CSV /NH`` stdout into a set of PIDs."""
    import csv
    import io

    if not (raw or "").strip() or not raw.lstrip().startswith('"'):
        return set()
    out: set[int] = set()
    try:
        for row in csv.reader(io.StringIO(raw)):
            if len(row) < 2:
                continue
            try:
                out.add(int(str(row[1]).strip().strip('"')))
            except ValueError:
                continue
    except Exception:
        return out
    return out


def _window_process_id(win) -> int | None:
    try:
        pid = getattr(win, "ProcessId", None)
        if pid is None:
            return None
        return int(pid)
    except Exception:
        return None


def _window_hwnd(win) -> int:
    try:
        return int(getattr(win, "NativeWindowHandle", 0) or 0)
    except Exception:
        return 0


def _foreground_hwnd() -> int:
    """Current foreground HWND (0 if unavailable)."""
    import sys

    if sys.platform != "win32":
        return 0
    try:
        import ctypes

        return int(ctypes.windll.user32.GetForegroundWindow() or 0)
    except Exception:
        return 0


def window_title_connect_score(title: str) -> int:
    """
    Pure score: how likely ``title`` is our GitHub PAT / connect flow tab.

    Window titles reflect the *active* tab (e.g. \"New Personal Access Token
    (Classic) - Chrome\"). Tab last-access timestamps are not available via
    UIA — title match is the strongest content clue.
    """
    name = (title or "").strip().lower()
    if not name:
        return 0
    score = 0
    # Strongest: classic PAT create page title observed on Chrome/Edge.
    if "new personal access token" in name:
        score += 50
    elif "personal access token" in name:
        score += 28
    if "github" in name:
        score += 20
    if "token" in name:
        score += 10
    if "settings" in name:
        score += 4
    # Login / auth related (Path B early scenes).
    if "sign in" in name or "로그인" in name:
        score += 6
    return score


def chromium_window_rank_tuple(
    *,
    title: str,
    is_foreground: bool,
    z_index: int,
) -> tuple[int, int, int, int]:
    """
    Sort key for Chromium windows (higher = better / try first).

    Per-tab last-access timestamps are not available on Windows. For Path B
    connect assist we approximate \"the right recent tab\" as:

    1. Strong PAT / connect title (active tab name on the window)
    2. Foreground browser window (recent focus among peers)
    3. Remaining title score
    4. Earlier among top-level siblings (``z_index`` 0 = first under root —
       treated as closer to front when walking UI Automation children)

    Strong title beats an unrelated foreground tab so a StayOnTop CloneUp
    guide (or a Google search in front) does not steal Expiration clicks.
    """
    title_score = window_title_connect_score(title)
    strong = 1 if title_score >= 28 else 0
    return (
        strong,
        1 if is_foreground else 0,
        title_score,
        -int(z_index),
    )


def _window_github_score(win) -> int:
    """Higher = more likely the GitHub tokens/new tab we care about."""
    try:
        name = win.Name or ""
    except Exception:
        name = ""
    return window_title_connect_score(name)


def _iter_chromium_windows(auto, *, pids: set[int] | None = None) -> list:
    """Top-level ``Chrome_WidgetWin_1`` windows, optionally filtered by PID set.

    When ``pids`` is None, loads current Chromium-family PIDs from tasklist and
    filters to those. Pass an empty set to skip PID filtering (all Chromium
    class windows).

    Sorted by :func:`chromium_window_rank_tuple` — strong PAT/connect title,
    then foreground, then remaining title score, then Z-order proxy (sibling
    index). Tab wall-clock times are not available on Windows; this is the
    practical \"most relevant / recent\" order for Path B assist.
    """
    out: list = []
    pid_filter = pids
    if pid_filter is None:
        pid_filter = list_chromium_browser_pids()
    fg_hwnd = _foreground_hwnd()
    try:
        root = auto.GetRootControl()
        z_index = 0
        for w in root.GetChildren():
            try:
                if (w.ClassName or "") != _BROWSER_CLASS:
                    continue
                if pid_filter:
                    wpid = _window_process_id(w)
                    if wpid is None or wpid not in pid_filter:
                        continue
                # Annotate for stable ranking without a parallel meta list.
                try:
                    w._cloneup_z_index = z_index  # type: ignore[attr-defined]
                    w._cloneup_is_fg = bool(  # type: ignore[attr-defined]
                        fg_hwnd and _window_hwnd(w) == fg_hwnd
                    )
                except Exception:
                    pass
                out.append(w)
                z_index += 1
            except Exception:
                continue
    except Exception:
        pass

    def _rank_key(win) -> tuple[int, int, int, int]:
        try:
            title = win.Name or ""
        except Exception:
            title = ""
        is_fg = bool(getattr(win, "_cloneup_is_fg", False))
        if not is_fg and fg_hwnd:
            is_fg = bool(_window_hwnd(win) == fg_hwnd)
        z = int(getattr(win, "_cloneup_z_index", 9999))
        return chromium_window_rank_tuple(
            title=title, is_foreground=is_fg, z_index=z
        )

    out.sort(key=_rank_key, reverse=True)
    return out


def _ctrl_clickable_point(ctrl) -> tuple[int, int] | None:
    """Center of BoundingRectangle, or GetClickablePoint if available."""
    try:
        if hasattr(ctrl, "GetClickablePoint"):
            pt = ctrl.GetClickablePoint()
            if pt is not None:
                # uiautomation may return (x, y) or a Point-like object
                if isinstance(pt, (tuple, list)) and len(pt) >= 2:
                    return int(pt[0]), int(pt[1])
                x = getattr(pt, "x", None)
                y = getattr(pt, "y", None)
                if x is not None and y is not None:
                    return int(x), int(y)
    except Exception:
        pass
    try:
        rect = ctrl.BoundingRectangle
        left = int(getattr(rect, "left", getattr(rect, "Left", 0)))
        top = int(getattr(rect, "top", getattr(rect, "Top", 0)))
        right = int(getattr(rect, "right", getattr(rect, "Right", 0)))
        bottom = int(getattr(rect, "bottom", getattr(rect, "Bottom", 0)))
        if right - left < 2 or bottom - top < 2:
            return None
        return (left + right) // 2, (top + bottom) // 2
    except Exception:
        return None


def _bring_uia_window_forward(win) -> bool:
    """Briefly foreground a browser HWND so coordinate clicks land.

    Does not close or minimize other apps; only SetForegroundWindow / restore.
    """
    import sys

    if sys.platform != "win32" or win is None:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = int(getattr(win, "NativeWindowHandle", 0) or 0)
        if not hwnd:
            return False
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        foreground = user32.GetForegroundWindow()
        if foreground == hwnd:
            return True
        fg_tid = user32.GetWindowThreadProcessId(foreground, None)
        our_tid = kernel32.GetCurrentThreadId()
        attached = False
        if fg_tid and our_tid and fg_tid != our_tid:
            attached = bool(user32.AttachThreadInput(fg_tid, our_tid, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(fg_tid, our_tid, False)
        return True
    except Exception:
        return False


def _uia_click_at_control(
    ctrl,
    *,
    owner_window=None,
    restore_cursor: bool = True,
) -> tuple[bool, str]:
    """
    Left-click the control's screen point (PID-scoped Path B assist).

    Moves the real cursor briefly, then restores it. Prefer Invoke when it
    works; use this when Primer menus ignore Invoke on a background window.
    Never sends close / Alt+F4.
    """
    import sys
    import time

    name = ""
    try:
        name = (ctrl.Name or "").strip()
    except Exception:
        pass
    point = _ctrl_clickable_point(ctrl)
    if point is None:
        return False, f"no-point:{name[:32]}"
    x, y = point
    if sys.platform != "win32":
        return False, "click-non-windows"

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        if owner_window is not None:
            _bring_uia_window_forward(owner_window)

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        old = POINT()
        user32.GetCursorPos(ctypes.byref(old))
        try:
            user32.SetCursorPos(int(x), int(y))
            time.sleep(0.04)
            # MOUSEEVENTF_LEFTDOWN / LEFTUP
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.03)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
        finally:
            if restore_cursor:
                try:
                    user32.SetCursorPos(old.x, old.y)
                except Exception:
                    pass
        return True, f"click:{name[:40]}@{x},{y}"
    except Exception as e:
        return False, f"click-fail:{e}"


def _uia_invoke_only(ctrl) -> tuple[bool, str]:
    """Invoke / ExpandCollapse — no mouse, no SetFocus."""
    name = ""
    try:
        name = (ctrl.Name or "").strip()
    except Exception:
        pass
    # Prefer InvokePattern (buttons / menuitemradio).
    try:
        if hasattr(ctrl, "GetInvokePattern"):
            pat = ctrl.GetInvokePattern()
            if pat is not None:
                pat.Invoke()
                return True, f"invoke:{name[:48]}"
    except Exception as e:
        invoke_err = f"invoke-fail:{e}"
    else:
        invoke_err = ""
    # Primer action-menu openers sometimes expose ExpandCollapse instead.
    try:
        if hasattr(ctrl, "GetExpandCollapsePattern"):
            pat = ctrl.GetExpandCollapsePattern()
            if pat is not None:
                # Expand if collapsed; ignore state read errors.
                try:
                    state = getattr(pat, "ExpandCollapseState", None)
                    # 0=Collapsed, 1=Expanded (uiautomation enum values)
                    if state is None or int(state) == 0:
                        pat.Expand()
                    else:
                        # Already open — still counts as success for opener.
                        pass
                except Exception:
                    pat.Expand()
                return True, f"expand:{name[:48]}"
    except Exception as e:
        expand_err = f"expand-fail:{e}"
    else:
        expand_err = ""
    detail = "|".join(x for x in (invoke_err, expand_err) if x) or "no-invoke"
    return False, detail


def _uia_activate(ctrl, *, allow_click: bool, owner_window=None) -> tuple[bool, str]:
    """Try Invoke first; optional coordinate click fallback (cursor restored)."""
    ok, detail = _uia_invoke_only(ctrl)
    if ok:
        return True, detail
    if not allow_click:
        return False, detail
    ok2, detail2 = _uia_click_at_control(ctrl, owner_window=owner_window)
    if ok2:
        return True, f"{detail}|{detail2}"
    return False, f"{detail}|{detail2}"


def _collect_named_controls(ctrl, out: list, *, depth: int, max_depth: int = 14) -> None:
    if depth > max_depth or ctrl is None:
        return
    try:
        ctype = (ctrl.ControlTypeName or "") if hasattr(ctrl, "ControlTypeName") else ""
        name = (ctrl.Name or "").strip()
        if name and (
            "Button" in ctype
            or "Hyperlink" in ctype
            or "MenuItem" in ctype
            or "ListItem" in ctype
            or "ComboBox" in ctype
        ):
            out.append((name, ctype, ctrl))
        for ch in ctrl.GetChildren():
            _collect_named_controls(ch, out, depth=depth + 1, max_depth=max_depth)
    except Exception:
        return


def try_invoke_generate_token_button(*, allow_click: bool = True) -> tuple[bool, str]:
    """
    Best-effort activate GitHub 「Generate token」 in a Chromium-PID window.

    Used by Path B 「버튼이 안 보여요」 / auto-assist. Tries Invoke first, then
    optional coordinate click (cursor restored) inside the PID-scoped window.
    Soft-fails without uiautomation or when the control is not exposed.

    Returns ``(ok, detail)``.
    """
    if not browser_address_available():
        path_b_log("[Path B] Generate: uiautomation 없음")
        return False, "uiautomation-missing"
    try:
        import uiautomation as auto
    except Exception as e:
        path_b_log(f"[Path B] Generate: import 실패 ({e})")
        return False, f"import:{e}"

    def _match_generate(name: str) -> bool:
        low = (name or "").strip().lower()
        if not low:
            return False
        if low == "generate token":
            return True
        return (
            ("generate token" in low or "토큰 생성" in low)
            and "new personal" not in low
            and "generate new token" not in low
        )

    try:
        pids = list_chromium_browser_pids()
        path_b_log(
            f"[Path B] Generate 시도 (click={'on' if allow_click else 'off'}, "
            f"browser_pids={len(pids)})"
        )
        # Ranked: strong PAT title → foreground → Z-order proxy.
        for w in _iter_chromium_windows(auto, pids=pids or None):
            found: list = []
            try:
                for ctrl in w.GetChildren():
                    _collect_named_controls(ctrl, found, depth=0)
            except Exception:
                continue
            for name, _ctype, ctrl in found:
                if not _match_generate(name):
                    continue
                ok, detail = _uia_activate(
                    ctrl, allow_click=allow_click, owner_window=w
                )
                if ok:
                    title = ""
                    try:
                        title = (w.Name or "")[:48]
                    except Exception:
                        pass
                    msg = f"{detail}|win={title}"
                    path_b_log(f"[Path B] Generate 성공: {msg}")
                    return True, msg
        fail = f"generate-not-found|pids={len(pids)}"
        path_b_log(f"[Path B] Generate 실패: {fail}")
        return False, fail
    except Exception as e:
        path_b_log(f"[Path B] Generate 오류: {e}")
        return False, f"scan:{e}"


def uia_name_is_expiration_opener(name: str) -> bool:
    """True if accessible Name looks like the Expiration dropdown button."""
    low = (name or "").strip().lower()
    if not low or len(low) > 80:
        return False
    if "generate" in low:
        return False
    if "no expiration" in low or "만료 없음" in low:
        return True
    if re.search(r"\b\d{1,3}\s*days?\b", low):
        return True
    if low == "expiration" or low.startswith("expiration"):
        return True
    return False


def uia_name_matches_expiration_option(name: str, days_value: str) -> bool:
    """True if Name is the menu option for ``days_value`` (7/30/60/90/none)."""
    want = (days_value or "90").strip().lower()
    if want in ("", "no-expiration", "never"):
        want = "none"
    low = (name or "").strip().lower()
    if not low or len(low) > 80:
        return False
    if want == "none":
        return "no expiration" in low or "만료 없음" in low or low == "none"
    if re.match(rf"^{want}\s*days?\b", low):
        return True
    if re.search(rf"(^|\b){want}\s*days?\b", low) and "custom" not in low:
        return True
    return False


def _control_looks_selected(ctrl) -> bool:
    """Best-effort selected/checked state for menu options."""
    try:
        sp = ctrl.GetSelectionItemPattern()
        if sp is not None and bool(getattr(sp, "IsSelected", False)):
            return True
    except Exception:
        pass
    try:
        tp = ctrl.GetTogglePattern()
        if tp is not None:
            # 1 == On (ToggleState_On)
            if int(getattr(tp, "ToggleState", 0) or 0) == 1:
                return True
    except Exception:
        pass
    try:
        leg = ctrl.GetLegacyIAccessiblePattern()
        if leg is not None:
            state = int(getattr(leg, "State", 0) or 0)
            # STATE_SYSTEM_SELECTED (0x2) | STATE_SYSTEM_CHECKED (0x10)
            if state & 0x12:
                return True
    except Exception:
        pass
    return False


def read_token_expiration_uia() -> tuple[str | None, str]:
    """
    Read-only: best-effort Expiration value from Chromium a11y tree.

    Returns ``(days_value_or_none_token, detail)``. ``days_value`` is
    ``\"7\"|\"30\"|\"60\"|\"90\"|\"none\"`` or ``YYYY-MM-DD`` when parsed,
    else ``None``.

    GitHub classic often exposes the closed dropdown Name as bare
    ``\"Expiration\"`` (no days). In that case we also check ValuePattern,
    selected menu options (open list), and other day-like Names.
    Does not Invoke, Click, or SetFocus.
    """
    if not browser_address_available():
        return None, "uiautomation-missing"
    try:
        import uiautomation as auto
    except Exception as e:
        return None, f"import:{e}"

    try:
        pids = list_chromium_browser_pids()
        last_detail = f"expiry-opener-not-found|pids={len(pids)}"
        for w in _iter_chromium_windows(auto, pids=pids or None):
            all_ctrls: list = []
            try:
                for ctrl in w.GetChildren():
                    _collect_named_controls(ctrl, all_ctrls, depth=0)
            except Exception:
                continue
            title = ""
            try:
                title = (w.Name or "")[:40]
            except Exception:
                pass

            openers = [
                (n, c) for n, _t, c in all_ctrls if uia_name_is_expiration_opener(n)
            ]
            # Day-like option names (open menu: "30 days", "No expiration", …)
            day_opts: list[tuple[str, str, object]] = []
            for n, _t, c in all_ctrls:
                parsed_n = _parse_expiration_opener_days(n)
                if parsed_n is None:
                    continue
                # Skip bare label-only if somehow parsed; keep real options.
                if (n or "").strip().lower() in ("expiration",):
                    continue
                day_opts.append((parsed_n, n, c))

            # 1) Opener Name already includes the selection ("30 days", …)
            scored: list[tuple[int, str, str]] = []
            for n, c in openers:
                p = _parse_expiration_opener_days(n)
                if p is None:
                    continue
                score = 0
                if re.search(r"\b\d{1,3}\s*days?\b", n, re.I):
                    score += 2
                if "no expiration" in n.lower() or "만료" in n:
                    score += 1
                scored.append((score, p, n))
            if scored:
                scored.sort(key=lambda t: (-t[0], len(t[2])))
                _sc, parsed, name = scored[0]
                return (
                    parsed,
                    f"opener:{name[:64]}|win={title}|pids={len(pids)}",
                )

            # 2) ValuePattern / Legacy value on bare "Expiration" button
            for n, c in openers:
                if "expiration" not in (n or "").lower():
                    continue
                val = _ctrl_value(c)
                p = _parse_expiration_opener_days(val) if val else None
                if p is None and val:
                    p = _parse_expiration_opener_days(f"{val} days")
                if p is not None:
                    return (
                        p,
                        f"opener-value:{val[:40]}|name:{n[:24]}|win={title}|pids={len(pids)}",
                    )
                # Nested text under the action-menu button (closed state).
                try:
                    for ch in c.GetChildren():
                        cn = (getattr(ch, "Name", None) or "").strip()
                        if not cn:
                            continue
                        p2 = _parse_expiration_opener_days(cn)
                        if p2 is not None:
                            return (
                                p2,
                                f"opener-child:{cn[:40]}|win={title}|pids={len(pids)}",
                            )
                except Exception:
                    pass

            # 3) Open menu: prefer selected / checked day option
            selected = [
                (p, n) for p, n, c in day_opts if _control_looks_selected(c)
            ]
            if selected:
                parsed, name = selected[0]
                return (
                    parsed,
                    f"menu-selected:{name[:64]}|win={title}|pids={len(pids)}",
                )

            # 3b) Focused menu row (keyboard / hover highlight often tracks focus)
            if openers and day_opts:
                try:
                    fg = auto.GetFocusedControl()
                    fn = (getattr(fg, "Name", None) or "").strip()
                    p_fg = _parse_expiration_opener_days(fn)
                    if p_fg is not None and any(p_fg == p for p, _n, _c in day_opts):
                        return (
                            p_fg,
                            f"menu-focused:{fn[:64]}|win={title}|pids={len(pids)}",
                        )
                except Exception:
                    pass

            # 4) Open menu with a single concrete day option visible near Expiration
            if openers and len(day_opts) == 1:
                parsed, name, _c = day_opts[0]
                return (
                    parsed,
                    f"menu-only:{name[:64]}|win={title}|pids={len(pids)}",
                )

            if openers:
                names = ",".join((n[:24] for n, _c in openers[:4]))
                last_detail = (
                    f"opener-unparsed:{names}|day_opts={len(day_opts)}"
                    f"|win={title}|pids={len(pids)}"
                )
                # Keep searching other windows; bare Expiration alone is not enough.
                continue
        return None, last_detail
    except Exception as e:
        return None, f"scan:{e}"


def _parse_expiration_opener_days(name: str) -> str | None:
    """
    Map Expiration opener / option Name → days token or absolute date.

    Returns ``\"7\"|\"30\"|\"60\"|\"90\"|\"none\"`` or ``YYYY-MM-DD`` for Custom.
    """
    low = (name or "").strip().lower()
    if not low:
        return None
    if "no expiration" in low or "만료 없음" in low:
        return "none"
    m = re.search(r"\b(\d{1,3})\s*days?\b", low)
    if m:
        return m.group(1)
    # Custom date shown on the opener after picking a calendar day.
    m_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", low)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)}"
    return None


def try_set_token_expiration_uia(
    days_value: str, *, allow_click: bool = True
) -> tuple[bool, str]:
    """
    Path B: set classic PAT Expiration on a Chromium-PID browser window.

    ``days_value``: ``\"7\"|\"30\"|\"60\"|\"90\"|\"none\"`` (same as WebView path).

    1. Resolve Chrome/Edge/… PIDs via ``tasklist`` and only scan those windows
       (ranked: strong PAT title → foreground → score → Z-order).
    2. Activate Expiration opener → matching option via Invoke, then optional
       coordinate click (cursor restored) if Invoke is ignored.
    3. Never closes the browser.

    Soft-fails when Chrome hides the menu from a11y.
    """
    import time

    if not browser_address_available():
        path_b_log("[Path B] Expiration: uiautomation 없음")
        return False, "uiautomation-missing"
    try:
        import uiautomation as auto
    except Exception as e:
        path_b_log(f"[Path B] Expiration: import 실패 ({e})")
        return False, f"import:{e}"

    want = (days_value or "90").strip().lower()
    if want in ("", "no-expiration", "never"):
        want = "none"

    def _is_opener(name: str) -> bool:
        return uia_name_is_expiration_opener(name)

    def _is_option(name: str) -> bool:
        return uia_name_matches_expiration_option(name, want)

    pids = list_chromium_browser_pids()
    path_b_log(
        f"[Path B] Expiration 시도 want={want} "
        f"click={'on' if allow_click else 'off'} browser_pids={len(pids)}"
    )

    def _find_opener() -> tuple[str, object, object] | None:
        """Highest-ranked window that exposes an Expiration opener.

        Returns ``(opener_name, opener_ctrl, owner_window)``.
        """
        for w in _iter_chromium_windows(auto, pids=pids or None):
            found: list = []
            try:
                for ctrl in w.GetChildren():
                    _collect_named_controls(ctrl, found, depth=0, max_depth=16)
            except Exception:
                continue
            pairs = [(n, c) for n, _t, c in found if _is_opener(n)]
            if not pairs:
                continue
            pairs.sort(
                key=lambda pair: (
                    0 if re.search(r"\b\d{1,3}\s*days?\b", pair[0], re.I) else 1,
                    0 if "no expiration" in pair[0].lower() else 1,
                    len(pair[0]),
                )
            )
            n, c = pairs[0]
            return n, c, w
        return None

    def _find_option(owner) -> tuple[str, object] | None:
        """Find expiry option; prefer controls under ``owner`` window."""
        windows = _iter_chromium_windows(auto, pids=pids or None)
        ordered = []
        if owner is not None:
            ordered.append(owner)
        for w in windows:
            if w is not owner:
                ordered.append(w)
        for w in ordered:
            found: list = []
            try:
                for ctrl in w.GetChildren():
                    _collect_named_controls(ctrl, found, depth=0, max_depth=16)
            except Exception:
                continue
            matches = [(n, c) for n, _t, c in found if _is_option(n)]
            if not matches:
                continue
            matches.sort(key=lambda pair: len(pair[0]))
            return matches[0]
        return None

    try:
        # Log top-ranked window (title = active tab) for post-mortem.
        ranked = _iter_chromium_windows(auto, pids=pids or None)
        if ranked:
            top = ranked[0]
            try:
                top_title = (top.Name or "")[:64]
            except Exception:
                top_title = "?"
            path_b_log(
                f"[Path B] 창 순위 1위: {top_title} "
                f"(score={window_title_connect_score(top_title)}, "
                f"windows={len(ranked)})"
            )

        found_opener = _find_opener()
        if found_opener is None:
            fail = f"expiry-opener-not-found|pids={len(pids)}"
            path_b_log(f"[Path B] Expiration 실패: {fail}")
            return False, fail

        opener_name, opener_ctrl, owner = found_opener
        already = _parse_expiration_opener_days(opener_name)
        if already is not None and already == want:
            ok_msg = f"already:{opener_name[:48]}|want={want}|pids={len(pids)}"
            path_b_log(f"[Path B] Expiration 이미 일치: {ok_msg}")
            return True, ok_msg

        ok, detail = _uia_activate(
            opener_ctrl, allow_click=allow_click, owner_window=owner
        )
        if not ok:
            fail = f"opener-{detail}|pids={len(pids)}"
            path_b_log(f"[Path B] Expiration opener 실패: {fail}")
            return False, fail

        time.sleep(0.55)

        found_opt = _find_option(owner)
        if found_opt is None:
            fail = f"expiry-option-not-found:{want}|opened:{detail}"
            path_b_log(f"[Path B] Expiration 옵션 실패: {fail}")
            return False, fail

        _opt_name, opt_ctrl = found_opt
        ok2, detail2 = _uia_activate(
            opt_ctrl, allow_click=allow_click, owner_window=owner
        )
        if not ok2:
            fail = f"option-{detail2}"
            path_b_log(f"[Path B] Expiration 옵션 활성화 실패: {fail}")
            return False, fail

        time.sleep(0.35)
        # Read-back without further interaction.
        got, read_detail = read_token_expiration_uia()
        win_title = ""
        try:
            win_title = ((owner.Name if owner is not None else "") or "")[:40]
        except Exception:
            pass
        if got is not None and got == want:
            ok_msg = (
                f"{detail}|{detail2}|verified:{got}|want={want}|win={win_title}"
            )
            path_b_log(f"[Path B] Expiration 성공(검증): {ok_msg}")
            return True, ok_msg
        # Activate may have worked even if read-back is stale / hidden.
        ok_msg = (
            f"{detail}|{detail2}|want={want}|readback={got}|"
            f"{read_detail}|win={win_title}"
        )
        path_b_log(f"[Path B] Expiration 적용(읽기검증 불완전): {ok_msg}")
        return True, ok_msg
    except Exception as e:
        path_b_log(f"[Path B] Expiration 오류: {e}")
        return False, f"scan:{e}"


def _is_connect_flow_url(url: str) -> bool:
    u = (url or "").lower()
    return (
        "github.com" in u
        or "accounts.google.com" in u
        or "appleid.apple.com" in u
        or "idmsa.apple.com" in u
    )


def read_browser_page_sample() -> BrowserPageSample | None:
    """
    Best-effort sample: omnibox URL + window title + accessible UI names.

    Prefers foreground Chromium, then Apple/Google/GitHub tabs, then any
    Chromium window. Also samples a foreground Windows Security sheet
    (passkey). Does not use screenshots (DOM often hidden from a11y);
    callers may combine with coordinate click if UIA Invoke fails.

    Performance: first pass reads **URL + title only** (no deep a11y walk).
    Full UI harvest runs only on the chosen window — otherwise Path B polls
    freeze the UI for 10s+ when many Chromium windows are open.
    """
    if not browser_address_available():
        return None
    try:
        import uiautomation as auto
    except Exception:
        return None

    def _peek(win) -> tuple[str, str]:
        """URL + title only — cheap enough to run on every Chromium window."""
        try:
            title = (win.Name or "").strip()
            url = ""
            if (win.ClassName or "") == _BROWSER_CLASS:
                url = _read_edit_url(win) or ""
            return url, title
        except Exception:
            return "", ""

    def _finish(
        win,
        source: str,
        *,
        url: str = "",
        title: str = "",
        harvest: bool = True,
    ) -> BrowserPageSample | None:
        try:
            if not url and not title:
                url, title = _peek(win)
            ui_text = _harvest_ui_text(win) if harvest else ""
            if not url and not title and not ui_text:
                return None
            return BrowserPageSample(
                url=url or "",
                window_title=title or "",
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

        weak_fg_win = None
        weak_fg_url = ""
        weak_fg_title = ""
        if top is not None:
            # Cheap passkey title check before any deep harvest.
            fg_title = (top.Name or "").strip()
            if looks_like_passkey_os_prompt(fg_title, ""):
                # Confirm with a harvest only when the title already looks right.
                ui_text = _harvest_ui_text(top)
                if looks_like_passkey_os_prompt(fg_title, ui_text):
                    return BrowserPageSample(
                        url="",
                        window_title=fg_title,
                        ui_text=ui_text,
                        source="foreground-os",
                    )
            # Foreground Chromium: only short-circuit when it looks like our
            # connect flow. A Google-search tab in front must not hide a
            # background "New Personal Access Token" window (same as UIA rank).
            if (top.ClassName or "") == _BROWSER_CLASS:
                u_fg, t_fg = _peek(top)
                score_fg = window_title_connect_score(t_fg)
                if score_fg >= 28 or _is_connect_flow_url(u_fg):
                    return _finish(
                        top, "foreground", url=u_fg, title=t_fg, harvest=True
                    )
                if u_fg or t_fg:
                    weak_fg_win = top
                    weak_fg_url = u_fg
                    weak_fg_title = t_fg

        # CloneUp guide is often StayOnTop, so foreground may not be the
        # browser. Walk PID-scoped windows — URL/title first, harvest last.
        pids = list_chromium_browser_pids()
        fallback_win = weak_fg_win
        fallback_url = weak_fg_url
        fallback_title = weak_fg_title
        github_win = None
        github_url = ""
        github_title = ""
        for w in _iter_chromium_windows(auto, pids=pids or None):
            try:
                u, title = _peek(w)
                if not u and not title:
                    continue
                title_l = title.lower()
                title_score = window_title_connect_score(title)
                if _is_connect_flow_url(u):
                    return _finish(
                        w, "scan-ranked", url=u, title=title, harvest=True
                    )
                # Strong PAT / GitHub title — take immediately (ranked first).
                if title_score >= 28:
                    return _finish(
                        w, "scan-ranked", url=u, title=title, harvest=True
                    )
                if (
                    ("github" in title_l or title_score > 0)
                    and github_win is None
                ):
                    github_win = w
                    github_url = u
                    github_title = title
                if fallback_win is None:
                    fallback_win = w
                    fallback_url = u
                    fallback_title = title
            except Exception:
                continue
        if github_win is not None:
            return _finish(
                github_win,
                "scan-ranked",
                url=github_url,
                title=github_title,
                harvest=True,
            )
        if fallback_win is not None:
            # Unrelated tabs (news, Intel DSA, …): URL+title is enough to
            # classify as ``away``. Deep harvest here froze Path B polls for
            # 10s+ on busy Chromium profiles.
            return _finish(
                fallback_win,
                "scan-ranked" if fallback_win is not weak_fg_win else "foreground",
                url=fallback_url,
                title=fallback_title,
                harvest=False,
            )
        return None
    except Exception:
        return None


def read_browser_address_bar() -> str | None:
    """Return https URL from Chrome/Edge omnibox, or None."""
    sample = read_browser_page_sample()
    if sample is None:
        return None
    return sample.url or None
