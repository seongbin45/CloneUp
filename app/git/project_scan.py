"""Discover project folders under registered scan roots (홈 목록).

Does **not** walk the whole disk. Roots = user 「찾을 위치」 ∪ defaults ∪
parents of recent folders. Depth and count are capped.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from app.ui.settings_store import load_recent_folders, load_scan_roots

# Caps — keep UI responsive on beginner PCs
DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_PROJECTS = 200
_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".next",
        "target",
        "AppData",
        "Application Data",
    }
)


@dataclass(frozen=True)
class ProjectEntry:
    path: str
    name: str
    has_git: bool
    last_mtime: float
    dirty: bool | None = None  # None = not probed; True/False = presence only (Phase B)
    branch: str = ""


def default_scan_roots() -> list[Path]:
    """Built-in roots when the user has not registered any yet."""
    home = Path.home()
    candidates = [
        home / "Desktop",
        home / "Documents",
        home / "Projects",
        home / "Developer",
        home / "source",
        home / "src",
        home / "code",
    ]
    # Parents of recent folders (one level up) — often a “Projects” tree
    for raw in load_recent_folders():
        try:
            p = Path(raw).expanduser().resolve()
        except OSError:
            continue
        if p.is_dir():
            candidates.append(p)
            if p.parent.is_dir() and p.parent != p:
                candidates.append(p.parent)
    out: list[Path] = []
    seen: set[str] = set()
    for c in candidates:
        try:
            r = c.resolve()
        except OSError:
            continue
        key = str(r).lower()
        if key in seen or not r.is_dir():
            continue
        seen.add(key)
        out.append(r)
    return out


def resolve_scan_roots() -> list[Path]:
    """Registered roots if any; otherwise defaults."""
    registered = load_scan_roots()
    if registered:
        out: list[Path] = []
        seen: set[str] = set()
        for raw in registered:
            try:
                p = Path(raw).expanduser().resolve()
            except OSError:
                continue
            key = str(p).lower()
            if key in seen or not p.is_dir():
                continue
            seen.add(key)
            out.append(p)
        return out or default_scan_roots()
    return default_scan_roots()


def _dir_mtime(path: Path) -> float:
    try:
        return float(path.stat().st_mtime)
    except OSError:
        return 0.0


def _looks_like_project(path: Path) -> bool:
    """Heuristic: has .git, or common project markers (non-git work folder)."""
    try:
        if (path / ".git").exists():
            return True
    except OSError:
        return False
    markers = (
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "README.md",
        "README.txt",
        "Makefile",
        "CMakeLists.txt",
    )
    try:
        for name in markers:
            if (path / name).is_file():
                return True
        # Visual Studio solution
        if any(p.suffix.lower() == ".sln" for p in path.iterdir() if p.is_file()):
            return True
    except OSError:
        return False
    return False


def scan_projects(
    roots: list[Path] | None = None,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_projects: int = DEFAULT_MAX_PROJECTS,
    probe_dirty: bool = False,
) -> list[ProjectEntry]:
    """
    Walk *roots* up to *max_depth* and collect project folders.

    When a directory contains ``.git``, it is recorded and **not** descended
    into further (repo root). Non-git project markers are included when found.
    """
    roots = list(roots) if roots is not None else resolve_scan_roots()
    found: list[ProjectEntry] = []
    seen: set[str] = set()

    def add(path: Path, *, has_git: bool) -> None:
        nonlocal found
        if len(found) >= max_projects:
            return
        try:
            key = str(path.resolve()).lower()
        except OSError:
            return
        if key in seen:
            return
        seen.add(key)
        dirty: bool | None = None
        branch = ""
        if has_git and probe_dirty:
            dirty, branch = _probe_git_presence(path)
        found.append(
            ProjectEntry(
                path=str(path),
                name=path.name or str(path),
                has_git=has_git,
                last_mtime=_dir_mtime(path),
                dirty=dirty,
                branch=branch,
            )
        )

    def walk(current: Path, depth: int) -> None:
        if len(found) >= max_projects:
            return
        if depth > max_depth:
            return
        try:
            has_git = (current / ".git").exists()
        except OSError:
            return
        if has_git:
            add(current, has_git=True)
            return  # do not walk into the repo
        # Optionally treat marker folders as projects (no .git)
        if depth >= 1 and _looks_like_project(current):
            add(current, has_git=False)
            # still walk children for nested git repos
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for child in children:
            if len(found) >= max_projects:
                return
            try:
                if not child.is_dir():
                    continue
                if child.is_symlink():
                    continue
                if child.name in _SKIP_DIR_NAMES or child.name.startswith("."):
                    continue
            except OSError:
                continue
            walk(child, depth + 1)

    for root in roots:
        if len(found) >= max_projects:
            break
        # Root itself may be a git repo
        walk(root, 0)

    # Always include recent folders even if outside roots
    for raw in load_recent_folders():
        if len(found) >= max_projects:
            break
        try:
            p = Path(raw).expanduser().resolve()
        except OSError:
            continue
        if not p.is_dir():
            continue
        key = str(p).lower()
        if key in seen:
            continue
        has_git = (p / ".git").exists()
        dirty = None
        branch = ""
        if has_git and probe_dirty:
            dirty, branch = _probe_git_presence(p)
        seen.add(key)
        found.append(
            ProjectEntry(
                path=str(p),
                name=p.name or str(p),
                has_git=has_git,
                last_mtime=_dir_mtime(p),
                dirty=dirty,
                branch=branch,
            )
        )

    found.sort(key=lambda e: e.last_mtime, reverse=True)
    return found


def _probe_git_presence(path: Path) -> tuple[bool, str]:
    """Return (has_pending_changes, branch_name). Presence only — no file counts."""
    from app.ui.boot_scan import folder_needs_notify

    branch = ""
    try:
        from app.git.sync_ops import SyncError, get_repo_status

        st = get_repo_status(path)
        branch = str(getattr(st, "branch", "") or "")
        return bool(folder_needs_notify(st)), branch
    except Exception:
        return False, branch


def format_relative_mtime(mtime: float, *, now: float | None = None) -> str:
    """Short Korean-ish relative time for list column."""
    now = time.time() if now is None else now
    if mtime <= 0:
        return "—"
    delta = max(0, int(now - mtime))
    if delta < 60:
        return "방금"
    if delta < 3600:
        return f"{delta // 60}분 전"
    if delta < 86400:
        return f"{delta // 3600}시간 전"
    days = delta // 86400
    if days == 1:
        return "어제"
    if days < 7:
        return f"{days}일 전"
    if days < 30:
        return f"{days // 7}주 전"
    return f"{days // 30}개월 전"


def use_legacy_tabs() -> bool:
    """CLONEUP_LEGACY_TABS=1 keeps the old tab shell as the main window."""
    return os.environ.get("CLONEUP_LEGACY_TABS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
