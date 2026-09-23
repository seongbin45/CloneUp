"""Discover project folders under registered scan roots (홈 목록).

Does **not** walk the whole disk. Roots = user 「찾을 위치」, or hybrid
defaults: recent folders (+ non-heavy parents), else seed dirs only.

Heavy-root (rev. 7.1): A-layer = Windows ``SHGetKnownFolderPath``
(Profile/Desktop/Documents/Downloads), fail-closed; B-layer = direct child
count ≥ T. See ``docs/BENCH_HOME_SCAN_S0.md``.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.ui.settings_store import MAX_RECENT, load_recent_folders, load_scan_roots

_log = logging.getLogger(__name__)

# Caps — keep UI responsive on beginner PCs
DEFAULT_MAX_DEPTH = 3
DEFAULT_SEED_MAX_DEPTH = 2  # heavy/seed roots walk shallower
# Registered 「찾을 위치」 non-heavy: one level deeper (plan A1; heavy locked below)
REGISTERED_MAX_DEPTH = 4
# Registered heavy roots: lock to 2 (same as seed) — S1 bench note / explode guard
REGISTERED_HEAVY_MAX_DEPTH = 2
DEFAULT_MAX_PROJECTS = 200
# Wall-clock budget for worker / incremental (includes shallow_sig stats)
SCAN_TIMEBOX_SEC = 45.0

# Dirty enrich budget (S0-locked; consumed by home_shell)
DIRTY_ENRICH_CAP = 8
DIRTY_TTL_SEC = 90
DIRTY_SELECT_DEBOUNCE_MS = 300

# B-layer: sibling-discovery priority (S0b on this PC: light≤33, heavy≥48)
HEAVY_CHILD_THRESHOLD = 48
HEAVY_CHILD_SCAN_LIMIT = 48  # scandir early-exit; intentional == T

# FOLDERID_Profile / Desktop / Documents / Downloads
_A_LAYER_FOLDER_IDS: tuple[tuple[str, str], ...] = (
    ("Profile", "5E6C858F-0E22-4760-9AFE-EA3317B67173"),
    ("Desktop", "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"),
    ("Documents", "FDD39AD0-238F-46AF-ADB4-6C85480369C7"),
    ("Downloads", "374DE290-123F-4565-9164-39C4925E467B"),
)

# Session-once A-layer: (normcase keys, fail_closed)
_A_LAYER_STATE: tuple[frozenset[str], bool] | None = None

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
    has_origin: bool | None = None  # None = unknown; False = no origin remote


@dataclass(frozen=True)
class SubPathHit:
    """A child path under a project, ranked by mtime (expand row)."""

    rel_path: str
    mtime: float


def count_direct_children(path: Path | str, *, limit: int = HEAVY_CHILD_SCAN_LIMIT) -> int:
    """Count direct children with early exit at *limit* (scandir, no recurse)."""
    try:
        p = Path(path)
    except (TypeError, ValueError):
        return 0
    n = 0
    try:
        with os.scandir(p) as it:
            for _ in it:
                n += 1
                if n >= int(limit):
                    return n
    except OSError:
        return 0
    return n


def path_norm_key(path: Path | str) -> str:
    """``resolve`` + ``os.path.normcase`` for A-layer / dedupe compares."""
    p = Path(path).expanduser().resolve()
    return os.path.normcase(str(p))


def _guid_from_str(s: str):
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", wintypes.BYTE * 8),
        ]

    u = UUID(s)
    g = GUID()
    g.Data1 = u.time_low
    g.Data2 = u.time_mid
    g.Data3 = u.time_hi_version
    for i, b in enumerate(u.bytes[8:]):
        g.Data4[i] = b
    return g


def query_known_folder_path(folder_id: str) -> str | None:
    """Injectable seam: ``SHGetKnownFolderPath`` → path string, or None.

    Lazy: does not import ctypes until called (non-Windows / tests safe).
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
    except ImportError:
        return None
    try:
        fid = _guid_from_str(folder_id)
        path_ptr = ctypes.c_wchar_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(fid), 0, None, ctypes.byref(path_ptr)
        )
        if hr != 0 or not path_ptr.value:
            return None
        try:
            return str(path_ptr.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)
    except Exception:
        return None


def reset_a_layer_cache() -> None:
    """Test helper: clear session-once A-layer state."""
    global _A_LAYER_STATE
    _A_LAYER_STATE = None


def _compute_a_layer_state() -> tuple[frozenset[str], bool]:
    """Return (normcase path keys, fail_closed)."""
    if sys.platform != "win32":
        # No Known Folder API — B-layer only (tests inject via monkeypatch).
        return frozenset(), False
    keys: set[str] = set()
    for _name, fid in _A_LAYER_FOLDER_IDS:
        raw = query_known_folder_path(fid)
        if raw is None:
            return frozenset(), True
        try:
            keys.add(path_norm_key(raw))
        except OSError:
            return frozenset(), True
    return frozenset(keys), False


def get_a_layer_state() -> tuple[frozenset[str], bool]:
    """Session-once A-set + fail-closed latch (no per-check API calls)."""
    global _A_LAYER_STATE
    if _A_LAYER_STATE is None:
        _A_LAYER_STATE = _compute_a_layer_state()
        if _A_LAYER_STATE[1]:
            _log.debug(
                "heavy-root A-layer fail-closed: SHGetKnownFolderPath "
                "failed for a required FOLDERID (Profile/Desktop/Documents/Downloads)"
            )
    return _A_LAYER_STATE


def is_heavy_scan_root(path: Path | str) -> bool:
    """True if *path* must not be an implied walk root (recent-parent trap).

    * **A:** Known Folder set (or fail-closed → always True)
    * **B:** direct children ≥ ``HEAVY_CHILD_THRESHOLD``
    """
    a_keys, fail_closed = get_a_layer_state()
    if fail_closed:
        return True
    try:
        key = path_norm_key(path)
    except OSError:
        return True
    if key in a_keys:
        return True
    try:
        p = Path(path).expanduser().resolve()
    except OSError:
        return True
    return count_direct_children(p, limit=HEAVY_CHILD_THRESHOLD) >= int(
        HEAVY_CHILD_THRESHOLD
    )


def is_broad_scan_root(path: Path | str) -> bool:
    """Alias for ``is_heavy_scan_root`` (compat)."""
    return is_heavy_scan_root(path)


def _dedupe_existing_dirs(candidates: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for c in candidates:
        try:
            key = path_norm_key(c)
            r = Path(c).expanduser().resolve()
        except OSError:
            continue
        if key in seen or not r.is_dir():
            continue
        seen.add(key)
        out.append(r)
    return out


def default_scan_roots() -> list[Path]:
    """Hybrid defaults when the user has not registered 「찾을 위치」.

    1. Each valid recent folder (up to ``MAX_RECENT``).
    2. Its parent only when the parent is **not** heavy.
    3. If no valid recent: seed Desktop/Documents/Projects/Developer only.
    """
    recent_roots: list[Path] = []
    for raw in load_recent_folders()[: int(MAX_RECENT)]:
        try:
            p = Path(raw).expanduser().resolve()
        except OSError:
            continue
        if not p.is_dir():
            continue
        recent_roots.append(p)
        parent = p.parent
        if parent != p and parent.is_dir() and not is_heavy_scan_root(parent):
            recent_roots.append(parent)

    if recent_roots:
        return _dedupe_existing_dirs(recent_roots)

    home = Path.home()
    seeds = [
        home / "Desktop",
        home / "Documents",
        home / "Projects",
        home / "Developer",
    ]
    return _dedupe_existing_dirs(seeds)


def resolve_scan_roots() -> list[Path]:
    """Registered roots if any; otherwise hybrid defaults."""
    registered = load_scan_roots()
    if registered:
        out: list[Path] = []
        seen: set[str] = set()
        for raw in registered:
            try:
                key = path_norm_key(raw)
                p = Path(raw).expanduser().resolve()
            except OSError:
                continue
            if key in seen or not p.is_dir():
                continue
            seen.add(key)
            out.append(p)
        return out or default_scan_roots()
    return default_scan_roots()


def _depth_for_root(
    root: Path,
    *,
    max_depth: int,
    registered: bool = False,
) -> int:
    """Depth cap per root. Registered non-heavy uses REGISTERED_MAX_DEPTH (4).

    Do **not** ``min`` with the caller's default ``DEFAULT_MAX_DEPTH`` (3) —
    that would silently cap registered roots at 3 (cross-verify depth-4 fail).
    """
    heavy = is_heavy_scan_root(root)
    if registered:
        if heavy:
            return int(REGISTERED_HEAVY_MAX_DEPTH)
        return int(REGISTERED_MAX_DEPTH)
    if heavy:
        return min(int(max_depth), int(DEFAULT_SEED_MAX_DEPTH))
    return int(max_depth)


def _is_unc_or_network(path: Path) -> bool:
    """Skip UNC / mapped-network style paths in background worker (S7)."""
    try:
        s = str(path.resolve())
    except OSError:
        s = str(path)
    if s.startswith("\\\\") or s.startswith("//"):
        return True
    return False


def registered_scan_root_keys() -> set[str]:
    """Normalized keys for user-registered scan roots (empty if none)."""
    keys: set[str] = set()
    for raw in load_scan_roots():
        try:
            keys.add(path_norm_key(raw))
        except OSError:
            continue
    return keys


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
    on_found: Callable[[ProjectEntry], None] | None = None,
    skip_unc: bool = False,
    timebox_sec: float | None = None,
    deadline_monotonic: float | None = None,
) -> tuple[list[ProjectEntry], bool]:
    """
    Collect project folders with budgeted discovery order (D-1b):

    * **Pass A** — pin up to ``MAX_RECENT`` recent folders first.
    * **Pass B** — walk *roots* (registered or hybrid defaults).

    Registered roots (``load_scan_roots``) allow **one level** of nested
    ``.git`` under a parent repo (C-4). Hybrid defaults keep stop-at-``.git``.

    Returns ``(entries, partial)`` where *partial* is True if a time-box cut
    the walk short.

    ``on_found`` is called for each newly added entry (discovery order).
    """
    roots = list(roots) if roots is not None else resolve_scan_roots()
    reg_keys = registered_scan_root_keys()
    found: list[ProjectEntry] = []
    seen: set[str] = set()
    partial = False
    if deadline_monotonic is None and timebox_sec is not None:
        deadline_monotonic = time.monotonic() + float(timebox_sec)

    def _timed_out() -> bool:
        nonlocal partial
        if deadline_monotonic is None:
            return False
        if time.monotonic() >= float(deadline_monotonic):
            partial = True
            return True
        return False

    def add(path: Path, *, has_git: bool) -> None:
        nonlocal found
        if len(found) >= max_projects:
            return
        try:
            key = path_norm_key(path)
        except OSError:
            return
        if key in seen:
            return
        seen.add(key)
        dirty: bool | None = None
        dirty_count = 0
        branch = ""
        has_origin: bool | None = None
        if has_git:
            has_origin = peek_has_origin(path)
            if probe_dirty:
                dirty, branch, dirty_count, origin_b = _probe_git_presence(path)
                if origin_b is not None:
                    has_origin = origin_b
        entry = ProjectEntry(
            path=str(path),
            name=path.name or str(path),
            has_git=has_git,
            last_mtime=_dir_mtime(path),
            dirty=dirty,
            dirty_count=dirty_count,
            branch=branch,
            has_origin=has_origin,
        )
        found.append(entry)
        if on_found is not None:
            try:
                on_found(entry)
            except Exception:  # noqa: BLE001
                _log.debug("on_found callback failed", exc_info=True)

    def _iter_child_dirs(current: Path) -> list[Path]:
        out: list[Path] = []
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return out
        for child in children:
            try:
                if not child.is_dir() or child.is_symlink():
                    continue
                if child.name in _SKIP_DIR_NAMES or child.name.startswith("."):
                    continue
            except OSError:
                continue
            out.append(child)
        return out

    def walk(
        current: Path,
        depth: int,
        *,
        depth_limit: int,
        allow_nested_git: bool,
    ) -> None:
        if len(found) >= max_projects or _timed_out():
            return
        if depth > depth_limit:
            return
        try:
            has_git = (current / ".git").exists()
        except OSError:
            return
        if has_git:
            add(current, has_git=True)
            if not allow_nested_git:
                return
            # C-4: one level only — direct children that are themselves git/markers
            for child in _iter_child_dirs(current):
                if len(found) >= max_projects or _timed_out():
                    return
                try:
                    child_git = (child / ".git").exists()
                except OSError:
                    continue
                if child_git:
                    add(child, has_git=True)
                    continue
                if _looks_like_project(child):
                    add(child, has_git=False)
            return
        if depth >= 1 and _looks_like_project(current):
            add(current, has_git=False)
            # still walk children for nested git repos
        for child in _iter_child_dirs(current):
            if len(found) >= max_projects or _timed_out():
                return
            walk(
                child,
                depth + 1,
                depth_limit=depth_limit,
                allow_nested_git=allow_nested_git,
            )

    # Pass A — recent pins (MAX_RECENT) occupy cap slots before any junk walk
    pin_budget = min(int(MAX_RECENT), int(max_projects))
    pinned = 0
    for raw in load_recent_folders():
        if len(found) >= max_projects or pinned >= pin_budget or _timed_out():
            break
        try:
            p = Path(raw).expanduser().resolve()
        except OSError:
            continue
        if not p.is_dir():
            continue
        try:
            has_git = (p / ".git").exists()
        except OSError:
            has_git = False
        before = len(found)
        add(p, has_git=has_git)
        if len(found) > before:
            pinned += 1

    # Pass B — walk roots (registered / hybrid)
    for root in roots:
        if len(found) >= max_projects or _timed_out():
            break
        if skip_unc and _is_unc_or_network(root):
            _log.debug("skip UNC/network root: %s", root)
            continue
        try:
            rkey = path_norm_key(root)
        except OSError:
            continue
        is_reg = rkey in reg_keys
        limit = _depth_for_root(
            root, max_depth=max_depth, registered=is_reg
        )
        walk(
            root,
            0,
            depth_limit=limit,
            allow_nested_git=is_reg,
        )

    found.sort(key=lambda e: e.last_mtime, reverse=True)
    return found, partial


def scan_projects_compat(
    roots: list[Path] | None = None,
    **kwargs: object,
) -> list[ProjectEntry]:
    """Backward-compatible wrapper returning only the entry list."""
    entries, _partial = scan_projects(roots, **kwargs)  # type: ignore[arg-type]
    return entries


def scan_projects_incremental(
    *,
    force_full: bool = False,
    probe_dirty: bool = False,
    on_found: Callable[[ProjectEntry], None] | None = None,
    skip_unc: bool = False,
    timebox_sec: float | None = SCAN_TIMEBOX_SEC,
    cache_path: Path | None = None,
) -> tuple[list[ProjectEntry], bool, object]:
    """Incremental discovery using disk cache (plan Phase C).

    Returns ``(entries, partial, cache_obj)`` where *cache_obj* is a
    ``ScanCache`` ready to save (caller holds lock).
    """
    from app.git.scan_cache import (
        RootStat,
        ScanCache,
        bump_counter_after_save,
        compute_shallow_sig,
        filter_entries_for_roots,
        load_scan_cache,
        roots_fingerprint,
        validate_entries,
    )

    roots = resolve_scan_roots()
    fp = roots_fingerprint(roots)
    prev = load_scan_cache(cache_path)
    deadline = (
        time.monotonic() + float(timebox_sec)
        if timebox_sec is not None
        else None
    )

    want_full = bool(force_full)
    prev_counter = 0
    if prev is not None:
        prev_counter = int(prev.full_scan_counter)
        if prev.needs_full_scan():
            want_full = True

    # Always compute shallow sigs inside the time-box (rev.2 note 2).
    root_stats: dict[str, RootStat] = {}
    dirty_roots: list[Path] = []
    for root in roots:
        if skip_unc and _is_unc_or_network(root):
            continue
        if deadline is not None and time.monotonic() >= deadline:
            # Time-box during sig — treat as needing walk of remaining as partial
            dirty_roots.append(root)
            continue
        try:
            key = path_norm_key(root)
        except OSError:
            continue
        sig = compute_shallow_sig(root)
        mtime = _dir_mtime(root)
        root_stats[key] = RootStat(shallow_sig=sig, mtime=mtime)
        if want_full or prev is None:
            dirty_roots.append(root)
            continue
        old = prev.root_stats.get(key)
        if old is None or old.shallow_sig != sig:
            dirty_roots.append(root)

    def _under_roots(e: ProjectEntry, root_list: list[Path]) -> bool:
        try:
            ep = Path(e.path).expanduser().resolve()
        except OSError:
            return False
        for r in root_list:
            try:
                rp = Path(r).expanduser().resolve()
            except OSError:
                continue
            if ep == rp or rp in ep.parents:
                return True
        return False

    # Seed reused entries from intersection of roots (M2)
    reused: list[ProjectEntry] = []
    if prev is not None and not want_full:
        reused = validate_entries(
            filter_entries_for_roots(prev.entries, roots)
        )
        # Drop entries under dirty roots (will be re-added by walk)
        reused = [e for e in reused if not _under_roots(e, dirty_roots)]

    # Walk only dirty roots (or all if full)
    walk_roots = list(roots) if want_full else dirty_roots
    if not walk_roots and want_full:
        walk_roots = list(roots)
    fresh, partial = scan_projects(
        walk_roots,
        probe_dirty=probe_dirty,
        on_found=on_found,
        skip_unc=skip_unc,
        deadline_monotonic=deadline,
    )

    # Merge: fresh wins over reused (dedupe by path_norm_key).
    # MUST: on partial, keep prev entries under incomplete roots so we do not
    # wipe the cache with a truncated walk (cross-verify Must-1).
    keep_prev: list[ProjectEntry] = []
    if partial and prev is not None:
        keep_prev = validate_entries(
            filter_entries_for_roots(prev.entries, roots)
        )
        if not want_full:
            # Prefer fresh for dirty roots that finished; for unfinished dirty
            # roots, prev fills gaps via keep_prev (fresh may be incomplete).
            pass

    merged: list[ProjectEntry] = []
    seen: set[str] = set()
    for e in list(fresh) + list(reused) + list(keep_prev):
        try:
            k = path_norm_key(e.path)
        except OSError:
            continue
        if k in seen:
            continue
        seen.add(k)
        merged.append(e)
    merged.sort(key=lambda e: e.last_mtime, reverse=True)
    merged = merged[: int(DEFAULT_MAX_PROJECTS)]

    # Successful full → reset counter; partial or incremental → increment
    new_counter = bump_counter_after_save(
        was_full=bool(want_full),
        was_partial=partial,
        prev_counter=prev_counter,
    )

    # root_stats: only keys for current roots (drop removed roots — SHOULD)
    current_keys: set[str] = set()
    for r in roots:
        try:
            current_keys.add(path_norm_key(r))
        except OSError:
            continue
    if prev is not None:
        for k, st in prev.root_stats.items():
            if k in current_keys and k not in root_stats:
                root_stats[k] = st
    root_stats = {k: v for k, v in root_stats.items() if k in current_keys}

    cache = ScanCache(
        version=1,
        updated_at=time.time(),
        generator="ui",
        partial=partial,
        full_scan_counter=new_counter,
        roots_fingerprint=fp,
        entries=merged,
        root_stats=root_stats,
    )

    return merged, partial, cache


def _git_dir(path: Path) -> Path | None:
    """Resolve the git directory for *path* (handles ``.git`` file / worktree)."""
    try:
        git_entry = path / ".git"
        if not git_entry.exists():
            return None
        if git_entry.is_dir():
            return git_entry
        # gitfile: "gitdir: <path>"
        text = git_entry.read_text(encoding="utf-8", errors="replace").strip()
        if not text.lower().startswith("gitdir:"):
            return None
        raw = text.split(":", 1)[1].strip()
        if not raw:
            return None
        target = Path(raw)
        if not target.is_absolute():
            target = (path / target).resolve()
        return target if target.is_dir() else None
    except OSError:
        return None


def peek_has_origin(path: Path | str) -> bool | None:
    """File-only check for ``[remote "origin"]`` in ``.git/config``.

    Returns ``True``/``False`` when config is readable, ``None`` on failure
    (missing config, unreadable, exotic layouts). Does **not** spawn git.exe.
    """
    try:
        root = Path(path)
    except (TypeError, ValueError):
        return None
    git_dir = _git_dir(root)
    if git_dir is None:
        return None
    config = git_dir / "config"
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Match common git config section headers (tolerant of spacing/case).
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("[") or not s.endswith("]"):
            continue
        inner = s[1:-1].strip().lower()
        # [remote "origin"] or [remote origin]
        if inner == 'remote "origin"' or inner == "remote origin":
            return True
    return False


def _probe_git_presence(path: Path) -> tuple[bool, str, int, bool | None]:
    """Return (dirty, branch, porcelain_count, has_origin)."""
    from app.ui.boot_scan import folder_needs_notify

    branch = ""
    count = 0
    has_origin: bool | None = None
    try:
        from app.git.sync_ops import get_repo_status

        st = get_repo_status(path)
        branch = str(getattr(st, "branch", "") or "")
        dirty = bool(folder_needs_notify(st))
        has_origin = bool(getattr(st, "has_origin", False))
    except Exception:
        return False, branch, 0, has_origin
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
        return bool(dirty or count > 0), branch, count, has_origin
    except Exception:
        return dirty, branch, count, has_origin


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
    """True when legacy tab main is active (settings + env; see ``app.ui.ui_mode``)."""
    from app.ui.ui_mode import use_legacy_tabs as _resolve

    return _resolve()


def select_dirty_enrich_paths(
    entries: list[ProjectEntry],
    *,
    cap: int = DIRTY_ENRICH_CAP,
    selected_path: str | None = None,
) -> list[str]:
    """mtime 상위 *cap* ∪ 선택 경로 (S2 initial enrich queue)."""
    ranked = sorted(
        [e for e in entries if e.has_git],
        key=lambda e: e.last_mtime,
        reverse=True,
    )
    paths = [e.path for e in ranked[: max(0, int(cap))]]
    if selected_path:
        sel = next(
            (e for e in entries if e.path == selected_path and e.has_git),
            None,
        )
        if sel is not None and sel.path not in paths:
            paths.append(sel.path)
    return paths


def dirty_probe_is_stale(
    probed_at: float | None,
    *,
    now: float,
    ttl_sec: float = DIRTY_TTL_SEC,
) -> bool:
    """True if never probed or TTL expired (S2-T3)."""
    if probed_at is None:
        return True
    return (now - probed_at) >= float(ttl_sec)
