"""Mask secrets in console / log output."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(
    r"\b(gh[pousr]_[A-Za-z0-9_]{10,}|github_pat_[A-Za-z0-9_]{10,})\b"
)


def mask_token(token: str | None) -> str:
    if not token:
        return "(empty)"
    if len(token) <= 12:
        return "***"
    return f"{token[:4]}…{token[-4:]} (len={len(token)})"


def mask_secrets_in_text(text: str) -> str:
    return _TOKEN_RE.sub(lambda m: mask_token(m.group(0)), text)
