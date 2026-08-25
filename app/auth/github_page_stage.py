"""Detect which GitHub web page the user is on during PAT connect.

Pure heuristics from URL / document title / HTML markers collected in
``temp/`` (login HTML, classic-token-new HTML, screenshots) and
``temp/github.com.zip`` (saved ``settings/tokens`` list page).

Does **not** open a browser, sniff traffic, or read another process.
Callers that later observe a page (WebView, etc.) pass a ``PageSnapshot``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class GitHubPageStage(str, Enum):
    UNKNOWN = "unknown"
    LOGIN = "login"
    AUTH_2FA = "auth_2fa"
    # Windows Security / OS passkey sheet — not visible in page HTML/URL.
    AUTH_PASSKEY_OS = "auth_passkey_os"
    TOKEN_CLASSIC_NEW = "token_classic_new"
    TOKEN_FINE_NEW = "token_fine_new"
    TOKEN_ISSUED = "token_issued"
    TOKEN_CLASSIC_LIST = "token_classic_list"
    TOKEN_FINE_LIST = "token_fine_list"
    SUDO_OR_OTHER = "sudo_or_other"


@dataclass(frozen=True)
class PageSnapshot:
    """Observable bits of a GitHub document (any subset may be empty)."""

    url: str = ""
    title: str = ""
    html: str = ""


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_ROUTE_RE = re.compile(
    r'<meta[^>]+name=["\']route-pattern["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_TOKEN_IN_HTML_RE = re.compile(
    r"\b(gh[pousr]_[A-Za-z0-9_]{10,}|github_pat_[A-Za-z0-9_]{10,})\b"
)


def _norm(s: str) -> str:
    return (s or "").strip()


def _extract_title(html: str) -> str:
    m = _TITLE_RE.search(html or "")
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def _path_of(url: str) -> str:
    raw = _norm(url)
    if not raw:
        return ""
    if "://" not in raw and raw.startswith("/"):
        return raw.split("?", 1)[0]
    try:
        return (urlparse(raw).path or "").rstrip("/") or "/"
    except Exception:
        return ""


def detect_github_page_stage(snap: PageSnapshot) -> GitHubPageStage:
    """
    Classify a GitHub page into a connect-flow stage.

    Priority: strong URL paths → title → HTML markers.
    """
    url = _norm(snap.url)
    html = snap.html or ""
    title = _norm(snap.title) or _extract_title(html)
    path = _path_of(url)
    html_l = html.lower()
    title_l = title.lower()

    # --- URL path (strong) ---
    if path == "/login" or path.startswith("/login/"):
        return GitHubPageStage.LOGIN

    if (
        "/sessions/two-factor" in path
        or path.endswith("/two-factor")
        or "/sessions/verified-device" in path
    ):
        return GitHubPageStage.AUTH_2FA

    if path.endswith("/settings/tokens/new") or path == "/settings/tokens/new":
        return GitHubPageStage.TOKEN_CLASSIC_NEW

    if (
        "/settings/personal-access-tokens/new" in path
        or path.endswith("/personal-access-tokens/new")
    ):
        return GitHubPageStage.TOKEN_FINE_NEW

    # List page from github.com.zip — not the same as "token just issued".
    if path == "/settings/tokens" or path.endswith("/settings/tokens"):
        if _is_token_issued(title_l, html_l, html):
            return GitHubPageStage.TOKEN_ISSUED
        return GitHubPageStage.TOKEN_CLASSIC_LIST

    # Fine-grained token list (not /new)
    if (
        path == "/settings/personal-access-tokens"
        or path.endswith("/settings/personal-access-tokens")
    ):
        return GitHubPageStage.TOKEN_FINE_LIST

    # --- Title ---
    if "sign in to github" in title_l:
        return GitHubPageStage.LOGIN

    if "two-factor authentication" in title_l or "two-factor authentication" in html_l:
        if "authentication code" in html_l or "authenticator" in html_l or "otp" in html_l:
            return GitHubPageStage.AUTH_2FA
        if "two-factor authentication" in title_l:
            return GitHubPageStage.AUTH_2FA

    if "new personal access token (classic)" in title_l:
        return GitHubPageStage.TOKEN_CLASSIC_NEW

    if "new fine-grained personal access token" in title_l:
        return GitHubPageStage.TOKEN_FINE_NEW

    if _is_token_issued(title_l, html_l, html):
        return GitHubPageStage.TOKEN_ISSUED

    if title_l == "personal access tokens (classic)" or (
        "personal access tokens (classic)" in title_l and "new " not in title_l
    ):
        return GitHubPageStage.TOKEN_CLASSIC_LIST

    # --- HTML markers (temp dumps) ---
    if 'id="login_field"' in html or "id='login_field'" in html:
        if 'id="password"' in html or "name=\"password\"" in html:
            return GitHubPageStage.LOGIN

    if 'id="new_oauth_access"' in html or "Generate token" in html:
        if "oauth_access[scopes]" in html or 'data-scope-for="repo"' in html:
            return GitHubPageStage.TOKEN_CLASSIC_NEW

    if "sudo_modal" in html_l and "settings/tokens" not in path:
        # Weak signal — only if nothing else matched.
        if "confirm access" in html_l or "sudo" in title_l:
            return GitHubPageStage.SUDO_OR_OTHER

    return GitHubPageStage.UNKNOWN


def _is_token_issued(title_l: str, html_l: str, html: str) -> bool:
    """
    Post-create page: must copy the token now.

    Screenshot evidence: banner + visible ghp_ value.
    """
    copy_now = (
        "make sure to copy your personal access token now" in html_l
        or "make sure to copy your personal access token now" in title_l
        or (
            "copy your personal access token" in html_l
            and "now" in html_l
        )
    )
    has_secret = bool(_TOKEN_IN_HTML_RE.search(html))
    return copy_now and has_secret


def stage_label_ko(stage: GitHubPageStage) -> str:
    """Short Korean label for UI (optional callers)."""
    return {
        GitHubPageStage.UNKNOWN: "알 수 없음",
        GitHubPageStage.LOGIN: "GitHub 로그인",
        GitHubPageStage.AUTH_2FA: "2단계 인증(코드)",
        GitHubPageStage.AUTH_PASSKEY_OS: "패스키(OS 창 · HTML로 감지 불가)",
        GitHubPageStage.TOKEN_CLASSIC_NEW: "classic 키 만들기",
        GitHubPageStage.TOKEN_FINE_NEW: "세분 키 만들기",
        GitHubPageStage.TOKEN_ISSUED: "키 발급됨(지금 복사)",
        GitHubPageStage.TOKEN_CLASSIC_LIST: "classic 키 목록",
        GitHubPageStage.TOKEN_FINE_LIST: "세분 키 목록",
        GitHubPageStage.SUDO_OR_OTHER: "추가 확인(sudo 등)",
    }.get(stage, stage.value)
