"""Temporary git credential helper files (token never in .git/config or argv)."""

from __future__ import annotations

import os
import re
import stat
import tempfile
import time
from pathlib import Path

_CRED_PREFIX = "cloneup-git-cred-"
_CRED_SUFFIX = ".txt"
# Orphans older than this are removed (crash / kill mid-push).
_ORPHAN_MAX_AGE_SEC = 15 * 60
# Reject path chars that break shell-based credential.helper (H2).
_UNSAFE_PATH_CHARS = re.compile(r"[\'\"$`\\\n\r]")


def default_cred_directory() -> Path:
    """
    Prefer a CloneUp-owned temp dir under LOCALAPPDATA (still may contain spaces).

    Quoting in credential_helper_configs is what makes spaces safe; this only
    keeps our files out of a shared anonymous TEMP when possible.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMP") or tempfile.gettempdir()
    d = Path(base) / "CloneUp" / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup_orphan_credential_files(
    *,
    max_age_sec: float = _ORPHAN_MAX_AGE_SEC,
    directories: list[Path] | None = None,
) -> int:
    """
    Delete leftover ``cloneup-git-cred-*.txt`` under known temp dirs.
    """
    removed = 0
    dirs: list[Path] = []
    if directories is not None:
        dirs = list(directories)
    else:
        try:
            dirs.append(default_cred_directory())
        except OSError:
            pass
        try:
            dirs.append(Path(tempfile.gettempdir()))
        except OSError:
            pass
    now = time.time()
    seen: set[str] = set()
    for temp in dirs:
        try:
            key = str(temp.resolve())
        except OSError:
            key = str(temp)
        if key in seen:
            continue
        seen.add(key)
        try:
            paths = list(temp.glob(f"{_CRED_PREFIX}*{_CRED_SUFFIX}"))
        except OSError:
            continue
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


def write_credential_file(
    token: str,
    *,
    directory: Path | str | None = None,
) -> str:
    """
    git-credential-store one-line format (trailing slash required on Windows):

      https://x-access-token:TOKEN@github.com/
    """
    cleanup_orphan_credential_files()

    if directory is not None:
        dest_dir = Path(directory)
        dest_dir.mkdir(parents=True, exist_ok=True)
    else:
        dest_dir = default_cred_directory()

    fd, path = tempfile.mkstemp(
        prefix=_CRED_PREFIX,
        suffix=_CRED_SUFFIX,
        dir=str(dest_dir),
    )
    try:
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
    """
    Clear helper chain, then store --file=<quoted path>.

    git runs credential helpers via a shell (use_shell=1). Unquoted paths with
    spaces break auth on common Windows profiles; metacharacters can inject
    commands (H2 / CLONEUP_SECURITY_REVIEW).
    """
    posix = Path(cred_path).resolve().as_posix()
    if _UNSAFE_PATH_CHARS.search(posix):
        raise RuntimeError(
            "임시 자격 증명 경로에 사용할 수 없는 문자가 있습니다 "
            f"(따옴표/$/`/\\\\). path={posix!r}"
        )
    # Single quotes: POSIX shell does not expand $ inside them.
    return [
        ("credential.helper", ""),
        ("credential.helper", f"store --file='{posix}'"),
    ]


def delete_credential_file(path: str | None) -> None:
    if not path:
        return
    try:
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
