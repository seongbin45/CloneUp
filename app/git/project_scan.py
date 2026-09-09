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
    dirty: bool | None = None  # None = not probed; True/False = pending changes
    dirty_count: int = 0  # porcelain line count (Phase C); 0 if unknown/clean
    branch: str = ""


@dataclass(frozen=True)
class SubPathHit:
    """A child path under a project, ranked by mtime (expand row)."""

    rel_path: str
    mtime: float


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
        dirty_count = 0
        branch = ""
        if has_git and probe_dirty:
            dirty, branch, dirty_count = _probe_git_presence(path)
        found.append(
            ProjectEntry(
                path=str(path),
                name=path.name or str(path),
                has_git=has_git,
                last_mtime=_dir_mtime(path),
                dirty=dirty,
                dirty_count=dirty_count,
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
        dirty_count = 0
        branch = ""
        if has_git and probe_dirty:
            dirty, branch, dirty_count = _probe_git_presence(p)
        seen.add(key)
        found.append(
            ProjectEntry(
                path=str(p),
                name=p.name or str(p),
                has_git=has_git,
                last_mtime=_dir_mtime(p),
                dirty=dirty,
                dirty_count=dirty_count,
                branch=branch,
            )
        )

    found.sort(key=lambda e: e.last_mtime, reverse=True)
    return found


def _probe_git_presence(path: Path) -> tuple[bool, str, int]:
    """Return (has_pending_changes, branch_name, porcelain_count)."""
    from app.ui.boot_scan import folder_needs_notify

    branch = ""
    count = 0
    try:
        from app.git.sync_ops import get_repo_status

        st = get_repo_status(path)
        branch = str(getattr(st, "branch", "") or "")
        dirty = bool(folder_needs_notify(st))
    except Exception:
        return False, branch, 0
    try:
        from app.git.runner import run_git

        full = run_git(["status", "--porcelain"], cwd=str(path), check=False)
        if full.returncode == 0:
            count = len(
                [ln for ln in (full.stdout or "").splitlines() if ln.strip()]
            )
        if count == 0 and dirty:
            # Ahead-only: surface as at least 1 so UI can show a count later
            ahead = int(getattr(st, "ahead", 0) or 0)
            count = max(ahead, 1) if dirty else 0
        return bool(dirty or count > 0), branch, count
    except Exception:
        return dirty, branch, count


def list_recent_child_paths(
    root: Path | str,
    *,
    limit: int = 8,
    max_depth: int = 2,
) -> list[SubPathHit]:
    """
    Recent child dirs/files under *root* for expand rows (mtime ranked).

    Skips ``.git`` / ``node_modules`` / etc. Depth is relative to *root*.
    """
    root = Path(root).expanduser()
    try:
        root = root.resolve()
    except OSError:
        return []
    if not root.is_dir():
        return []
    hits: list[SubPathHit] = []

    def walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = list(current.iterdir())
        except OSError:
            return
        for child in children:
            try:
                if child.name in _SKIP_DIR_NAMES or (
                    child.name.startswith(".") and child.name != ".env"
                ):
                    continue
                if child.is_symlink():
                    continue
                is_dir = child.is_dir()
                is_file = child.is_file()
            except OSError:
                continue
            if not is_dir and not is_file:
                continue
            # Prefer directories for “손댄 곳”; skip huge binary noise files
            if is_file and child.suffix.lower() in {
                ".pyc",
                ".pyo",
                ".dll",
                ".exe",
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".webp",
                ".mp4",
                ".zip",
                ".7z",
            }:
                continue
            try:
                rel = str(child.relative_to(root)).replace("\\", "/")
                mt = float(child.stat().st_mtime)
            except OSError:
                continue
            if depth >= 1:
                hits.append(SubPathHit(rel_path=rel, mtime=mt))
            if is_dir and depth < max_depth:
                walk(child, depth + 1)

    walk(root, 0)
    hits.sort(key=lambda h: h.mtime, reverse=True)
    # De-dupe by top segment preference: keep first N unique rel paths
    out: list[SubPathHit] = []
    seen: set[str] = set()
    for h in hits:
        if h.rel_path in seen:
            continue
        seen.add(h.rel_path)
        out.append(h)
        if len(out) >= max(1, int(limit)):
            break
    return out


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


def format_clock(mtime: float) -> str:
    """HH:MM for timeline rows."""
    if mtime <= 0:
        return "--:--"
    try:
        return time.strftime("%H:%M", time.localtime(mtime))
    except (OverflowError, OSError, ValueError):
        return "--:--"


def time_bucket_label(mtime: float, *, now: float | None = None) -> str:
    """Bucket label: 오늘 / 어제 / 이번 주 / 지난주 / 더 오래 전."""
    from datetime import date, datetime, timedelta

    if mtime <= 0:
        return "더 오래 전"
    now_dt = datetime.fromtimestamp(now if now is not None else time.time())
    try:
        then = datetime.fromtimestamp(mtime)
    except (OverflowError, OSError, ValueError):
        return "더 오래 전"
    today = now_dt.date()
    d = then.date()
    if d == today:
        return "오늘"
    if d == today - timedelta(days=1):
        return "어제"
    # Week starts Monday
    start_this = today - timedelta(days=today.weekday())
    start_last = start_this - timedelta(days=7)
    if d >= start_this:
        return "이번 주"
    if d >= start_last:
        return "지난주"
    return "더 오래 전"


_BUCKET_ORDER = ("오늘", "어제", "이번 주", "지난주", "더 오래 전")


def group_by_time_bucket(
    entries: list[ProjectEntry], *, now: float | None = None
) -> list[tuple[str, list[ProjectEntry]]]:
    """Return ordered (label, entries) buckets for timeline view."""
    now = time.time() if now is None else now
    buckets: dict[str, list[ProjectEntry]] = {k: [] for k in _BUCKET_ORDER}
    for e in entries:
        label = time_bucket_label(e.last_mtime, now=now)
        buckets.setdefault(label, []).append(e)
    out: list[tuple[str, list[ProjectEntry]]] = []
    for label in _BUCKET_ORDER:
        items = buckets.get(label) or []
        if not items:
            continue
        items.sort(key=lambda x: x.last_mtime, reverse=True)
        out.append((label, items))
    return out


def use_legacy_tabs() -> bool:
    """CLONEUP_LEGACY_TABS=1 keeps the old tab shell as the main window."""
    return os.environ.get("CLONEUP_LEGACY_TABS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
