"""App configuration.

client_id is a *public* OAuth client identifier (Device Flow / public client).
It is safe to ship a build-time default inside the binary. `.env` only overrides
that default during local development (e.g. testing another OAuth App).

OAuth **ownership** (personal vs Organization) is product/ops metadata used in
trust copy — not a secret. After moving the app to an Org, update the defaults
here (or set env vars) so the UI tells users who owns the login app.
See docs/ORG_OAUTH_APP.md.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Built-in default for packaged / end-user runs (not a secret).
DEFAULT_GITHUB_CLIENT_ID = "Ov23liuwynj1IgDmz8Tj"
# Classic PAT scope: still ``repo`` because default publish is *private* (M5).
# ``public_repo`` alone cannot create private repos — reducing the default
# scope would break the product path. Prefer fine-grained PAT (one repo +
# Contents R/W) via login UI copy; we do not invent a narrower classic scope.
DEFAULT_GITHUB_SCOPES = "repo"

# --- OAuth App ownership (transparency for Device Flow; PAT ignores this) ---
# Ownership kind: "personal" | "organization"
DEFAULT_OAUTH_APP_OWNER_KIND = "personal"
# Display name shown in login UI (GitHub user or Org login).
DEFAULT_OAUTH_APP_OWNER_NAME = "seongbin45"
# Public page for the product / repo (Homepage URL of the OAuth App).
DEFAULT_OAUTH_APP_HOMEPAGE = "https://github.com/seongbin45/CloneUp"

_ROOT = Path(__file__).resolve().parent.parent
_ENV_LOADED = False


def _ensure_dotenv() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    # Override-only: missing .env is fine (production / PyInstaller).
    load_dotenv(_ROOT / ".env", override=False)
    _ENV_LOADED = True


def get_github_client_id() -> str:
    _ensure_dotenv()
    return (os.getenv("GITHUB_CLIENT_ID") or DEFAULT_GITHUB_CLIENT_ID).strip()


def get_github_scopes() -> str:
    """Requested scopes for a *new* login (PAT expected scopes / Device opt-in)."""
    _ensure_dotenv()
    return (os.getenv("GITHUB_SCOPES") or DEFAULT_GITHUB_SCOPES).strip()


def is_device_flow_allowed() -> bool:
    """
    Device Flow (OAuth public client_id) is **off by default**.

    Why: any program can reuse a shipped client_id, show the same GitHub
    consent screen, and steal the token when the user authorizes. That is not
    fixable by hiding the id. End-user auth is PAT-only (user-created token).

    Maintainers may set CLONEUP_ALLOW_DEVICE_FLOW=1 for local experiments only.
    """
    _ensure_dotenv()
    raw = (os.getenv("CLONEUP_ALLOW_DEVICE_FLOW") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_oauth_app_owner_kind() -> str:
    """Return ``personal`` or ``organization`` (default personal until Org move)."""
    _ensure_dotenv()
    raw = (
        os.getenv("GITHUB_OAUTH_APP_OWNER_KIND") or DEFAULT_OAUTH_APP_OWNER_KIND
    ).strip().lower()
    if raw in ("org", "organisation", "organization"):
        return "organization"
    return "personal"


def get_oauth_app_owner_name() -> str:
    _ensure_dotenv()
    return (
        os.getenv("GITHUB_OAUTH_APP_OWNER_NAME") or DEFAULT_OAUTH_APP_OWNER_NAME
    ).strip()


def get_oauth_app_homepage() -> str:
    _ensure_dotenv()
    return (
        os.getenv("GITHUB_OAUTH_APP_HOMEPAGE") or DEFAULT_OAUTH_APP_HOMEPAGE
    ).strip()


def oauth_app_trust_summary(*, include_client_id: bool = False) -> str:
    """
    One short Korean block for login dialogs / tooltips.

    Honest about personal vs Org ownership so users can choose PAT instead.
    """
    kind = get_oauth_app_owner_kind()
    name = get_oauth_app_owner_name() or "(미설정)"
    homepage = get_oauth_app_homepage()
    scopes = get_github_scopes() or "repo"

    if kind == "organization":
        owner_line = f"OAuth 앱 소유: GitHub 조직 「{name}」"
    else:
        owner_line = (
            f"OAuth 앱 소유: 개인 계정 「{name}」 "
            "(아직 Organization 이전 전 — 불신 시 PAT 로그인 권장)"
        )

    lines = [
        owner_line,
        f"요청 권한(scope): {scopes}",
        "토큰 저장: 이 PC OS keyring만 (.git/config·로그 제외)",
    ]
    if homepage:
        lines.append(f"제품/저장소: {homepage}")
    if include_client_id:
        cid = get_github_client_id()
        if cid:
            # Public identifier — safe to show; helps advanced users verify.
            lines.append(f"client_id: {cid}")
    return "\n".join(lines)


def oauth_app_owner_one_liner() -> str:
    """Single line for device-code overlay / compact UI."""
    kind = get_oauth_app_owner_kind()
    name = get_oauth_app_owner_name() or "?"
    if kind == "organization":
        return f"이 로그인은 조직 「{name}」 OAuth 앱을 사용합니다."
    return (
        f"이 로그인은 개인 계정 「{name}」 OAuth 앱을 사용합니다. "
        "앱을 신뢰하기 어려우면 PAT 로그인을 쓰세요."
    )
