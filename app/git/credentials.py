"""Temporary git credential helper files (token never in .git/config or argv)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_credential_file(token: str) -> str:
    """
    git-credential-store one-line format (trailing slash required on Windows):

      https://x-access-token:TOKEN@github.com/
    """
    fd, path = tempfile.mkstemp(prefix="cloneup-git-cred-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"https://x-access-token:{token}@github.com/\n")
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def credential_helper_configs(cred_path: str) -> list[tuple[str, str]]:
    """Clear helper chain, then store --file=<posix path>."""
    posix = Path(cred_path).resolve().as_posix()
    return [
        ("credential.helper", ""),
        ("credential.helper", f"store --file={posix}"),
    ]


def delete_credential_file(path: str | None) -> None:
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        pass
