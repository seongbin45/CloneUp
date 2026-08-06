"""Persist GitHub access tokens + metadata in the OS keyring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import keyring

SERVICE_NAME = "CloneUp"
TOKEN_USERNAME = "github_oauth_access_token"
SCOPE_USERNAME = "github_oauth_scope"
# How the token was obtained: "device" | "pat"
AUTH_KIND_USERNAME = "github_auth_kind"
# When CloneUp last successfully stored this token (ISO-8601 UTC).
# GitHub does not always expose PAT expiry via API — we track *connect age*.
CONNECTED_AT_USERNAME = "github_token_connected_at"

AUTH_KIND_DEVICE = "device"
AUTH_KIND_PAT = "pat"

# Stored when GitHub omits X-OAuth-Scopes (common for fine-grained PATs).
# Must NOT be replaced with a guessed "repo" — that was a false confidence bug (M3).
SCOPE_UNKNOWN = "unknown"

# Soft reminders (days since connect). Not exact GitHub expiry.
WARN_DAYS_SOFT = 30
WARN_DAYS_STRONG = 60
WARN_DAYS_STALE = 90


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def save_token(
    token: str,
    scope: str = "",
    *,
    auth_kind: str | None = None,
    connected_at: str | None = None,
) -> None:
    if not token or not token.strip():
        raise ValueError("refusing to store empty token")
    keyring.set_password(SERVICE_NAME, TOKEN_USERNAME, token.strip())
    # Empty string is valid (GitHub may omit scope for some grants).
    keyring.set_password(SERVICE_NAME, SCOPE_USERNAME, (scope or "").strip())
    if auth_kind is not None:
        kind = (auth_kind or "").strip().lower()
        if kind:
            keyring.set_password(SERVICE_NAME, AUTH_KIND_USERNAME, kind)
        else:
            _delete_key(AUTH_KIND_USERNAME)
    # Stamp connect time on every successful save (new key or re-login).
    stamp = (connected_at or "").strip() or _iso_now()
    keyring.set_password(SERVICE_NAME, CONNECTED_AT_USERNAME, stamp)


def load_token() -> str | None:
    return keyring.get_password(SERVICE_NAME, TOKEN_USERNAME)


def load_scope() -> str | None:
    """Granted scope string from last successful login (may be None)."""
    return keyring.get_password(SERVICE_NAME, SCOPE_USERNAME)


def load_auth_kind() -> str | None:
    """Return ``device`` / ``pat`` / None if unknown (older installs)."""
    raw = keyring.get_password(SERVICE_NAME, AUTH_KIND_USERNAME)
    if raw is None:
        return None
    kind = raw.strip().lower()
    return kind or None


def load_connected_at_raw() -> str | None:
    raw = keyring.get_password(SERVICE_NAME, CONNECTED_AT_USERNAME)
    if raw is None:
        return None
    s = raw.strip()
    return s or None


def load_connected_at() -> datetime | None:
    """Parse stored connect time as timezone-aware UTC datetime."""
    raw = load_connected_at_raw()
    if not raw:
        return None
    text = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def days_since_connected() -> int | None:
    """Whole days since token was stored in CloneUp, or None if unknown."""
    dt = load_connected_at()
    if dt is None:
        return None
    delta = _utc_now() - dt
    return max(0, int(delta.total_seconds() // 86400))


@dataclass(frozen=True)
class TokenAgeInfo:
    """Soft age info — not GitHub's exact expiry date."""

    days: int | None
    connected_at: datetime | None
    level: str  # "unknown" | "ok" | "soft" | "strong" | "stale"
    status_line: str  # short Korean for button / log
    tooltip_extra: str


def token_age_info() -> TokenAgeInfo:
    """
    Classify how long ago this PC stored the key.

    GitHub PAT may expire on a user-chosen date (7/30/90/none). API often does
    not tell us that date for classic PATs, so we warn by *connect age*.
    """
    days = days_since_connected()
    connected = load_connected_at()
    if days is None:
        return TokenAgeInfo(
            days=None,
            connected_at=None,
            level="unknown",
            status_line="",
            tooltip_extra=(
                "연결 시각 기록 없음 (이전 버전 가능).\n"
                "GitHub 키는 만료일이 있으면 그날 이후 사용할 수 없습니다.\n"
                "만료·취소되면 「GitHub: 로그인」에서 새 키로 다시 연결하세요."
            ),
        )

    when = connected.strftime("%Y-%m-%d") if connected else "?"
    base = f"이 PC에 연결한 날: {when} (약 {days}일 전)"

    if days >= WARN_DAYS_STALE:
        return TokenAgeInfo(
            days=days,
            connected_at=connected,
            level="stale",
            status_line="키 확인 권장",
            tooltip_extra=(
                f"{base}\n"
                "키가 꽤 오래됐습니다. GitHub에서 설정한 만료일이 지났을 수 있습니다.\n"
                "올리기/받기가 실패하면 새 키를 만들어 다시 연결하세요."
            ),
        )
    if days >= WARN_DAYS_STRONG:
        return TokenAgeInfo(
            days=days,
            connected_at=connected,
            level="strong",
            status_line="",
            tooltip_extra=(
                f"{base}\n"
                "곧 만료됐을 수 있습니다 (30·60·90일 옵션을 고른 경우).\n"
                "GitHub → Settings → Developer settings → Personal access tokens\n"
                "에서 만료일을 확인하세요."
            ),
        )
    if days >= WARN_DAYS_SOFT:
        return TokenAgeInfo(
            days=days,
            connected_at=connected,
            level="soft",
            status_line="",
            tooltip_extra=(
                f"{base}\n"
                "키가 30일 이상 됐습니다. 짧은 만료(7·30일)를 골랐다면 곧 다시 연결이 필요할 수 있습니다."
            ),
        )
    return TokenAgeInfo(
        days=days,
        connected_at=connected,
        level="ok",
        status_line="",
        tooltip_extra=(
            f"{base}\n"
            "만료일은 GitHub에서 키를 만들 때 정합니다. "
            "만료 후에는 이 앱에서 새 키로 다시 연결해야 합니다."
        ),
    )


def delete_token() -> None:
    for username in (
        TOKEN_USERNAME,
        SCOPE_USERNAME,
        AUTH_KIND_USERNAME,
        CONNECTED_AT_USERNAME,
    ):
        _delete_key(username)


def _delete_key(username: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, username)
    except keyring.errors.PasswordDeleteError:
        pass


def is_scope_unknown(scope: str | None = None) -> bool:
    """
    True when we do not know classic OAuth scopes for this token.

    Fine-grained PATs often send an empty X-OAuth-Scopes header. We store
    ``SCOPE_UNKNOWN`` instead of inventing ``repo``.
    """
    raw = load_scope() if scope is None else scope
    if raw is None:
        return True
    s = raw.strip().lower()
    return s in ("", SCOPE_UNKNOWN, "__unknown__")


def scopes_known() -> bool:
    """False when scope is missing/unknown — skip optimistic pre-checks."""
    return not is_scope_unknown()


def has_scope(required: str) -> bool:
    """
    Return True if the stored grant appears to include `required`.

    GitHub returns space-separated scopes.
    Unknown/missing stored scope → False (do not claim a permission we cannot prove).
    Callers that only need "token exists" should use ``scopes_known()`` / skip this gate.
    """
    granted = load_scope()
    if granted is None or is_scope_unknown(granted):
        return False
    parts = set(granted.split())
    if required in parts:
        return True
    # repo implies public_repo for our purposes
    if required == "public_repo" and "repo" in parts:
        return True
    return False
