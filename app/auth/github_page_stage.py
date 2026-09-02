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

    # Passkey WebAuthn 2FA before generic two-factor (email/app OTP).
    if "/two-factor/webauthn" in path or path.endswith("/webauthn"):
        return GitHubPageStage.AUTH_PASSKEY_OS

    if (
        "/sessions/two-factor" in path
        or path.endswith("/two-factor")
        or "/sessions/verified-device" in path
        or "/sessions/email-verification" in path
        or "/login/device" in path
    ):
        return GitHubPageStage.AUTH_2FA

    # --- Auth body BEFORE token URL ---
    # Screenshot: Confirm access + Use passkey can sit on tokens/new URL.
    # Treating URL alone as TOKEN_CLASSIC_NEW skipped AUTH_WAIT.
    if _looks_like_sudo_passkey_confirm(title_l, html_l):
        return GitHubPageStage.AUTH_PASSKEY_OS

    if _looks_like_webauthn_passkey(title_l, html_l):
        return GitHubPageStage.AUTH_PASSKEY_OS

    # Device / email verification (Verify your device · Device verification).
    if _looks_like_device_or_email_verify(title_l, html_l):
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

    # --- Title / body (Path B often has title+UIA text but a vague omnibox) ---
    if "sign in to github" in title_l:
        return GitHubPageStage.LOGIN

    if _looks_like_webauthn_passkey(title_l, html_l):
        return GitHubPageStage.AUTH_PASSKEY_OS
    try:
        from app.util.auth_ocr import (
            looks_like_github_mobile_2fa,
            looks_like_github_recovery_2fa,
            looks_like_github_totp_2fa,
        )

        if (
            looks_like_github_mobile_2fa(title_l, html_l)
            or looks_like_github_recovery_2fa(title_l, html_l)
            or looks_like_github_totp_2fa(title_l, html_l)
        ):
            return GitHubPageStage.AUTH_2FA
    except Exception:
        pass
    if "two-factor authentication" in title_l or "two-factor authentication" in html_l:
        if "authentication code" in html_l or "authenticator" in html_l or "otp" in html_l:
            return GitHubPageStage.AUTH_2FA
        if "two-factor authentication" in title_l:
            return GitHubPageStage.AUTH_2FA
    if "two-factor recovery" in title_l or "two-factor recovery" in html_l:
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

    # Body/OCR when omnibox empty (Path B StayOnTop often blanks URL).
    if _looks_like_token_classic_new(title_l, html_l):
        return GitHubPageStage.TOKEN_CLASSIC_NEW
    if _looks_like_token_classic_list(title_l, html_l):
        return GitHubPageStage.TOKEN_CLASSIC_LIST

    # --- HTML markers (temp dumps) ---
    if 'id="login_field"' in html or "id='login_field'" in html:
        if 'id="password"' in html or "name=\"password\"" in html:
            return GitHubPageStage.LOGIN

    if 'id="new_oauth_access"' in html or "Generate token" in html:
        if "oauth_access[scopes]" in html or 'data-scope-for="repo"' in html:
            return GitHubPageStage.TOKEN_CLASSIC_NEW

    if "confirm access" in html_l or "sudo_modal" in html_l:
        if "passkey" in html_l or "use passkey" in html_l:
            return GitHubPageStage.AUTH_PASSKEY_OS
        if "sudo" in title_l or "sudo_modal" in html_l:
            return GitHubPageStage.SUDO_OR_OTHER

    return GitHubPageStage.UNKNOWN


def _looks_like_token_classic_new(title_l: str, body_l: str) -> bool:
    """Create form: Note + Expiration + Select scopes (screenshot 2026-09-02)."""
    blob = f"{title_l}\n{body_l}"
    if "new personal access token (classic)" in blob:
        return True
    if "new personal access token" in blob and "classic" in blob:
        return True
    formish = (
        ("select scopes" in blob or "what's this token for" in blob or "whats this token for" in blob)
        and ("expiration" in blob or "note" in blob)
    )
    if formish and (
        "generate token" in blob
        or "repo:status" in blob
        or "public_repo" in blob
    ):
        return True
    return False


def _looks_like_token_classic_list(title_l: str, body_l: str) -> bool:
    """
    Token list (not /new): Generate new token + existing rows.

    Screenshot 2026-09-02: ``/settings/tokens`` with
    「Tokens you have generated…」, Last used / Never used / Expires on.
    Must not match the create form (Select scopes + Note).
    """
    if _looks_like_token_classic_new(title_l, body_l):
        return False
    blob = f"{title_l}\n{body_l}"
    list_heading = (
        "tokens you have generated" in blob
        or "generate new token" in blob
        or (
            "personal access tokens (classic)" in blob
            and "new personal access token" not in blob
        )
    )
    list_rows = (
        "last used" in blob
        or "never used" in blob
        or "this token has no expiration" in blob
        or "expires on" in blob
        or "no expiration date" in blob
    )
    if list_heading and list_rows:
        return True
    if "generate new token" in blob and (
        "tokens you have generated" in blob or "last used" in blob
    ):
        return True
    return False


def _looks_like_sudo_passkey_confirm(title_l: str, body_l: str) -> bool:
    """GitHub Confirm access / sudo card with Passkey (OCR or UIA)."""
    try:
        from app.util.auth_ocr import looks_like_github_sudo_passkey

        return looks_like_github_sudo_passkey(title_l, body_l)
    except Exception:
        blob = f"{title_l}\n{body_l}"
        return "confirm access" in blob and (
            "use passkey" in blob or "passkey" in blob
        )


def _looks_like_webauthn_passkey(title_l: str, body_l: str) -> bool:
    """GitHub 2FA 「Authenticate using your passkey」 / Use passkey."""
    try:
        from app.util.auth_ocr import looks_like_github_webauthn_passkey

        return looks_like_github_webauthn_passkey(title_l, body_l)
    except Exception:
        blob = f"{title_l}\n{body_l}"
        return "use passkey" in blob and (
            "two-factor" in blob or "authenticate using your passkey" in blob
        )


def _looks_like_device_or_email_verify(title_l: str, body_l: str) -> bool:
    """
    GitHub 「Verify your device」 / 「Device verification」 email OTP.

    Seen in browser title ``Verify your device · GitHub`` with six digit
    inputs and optional 「Verify with a passkey」, or Device verification
    email code page (``/sessions/verified-device``).
    """
    try:
        from app.util.auth_ocr import looks_like_device_email_verify

        if looks_like_device_email_verify(title_l, body_l):
            return True
    except Exception:
        pass
    blob = f"{title_l}\n{body_l}"
    if "verify your device" in blob:
        return True
    if "verification code" in blob and (
        "email" in blob or "sent a verification" in blob or "we just sent" in blob
    ):
        return True
    if "verify with a passkey" in blob and (
        "verification code" in blob or "verify your device" in blob
    ):
        return True
    if "verify with something else" in blob and "passkey" in blob:
        return True
    return False


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
        GitHubPageStage.AUTH_PASSKEY_OS: "패스키(Windows 보안·Confirm access)",
        GitHubPageStage.TOKEN_CLASSIC_NEW: "classic 키 만들기",
        GitHubPageStage.TOKEN_FINE_NEW: "세분 키 만들기",
        GitHubPageStage.TOKEN_ISSUED: "키 발급됨(지금 복사)",
        GitHubPageStage.TOKEN_CLASSIC_LIST: "classic 키 목록",
        GitHubPageStage.TOKEN_FINE_LIST: "세분 키 목록",
        GitHubPageStage.SUDO_OR_OTHER: "추가 확인(sudo 등)",
    }.get(stage, stage.value)
