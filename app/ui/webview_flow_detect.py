"""Independent WebView flow classifier (HTML/URL/title).

Mirrors the browser-guide (ExternalBrowserPatGuide) exception and login
detection, but does **not** import that dialog. Uses page HTML instead of UIA.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.auth.github_page_stage import GitHubPageStage, PageSnapshot, detect_github_page_stage

# --- PAT scrape (same shape as browser guide / connect_webview JS) ---
_VISIBLE_PAT_RE = re.compile(
    r"\b(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
    re.IGNORECASE,
)

# Google insecure-browser / rejected (EN)
_GOOGLE_BLOCK_NEEDLES = (
    "may not be secure",
    "couldn't sign you in",
    "couldn’t sign you in",
    "try using a different browser",
    "browser or app may not be secure",
    "signin/rejected",
)

# Logged-out github.com marketing (HTML)
_LOGGED_OUT_STRONG = (
    "sign up for github",
    "sign in to github",
    "github에 가입",
    "github에 로그인",
)

_NOTE_TAKEN_NEEDLES = (
    "note has already been taken",
    "note already been taken",
    "has already been taken",
)


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _path(url: str) -> str:
    try:
        return (urlparse(url).path or "").lower()
    except Exception:
        return ""


def _blob(title: str, html: str) -> str:
    b = f"{title or ''}\n{html or ''}".lower()
    return b.replace("\xa0", " ").replace("\u00a0", " ")


def looks_like_google_blocked_html(url: str, title: str = "", html: str = "") -> bool:
    u = (url or "").lower()
    if "accounts.google.com" in u and (
        "/signin/rejected" in u or "rejected" in _path(u)
    ):
        return True
    blob = _blob(title, html)
    if not blob.strip():
        return False
    if "accounts.google.com" in u or "google" in (title or "").lower():
        return any(n in blob for n in _GOOGLE_BLOCK_NEEDLES)
    return any(n in blob for n in _GOOGLE_BLOCK_NEEDLES)


def looks_like_github_logged_out_html(
    url: str, title: str = "", html: str = ""
) -> bool:
    """Same intent as UIA Sign in/Sign up check — for github.com HTML."""
    host = _hostname(url)
    if host and host != "github.com" and not host.endswith(".github.com"):
        return False
    blob = _blob(title, html)
    if not blob.strip():
        return False
    if any(s in blob for s in _LOGGED_OUT_STRONG):
        return True
    has_in = "sign in" in blob or "로그인" in blob
    has_up = "sign up" in blob or "가입" in blob
    return bool(has_in and has_up and "github" in blob)


def looks_like_token_note_taken_html(
    url: str, title: str = "", html: str = ""
) -> bool:
    blob = _blob(title, html)
    if not blob.strip():
        return False
    if "note has already been taken" in blob:
        return True
    if "has already been taken" in blob and (
        "note" in blob or "validation failed" in blob
    ):
        return True
    path = _path(url)
    on_token = "settings/tokens" in path or "personal-access-token" in path
    return on_token and any(n in blob for n in _NOTE_TAKEN_NEEDLES)


def extract_pat_from_html(title: str = "", html: str = "") -> str | None:
    blob = f"{title or ''}\n{html or ''}"
    m = _VISIBLE_PAT_RE.search(blob)
    if not m:
        return None
    tok = m.group(1).strip()
    if len(tok) < 24:
        return None
    return tok


def looks_like_token_issued_html(title: str = "", html: str = "") -> bool:
    blob = _blob(title, html)
    if "make sure to copy your personal access token now" in blob:
        return True
    if "copy your personal access token" in blob and "now" in blob:
        return True
    if "개인용 액세스 토큰을 지금 복사" in blob or "지금 복사해 두세요" in blob:
        return True
    return False


def detect_webview_method(url: str, title: str = "", html: str = "") -> str:
    """Mirror detect_signin_method for WebView samples."""
    u = (url or "").strip()
    if looks_like_google_blocked_html(u, title, html):
        return "google_blocked"
    host = _hostname(u)
    path = _path(u)
    if host in ("appleid.apple.com", "idmsa.apple.com") or "appleid.apple.com" in u.lower():
        return "apple"
    if host == "accounts.google.com" or (
        host.endswith(".google.com") and host.startswith("accounts.")
    ):
        return "google"
    if host == "github.com" or (host and host.endswith(".github.com")):
        if path == "/logout" or path.startswith("/logout"):
            return "github_logout"
        if path.startswith("/login") or path.startswith("/sessions/"):
            return "github_login"
        if looks_like_github_logged_out_html(u, title, html):
            return "github_logged_out"
        return "github"
    return "other"


def classify_webview_sample(
    url: str,
    *,
    title: str = "",
    html: str = "",
) -> tuple[str, int | None, dict]:
    """
    Independent twin of ``classify_browser_sample`` for in-app WebView.

    kind: rejected | logged_out | token_error | current | reached | away | unknown
    """
    u = (url or "").strip()
    method = detect_webview_method(u, title, html)
    meta: dict = {"method": method, "source": "webview_html"}

    if method == "google_blocked":
        return ("rejected", 0, meta)

    if method in ("github_logout", "github_logged_out"):
        return ("logged_out", 0, meta)

    if method in ("apple", "google", "github_login"):
        return ("current", 0, meta)

    if not u and not title:
        return ("unknown", None, meta)

    if looks_like_token_note_taken_html(u, title, html):
        meta["method"] = "token_note_taken"
        meta["token_error"] = "note_taken"
        return ("token_error", 2, meta)

    visible = extract_pat_from_html(title, html)
    if visible:
        meta["method"] = "token_visible"
        meta["visible_pat"] = visible
        return ("reached", 3, meta)
    if looks_like_token_issued_html(title, html):
        meta["method"] = "token_issued_banner"
        return ("reached", 3, meta)

    st = detect_github_page_stage(PageSnapshot(url=u, title=title, html=html))
    if st == GitHubPageStage.TOKEN_ISSUED:
        return ("reached", 3, meta)
    if st in (
        GitHubPageStage.TOKEN_CLASSIC_NEW,
        GitHubPageStage.TOKEN_FINE_NEW,
        GitHubPageStage.TOKEN_CLASSIC_LIST,
        GitHubPageStage.TOKEN_FINE_LIST,
    ):
        return ("reached", 2, meta)
    if st == GitHubPageStage.AUTH_2FA:
        return ("reached", 1, meta)
    if st == GitHubPageStage.LOGIN:
        return ("current", 0, meta)

    host = _hostname(u)
    path = _path(u)
    if host == "github.com" or (host and host.endswith(".github.com")):
        if path == "/logout" or path.startswith("/logout"):
            return ("logged_out", 0, meta)
        if path.startswith("/login"):
            return ("current", 0, meta)
        return ("reached", 1, meta)

    if method == "apple" or "appleid.apple.com" in u.lower():
        return ("current", 0, meta)

    # Completely different parent host (not GitHub / Google accounts / Apple)
    if u and host and is_off_github_flow_family(u):
        meta["method"] = "away"
        return ("away", None, meta)

    return ("unknown", None, meta)


_AWAY_RETURN_SECONDS = 5


def is_off_github_flow_family(url: str) -> bool:
    """
    True when the URL has a host that is not the GitHub connect "parent" family.

    Family: github.com, Google account sign-in, Apple ID.
    Empty / host-less URLs are not treated as away (avoid about:blank flashes).
    """
    from app.util.browser_address import is_github_flow_family_url

    u = (url or "").strip()
    if not u:
        return False
    if not _hostname(u):
        return False
    return not is_github_flow_family_url(u)


def away_return_countdown_seconds() -> int:
    return _AWAY_RETURN_SECONDS


def away_return_target_url() -> str:
    """Classic PAT create page (fresh unique Note each call)."""
    from app.auth.pat_urls import classic_pat_create_url, make_pat_note

    return classic_pat_create_url(note=make_pat_note())


def format_away_return_banner(secs_left: int) -> str:
    """Dialog overlay copy: countdown before returning to token create."""
    n = max(0, int(secs_left))
    return f"{n}초 후 Github 키 발급 페이지로 다시 이동합니다."


# Single-segment paths that are product/chrome, not ``/{username}`` profiles.
_GITHUB_RESERVED_ROOT_SEGMENTS = frozenset(
    {
        "about",
        "account",
        "apps",
        "collections",
        "contact",
        "copilot",
        "customer-stories",
        "enterprise",
        "events",
        "explore",
        "features",
        "home",
        "issues",
        "join",
        "login",
        "logout",
        "marketplace",
        "new",
        "notifications",
        "organizations",
        "orgs",
        "password_reset",
        "pricing",
        "pulls",
        "readme",
        "search",
        "security",
        "sessions",
        "settings",
        "signup",
        "site",
        "sponsors",
        "stars",
        "topics",
        "watching",
    }
)


def looks_like_github_user_profile_url(url: str) -> bool:
    """
    True for ``github.com/{username}`` (and ``?tab=repositories`` etc.).

    One path segment that is not a reserved product route. Repo paths
    (``/{owner}/{repo}``) are excluded — two or more segments.
    """
    host = _hostname(url)
    if not host or (host != "github.com" and not host.endswith(".github.com")):
        return False
    if host.startswith("gist."):
        return False
    path = (_path(url) or "").strip("/")
    if not path:
        return False
    parts = [p for p in path.split("/") if p]
    if len(parts) != 1:
        return False
    seg = parts[0].lower()
    if seg in _GITHUB_RESERVED_ROOT_SEGMENTS:
        return False
    if seg.startswith("."):
        return False
    return True


def is_github_main_home_url(url: str) -> bool:
    """True for github.com `/`, `/dashboard`, `/home` (logged-in landing)."""
    host = _hostname(url)
    if not host:
        return False
    if host != "github.com" and not host.endswith(".github.com"):
        return False
    path = (_path(url) or "").rstrip("/")
    return path in ("", "/", "/dashboard", "/home")


def looks_like_github_token_flow_url(url: str) -> bool:
    """Classic / fine-grained PAT list or create pages (stay — connect flow)."""
    path = (_path(url) or "").lower()
    if not path:
        return False
    if "settings/tokens" in path:
        return True
    if "personal-access-tokens" in path:
        return True
    return False


def _is_github_host(url: str) -> bool:
    host = _hostname(url)
    return bool(host == "github.com" or (host and host.endswith(".github.com")))


def _is_github_login_or_sessions_path(url: str) -> bool:
    path = _path(url) or ""
    return path.startswith("/login") or path.startswith("/sessions")


def should_start_away_return_countdown(kind: str, url: str = "") -> bool:
    """
    When to show the 5s rollback-to-token-create banner.

    - ``away``: off GitHub-flow family hosts
    - 로그인 전 (``logged_out``): github.com 하위 **전부** 롤백
      (``/login``·``/sessions`` 은 보통 ``current``라 여기 안 옴; 경로로도 제외)
    - 로그인 후 (``reached``): **토큰 페이지가 아니면** 롤백
      (``/settings/tokens*``, personal-access-tokens 제외)
    - ``current`` (login / Google / Apple / 2FA sessions): 롤백 없음
    """
    if kind == "away":
        return True
    if kind in ("rejected", "current", "token_error", "unknown"):
        return False

    if not _is_github_host(url):
        return False
    if _is_github_login_or_sessions_path(url):
        return False

    if kind == "logged_out":
        # Pre-login: any github sub-URL (except login/sessions above)
        return True

    if kind == "reached":
        # Post-login: stay only on PAT create/list/issued pages
        if looks_like_github_token_flow_url(url):
            return False
        st = detect_github_page_stage(PageSnapshot(url=url))
        if st == GitHubPageStage.AUTH_2FA:
            return False
        return True

    return False


def should_auto_open_token_page(
    *,
    kind: str,
    idx: int | None,
    already_opened: bool,
    url: str = "",
    title: str = "",
    page_text: str = "",
) -> bool:
    """
    Open classic tokens/new once when logged-in on github.com main.

    Login is inferred as: classify ``reached`` idx 1, home URL, page text
    present, and no Sign in / Sign up (logged-out marketing).
    Skips empty first-paint and 2FA / other github paths.
    """
    if already_opened:
        return False
    if kind != "reached" or idx != 1:
        return False
    if not is_github_main_home_url(url):
        return False
    if not (title or page_text).strip():
        return False
    if looks_like_github_logged_out_html(url, title, page_text):
        return False
    return True


def guide_copy_for_webview_kind(
    kind: str, *, method: str = ""
) -> tuple[str, str] | None:
    """Optional (title, lead) overrides for the WebView chrome — ≤60 char leads."""
    if kind == "rejected" or method == "google_blocked":
        return (
            "Google 로그인이 막혔어요",
            "브라우저 안내로 바꿉니다. 잠시만 기다려 주세요.",
        )
    if kind == "logged_out":
        return (
            "로그인이 필요해요",
            "Sign in / Sign up이 보입니다. 다시 로그인해 주세요.",
        )
    if kind == "token_error":
        return (
            "Note 이름이 중복되었습니다",
            "새 Note(날짜·시간)로 다시 엽니다.",
        )
    if kind == "away":
        return (
            "GitHub 연결 화면이 아니에요",
            "주소창에서 github.com 으로 돌아와 주세요.",
        )
    return None
