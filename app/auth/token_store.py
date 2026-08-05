"""Persist OAuth access tokens + granted scope in the OS keyring."""

from __future__ import annotations

import keyring

SERVICE_NAME = "CloneUp"
TOKEN_USERNAME = "github_oauth_access_token"
SCOPE_USERNAME = "github_oauth_scope"


def save_token(token: str, scope: str = "") -> None:
    if not token or not token.strip():
        raise ValueError("refusing to store empty token")
    keyring.set_password(SERVICE_NAME, TOKEN_USERNAME, token.strip())
    # Empty string is valid (GitHub may omit scope for some grants).
    keyring.set_password(SERVICE_NAME, SCOPE_USERNAME, (scope or "").strip())


def load_token() -> str | None:
    return keyring.get_password(SERVICE_NAME, TOKEN_USERNAME)


def load_scope() -> str | None:
    """Granted scope string from last successful Device Flow (may be None)."""
    return keyring.get_password(SERVICE_NAME, SCOPE_USERNAME)


def delete_token() -> None:
    for username in (TOKEN_USERNAME, SCOPE_USERNAME):
        try:
            keyring.delete_password(SERVICE_NAME, username)
        except keyring.errors.PasswordDeleteError:
            pass


def has_scope(required: str) -> bool:
    """
    Return True if the stored grant appears to include `required`.

    GitHub returns space-separated scopes. Unknown/missing stored scope → False
    so callers re-auth rather than guessing.
    """
    granted = load_scope()
    if granted is None:
        return False
    parts = set(granted.split())
    if required in parts:
        return True
    # repo implies public_repo for our purposes
    if required == "public_repo" and "repo" in parts:
        return True
    return False
