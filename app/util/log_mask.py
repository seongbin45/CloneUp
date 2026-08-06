"""Mask secrets in console / log output."""

from __future__ import annotations

import re

# Classic / fine-grained GitHub tokens
_TOKEN_RE = re.compile(
    r"\b(gh[pousr]_[A-Za-z0-9_]{10,}|github_pat_[A-Za-z0-9_]{10,})\b"
)
# Temp credential-helper line / URL embed
_X_ACCESS_RE = re.compile(
    r"(?i)(x-access-token:)([^\s@/\"']+)"
)
# Authorization headers
_BEARER_RE = re.compile(
    r"(?i)(authorization:\s*bearer\s+)([^\s\"']+)"
)
# https://user:pass@host — mask password segment
_URL_USERINFO_RE = re.compile(
    r"(https?://)([^:/@\s]+):([^@\s]+)(@)",
    re.I,
)


def mask_token(token: str | None) -> str:
    """
    Display form for a known secret.

    Prefer not leaking prefix/suffix of live tokens in UI logs.
    """
    if not token:
        return "(empty)"
    n = len(token)
    if n <= 8:
        return "***"
    return f"*** (len={n})"


def mask_secrets_in_text(text: str) -> str:
    """Redact GitHub tokens and credential-helper embeds from free-form text."""
    if not text:
        return text

    def _tok(m: re.Match[str]) -> str:
        return mask_token(m.group(0))

    # Embed forms first (so token regex does not leave "*** (len=N)" inside URLs)
    out = _X_ACCESS_RE.sub(lambda m: f"{m.group(1)}***", text)
    out = _BEARER_RE.sub(lambda m: f"{m.group(1)}***", out)
    out = _URL_USERINFO_RE.sub(r"\1\2:***\4", out)
    out = _TOKEN_RE.sub(_tok, out)
    return out