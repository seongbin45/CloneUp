"""App configuration.

client_id is a *public* OAuth client identifier (Device Flow / public client).
It is safe to ship a build-time default inside the binary. `.env` only overrides
that default during local development (e.g. testing another OAuth App).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Built-in default for packaged / end-user runs (not a secret).
DEFAULT_GITHUB_CLIENT_ID = "Ov23liuwynj1IgDmz8Tj"
DEFAULT_GITHUB_SCOPES = "public_repo"

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
    """Requested scopes for a *new* Device Flow login (not the stored grant)."""
    _ensure_dotenv()
    return (os.getenv("GITHUB_SCOPES") or DEFAULT_GITHUB_SCOPES).strip()
