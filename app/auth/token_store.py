"""Persist GitHub access tokens + metadata in the OS keyring.

When master protection is enabled (see ``secret_vault``), the PAT is stored as
``enc.v1.<b64>`` ciphertext. Day-to-day ``load_token`` decrypts via DPAPI DEK
without prompting for the master password.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import keyring

from . import secret_vault

logger = logging.getLogger(__name__)

SERVICE_NAME = "CloneUp"
TOKEN_USERNAME = "github_oauth_access_token"
SCOPE_USERNAME = "github_oauth_scope"
# How the token was obtained: "device" | "pat"
AUTH_KIND_USERNAME = "github_auth_kind"
# When CloneUp last successfully stored this token (ISO-8601 UTC).
# GitHub does not always expose PAT expiry via API — we track *connect age*.
CONNECTED_AT_USERNAME = "github_token_connected_at"
# GitHub PAT expiration when known: ISO-8601 UTC ``…Z``, or ``none``.
EXPIRES_AT_USERNAME = "github_token_expires_at"
# Note / name CloneUp put on the GitHub token form when the key was created.
PAT_NOTE_USERNAME = "github_pat_note"

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


def load_token_raw() -> str | None:
    """Raw keyring value — plaintext PAT or ``enc.v1.…`` ciphertext."""
    return keyring.get_password(SERVICE_NAME, TOKEN_USERNAME)


def save_token(
    token: str,
    scope: str = "",
    *,
    auth_kind: str | None = None,
    connected_at: str | None = None,
    expires_at: str | None = None,
    pat_note: str | None = None,
) -> None:
    if not token or not token.strip():
        raise ValueError("refusing to store empty token")
    plain = token.strip()
    # If caller already passed an enc.v1 blob, store as-is; otherwise encrypt
    # when master protection is on.
    if secret_vault.is_encrypted_blob(plain):
        to_store = plain
    elif secret_vault.is_protection_enabled():
        to_store = secret_vault.encrypt_token_for_store(plain)
    else:
        to_store = plain
    keyring.set_password(SERVICE_NAME, TOKEN_USERNAME, to_store)
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
    if expires_at is not None:
        exp = (expires_at or "").strip()
        if exp:
            keyring.set_password(SERVICE_NAME, EXPIRES_AT_USERNAME, exp)
        else:
            _delete_key(EXPIRES_AT_USERNAME)
    if pat_note is not None:
        note = (pat_note or "").strip()
        if note:
            keyring.set_password(SERVICE_NAME, PAT_NOTE_USERNAME, note)
        else:
            _delete_key(PAT_NOTE_USERNAME)


def load_token() -> str | None:
    """Plaintext PAT, or None. Decrypts ``enc.v1.…`` when protection is on."""
    raw = load_token_raw()
    if raw is None:
        return None
    if not secret_vault.is_encrypted_blob(raw):
        return raw
    try:
        return secret_vault.decrypt_token_from_store(raw)
    except secret_vault.VaultError as e:
        logger.warning("encrypted token present but decrypt failed: %s", e)
        return None


def is_logged_in() -> bool:
    """True when a GitHub access token is stored on this PC."""
    # Raw keyring presence covers enc.v1 blobs even if DPAPI unlock fails.
    raw = load_token_raw()
    if raw is not None and str(raw).strip():
        return True
    # Fallback: callers/tests that only stub ``load_token``.
    return bool(load_token())
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


def load_expires_at_raw() -> str | None:
    """ISO-8601 UTC, ``none``, or None if never recorded."""
    raw = keyring.get_password(SERVICE_NAME, EXPIRES_AT_USERNAME)
    if raw is None:
        return None
    s = raw.strip()
    return s or None


def load_expires_at() -> datetime | None:
    """Parsed expiry, or None when unknown / ``none`` (no expiration)."""
    raw = load_expires_at_raw()
    if not raw or raw.lower() == "none":
        return None
    text = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_pat_note() -> str | None:
    """Note / name used on the GitHub token form when CloneUp created the key."""
    raw = keyring.get_password(SERVICE_NAME, PAT_NOTE_USERNAME)
    if raw is None:
        return None
    s = raw.strip()
    return s or None


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
    """Remove token + metadata from keyring. Vault (master wrap) is left intact."""
    for username in (
        TOKEN_USERNAME,
        SCOPE_USERNAME,
        AUTH_KIND_USERNAME,
        CONNECTED_AT_USERNAME,
        EXPIRES_AT_USERNAME,
        PAT_NOTE_USERNAME,
    ):
        _delete_key(username)


def _delete_key(username: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, username)
    except keyring.errors.PasswordDeleteError:
        pass


# ---------------------------------------------------------------------------
# Master-protection migration helpers (Settings API; no UI yet)
# ---------------------------------------------------------------------------


def is_token_encrypted() -> bool:
    """True when the stored PAT is an ``enc.v1.…`` ciphertext."""
    return secret_vault.is_encrypted_blob(load_token_raw())


def enable_master_protection(password: str) -> None:
    """
    Enable master protection and migrate any existing plaintext PAT.

    Master password is used only in memory here — never written to disk.
    Daily loads use DPAPI afterwards (no password prompt).
    """
    if secret_vault.is_protection_enabled():
        raise secret_vault.VaultError("master protection is already enabled")
    raw = load_token_raw()
    plain: str | None = None
    if raw and not secret_vault.is_encrypted_blob(raw):
        plain = raw.strip() or None
    elif raw and secret_vault.is_encrypted_blob(raw):
        # Orphan ciphertext without vault — cannot migrate safely.
        raise secret_vault.VaultError(
            "encrypted token found but vault is missing; clear token and reconnect"
        )

    enc = secret_vault.enable_protection(password, plaintext_token=plain)
    if enc is not None:
        keyring.set_password(SERVICE_NAME, TOKEN_USERNAME, enc)


def change_master_password(old_password: str, new_password: str) -> None:
    """Re-wrap DEK with a new master password (DPAPI blob unchanged)."""
    secret_vault.change_password(old_password, new_password)


def disable_master_protection(password: str) -> None:
    """
    Disable master protection after verifying ``password``.

    Decrypts the PAT back to plaintext in keyring, then clears vault files.
    """
    if not secret_vault.is_protection_enabled():
        raise secret_vault.VaultError("master protection is not enabled")
    raw = load_token_raw()
    plain = secret_vault.disable_protection(password, encrypted_blob=raw)
    if plain is not None:
        keyring.set_password(SERVICE_NAME, TOKEN_USERNAME, plain)
    elif raw and secret_vault.is_encrypted_blob(raw):
        # disable_protection should have returned plaintext; fail closed.
        raise secret_vault.VaultError("failed to recover plaintext token on disable")


def master_protection_enabled() -> bool:
    """True when wrap.json + dek.dpapi exist."""
    return secret_vault.is_protection_enabled()

def parse_oauth_scopes(raw: str | None) -> list[str]:
    """
    Parse GitHub scope strings from ``X-OAuth-Scopes`` or keyring storage.

    GitHub documents comma-separated values (optional spaces), e.g.
    ``repo, user`` or ``gist, read:org, repo, workflow``. Some paths use
    spaces only. Accept both; never split on ``:`` (scopes like ``read:org``).
    """
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    out: list[str] = []
    for chunk in text.replace(",", " ").split():
        s = chunk.strip()
        if s:
            out.append(s)
    return out


def normalize_scope_string(raw: str | None) -> str:
    """
    Canonical scope list for storage and UI (order preserved, first wins on dupes).

    Format matches GitHub's X-OAuth-Scopes style: ``repo, user`` (comma + space).
    Parsing accepts both commas and spaces; never leave a trailing comma on a name.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for s in parse_oauth_scopes(raw):
        if s in seen:
            continue
        seen.add(s)
        ordered.append(s)
    return ", ".join(ordered)


def format_scopes_display(raw: str | None) -> str:
    """
    Human-readable scopes for Settings / tooltips / error text.

    Unknown / empty → empty string (caller chooses 「권한 확인 불가」 etc.).
    """
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text or is_scope_unknown(text):
        return ""
    return normalize_scope_string(text)


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

    GitHub may return comma- or space-separated scopes in X-OAuth-Scopes.
    Unknown/missing stored scope → False (do not claim a permission we cannot prove).
    Callers that only need "token exists" should use ``scopes_known()`` / skip this gate.
    """
    granted = load_scope()
    if granted is None or is_scope_unknown(granted):
        return False
    parts = set(parse_oauth_scopes(granted))
    if required in parts:
        return True
    # repo implies public_repo for our purposes
    if required == "public_repo" and "repo" in parts:
        return True
    return False
