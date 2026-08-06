"""Temporary git credential helper files (token never in .git/config or argv)."""

from __future__ import annotations

import os
import stat
import tempfile
import time
from pathlib import Path

_CRED_PREFIX = "cloneup-git-cred-"
_CRED_SUFFIX = ".txt"
# Orphans older than this are removed (crash / kill mid-push).
_ORPHAN_MAX_AGE_SEC = 15 * 60


def cleanup_orphan_credential_files(
    *,
    max_age_sec: float = _ORPHAN_MAX_AGE_SEC,
) -> int:
    """
    Delete leftover ``cloneup-git-cred-*.txt`` under the system temp dir.

    Safe to call often: only removes our prefix and only files older than
    ``max_age_sec`` (default 15 min) so an in-flight push is not disturbed.
    """
    removed = 0
    try:
        temp = Path(tempfile.gettempdir())
    except OSError:
        return 0
    now = time.time()
    try:
        paths = list(temp.glob(f"{_CRED_PREFIX}*{_CRED_SUFFIX}"))
    except OSError:
        return 0
    for p in paths:
        try:
            if not p.is_file():
                continue
            age = now - p.stat().st_mtime
            if age < max_age_sec:
                continue
            p.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
    return removed


def write_credential_file(token: str) -> str:
    """
    git-credential-store one-line format (trailing slash required on Windows):

      https://x-access-token:TOKEN@github.com/
    """
    # Best-effort: clear old leftovers from a previous crash
    cleanup_orphan_credential_files()

    fd, path = tempfile.mkstemp(prefix=_CRED_PREFIX, suffix=_CRED_SUFFIX)
    try:
        # Owner read/write only where the OS honors chmod (Unix; best-effort on Win)
        try:
            os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        except (AttributeError, OSError):
            pass
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"https://x-access-token:{token}@github.com/\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
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
        # Best-effort wipe before unlink (reduces slack-space residue on some FS)
        p = Path(path)
        if p.is_file():
            try:
                size = p.stat().st_size
                with open(p, "r+b", buffering=0) as f:
                    f.write(b"\0" * max(size, 1))
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
            except OSError:
                pass
        os.unlink(path)
    except OSError:
        pass
