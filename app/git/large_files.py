"""GitHub channel-aware large-file detection (plan rev.3).

Thresholds use strict ``>`` (exactly 100 MiB is warn-only, not a hard block).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# GitHub docs: warn above 50 MiB; hard-block above 100 MiB (MiB = 1024**2).
WARN_BYTES = 50 * 1024 * 1024
BLOCK_BYTES = 100 * 1024 * 1024
RELEASE_MAX_BYTES = 2 * 1024 * 1024 * 1024

_LFS_POINTER_RE = re.compile(
    r"^version https://git-lfs\.github\.com/spec/v1\s*$", re.M
)
_LFS_ATTR_RE = re.compile(r"^\s*([^\s#]+)\s+.*\bfilter=lfs\b", re.M)


class LargeKind(str, Enum):
    OK = "ok"
    WARN = "warn"  # WARN_BYTES < size <= BLOCK_BYTES
    BLOCK = "block"  # size > BLOCK_BYTES


@dataclass(frozen=True)
class LargeFileHit:
    rel: str  # posix relative path
    size: int
    kind: LargeKind

    @property
    def size_mib(self) -> float:
        return self.size / (1024 * 1024)


def classify_size(
    size: int,
    *,
    warn_bytes: int = WARN_BYTES,
    block_bytes: int = BLOCK_BYTES,
) -> LargeKind:
    if size > block_bytes:
        return LargeKind.BLOCK
    if size > warn_bytes:
        return LargeKind.WARN
    return LargeKind.OK


def format_warn_log_line(hit: LargeFileHit) -> str:
    """L-10: warn-only — one Korean log line, no popup."""
    return (
        f"안내: {hit.rel} ({hit.size_mib:.0f} MB) — "
        "GitHub 권장 크기(50 MB)를 넘지만 올리기는 됩니다. "
        "가능하면 빼 두는 편이 좋습니다."
    )


def is_lfs_pointer_file(path: Path) -> bool:
    """True if *path* looks like a Git LFS pointer (mandatory skip)."""
    try:
        if not path.is_file():
            return False
        # Pointers are tiny text; skip huge files without reading.
        if path.stat().st_size > 1024:
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if not _LFS_POINTER_RE.search(text):
        return False
    return "oid sha256:" in text and "size " in text


def load_lfs_attr_patterns(folder: Path) -> list[str]:
    """Patterns from ``.gitattributes`` that use ``filter=lfs``."""
    ga = folder / ".gitattributes"
    if not ga.is_file():
        return []
    try:
        text = ga.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [m.group(1) for m in _LFS_ATTR_RE.finditer(text)]


def _path_matches_lfs_attr(rel: str, patterns: list[str]) -> bool:
    """Minimal glob: ``*`` and ``**`` / suffix patterns used in .gitattributes."""
    name = Path(rel).name
    for pat in patterns:
        if pat == rel or pat == f"/{rel}":
            return True
        if pat.startswith("*.") and name.endswith(pat[1:]):
            return True
        if pat.endswith("/**") and rel.startswith(pat[:-3].lstrip("/")):
            return True
        # simple ``path/**`` already handled; ``*.psd`` style above
        if "*" not in pat and (rel == pat.lstrip("/") or rel.endswith("/" + pat)):
            return True
    return False


def should_skip_as_lfs(folder: Path, rel: str, *, patterns: list[str] | None = None) -> bool:
    root = folder.resolve()
    path = root / rel
    if is_lfs_pointer_file(path):
        return True
    pats = patterns if patterns is not None else load_lfs_attr_patterns(root)
    return _path_matches_lfs_attr(rel.replace("\\", "/"), pats)


def gitignore_exact_line(rel: str) -> str:
    """Leading-slash exact repo-relative pattern (``/assets/video.mp4``)."""
    posix = rel.replace("\\", "/").lstrip("/")
    return f"/{posix}"


def find_working_tree_large_files(
    folder: Path,
    *,
    paths: list[str] | None = None,
    warn_bytes: int = WARN_BYTES,
    block_bytes: int = BLOCK_BYTES,
) -> tuple[list[LargeFileHit], list[LargeFileHit]]:
    """
    Stage A scan.

    Returns ``(warnings, blocks)``. Uses publishable paths when *paths* is None
    (git view if ``.git`` exists, else filesystem fallback).
    """
    from app.git.safety import list_publishable_relpaths

    root = folder.resolve()
    if paths is None:
        paths, _ = list_publishable_relpaths(root)
    lfs_pats = load_lfs_attr_patterns(root)
    warnings: list[LargeFileHit] = []
    blocks: list[LargeFileHit] = []
    for rel in paths:
        rel_p = rel.replace("\\", "/")
        if should_skip_as_lfs(root, rel_p, patterns=lfs_pats):
            continue
        path = root / rel_p
        try:
            if not path.is_file():
                continue
            size = int(path.stat().st_size)
        except OSError:
            continue
        kind = classify_size(size, warn_bytes=warn_bytes, block_bytes=block_bytes)
        if kind is LargeKind.OK:
            continue
        hit = LargeFileHit(rel=rel_p, size=size, kind=kind)
        if kind is LargeKind.BLOCK:
            blocks.append(hit)
        else:
            warnings.append(hit)
    return warnings, blocks


def is_github_size_limit_error(message: str) -> bool:
    """Stage B reactive trigger: GH001 / 100 MB pre-receive text."""
    low = (message or "").lower()
    if "gh001" in low:
        return True
    if "file size limit of 100" in low:
        return True
    if "exceeds github" in low and "100" in low and "mb" in low:
        return True
    if "이 초과" in (message or "") and "100" in (message or ""):
        return True
    return False
