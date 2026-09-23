"""Persistent project-discovery cache (%LOCALAPPDATA%\\CloneUp\\scan_cache).

Schema v1 — see plan rev.2 (C-5, M2 fingerprint intersection).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from app.git.project_scan import ProjectEntry, path_norm_key

_log = logging.getLogger(__name__)

CACHE_VERSION = 1
FULL_SCAN_EVERY_N = 6
FULL_SCAN_MAX_AGE_SEC = 6 * 3600
GeneratorName = Literal["ui", "worker"]


def scan_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMP") or "."
    return Path(base) / "CloneUp" / "scan_cache"


def scan_cache_path() -> Path:
    return scan_cache_dir() / "projects.json"


def scan_cache_lock_path() -> Path:
    return scan_cache_dir() / ".lock"


@dataclass
class RootStat:
    shallow_sig: str
    mtime: float = 0.0


@dataclass
class ScanCache:
    version: int
    updated_at: float
    generator: str
    partial: bool
    full_scan_counter: int
    roots_fingerprint: str
    entries: list[ProjectEntry]
    root_stats: dict[str, RootStat]

    def needs_full_scan(self, *, now: float | None = None) -> bool:
        """C-11: every N runs or age > 6h."""
        t = float(now if now is not None else time.time())
        if self.full_scan_counter >= int(FULL_SCAN_EVERY_N):
            return True
        if self.updated_at and (t - float(self.updated_at)) >= float(
            FULL_SCAN_MAX_AGE_SEC
        ):
            return True
        return False


def roots_fingerprint(roots: list[Path | str]) -> str:
    keys: list[str] = []
    for r in roots:
        try:
            keys.append(path_norm_key(r))
        except OSError:
            continue
    return "|".join(sorted(set(keys)))


def compute_shallow_sig(root: Path | str) -> str:
    """Hash of direct children (name + mtime). Skip rules match project_scan."""
    from app.git.project_scan import _SKIP_DIR_NAMES

    try:
        p = Path(root)
        if not p.is_dir():
            return ""
        rows: list[str] = []
        with os.scandir(p) as it:
            for ent in it:
                name = ent.name
                if name in _SKIP_DIR_NAMES or name.startswith("."):
                    continue
                try:
                    st = ent.stat(follow_symlinks=False)
                except OSError:
                    continue
                rows.append(f"{name.lower()}:{int(st.st_mtime)}")
        rows.sort()
        blob = "\n".join(rows).encode("utf-8", errors="replace")
        return hashlib.sha256(blob).hexdigest()[:32]
    except OSError:
        return ""


def _entry_to_dict(e: ProjectEntry) -> dict[str, Any]:
    d = asdict(e)
    # JSON-friendly: keep None
    return d


def _entry_from_dict(d: dict[str, Any]) -> ProjectEntry | None:
    try:
        path = str(d.get("path") or "")
        if not path:
            return None
        has_origin = d.get("has_origin", None)
        if has_origin is not None:
            has_origin = bool(has_origin)
        dirty = d.get("dirty", None)
        if dirty is not None:
            dirty = bool(dirty)
        return ProjectEntry(
            path=path,
            name=str(d.get("name") or Path(path).name or path),
            has_git=bool(d.get("has_git")),
            last_mtime=float(d.get("last_mtime") or 0.0),
            dirty=dirty,
            dirty_count=int(d.get("dirty_count") or 0),
            branch=str(d.get("branch") or ""),
            has_origin=has_origin,
        )
    except (TypeError, ValueError):
        return None


def load_scan_cache(path: Path | None = None) -> ScanCache | None:
    """Return cache or None if missing/corrupt/wrong version."""
    p = path or scan_cache_path()
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("version") or 0) != CACHE_VERSION:
        return None
    entries_raw = data.get("entries")
    if not isinstance(entries_raw, list):
        return None
    entries: list[ProjectEntry] = []
    for item in entries_raw:
        if not isinstance(item, dict):
            continue
        e = _entry_from_dict(item)
        if e is not None:
            entries.append(e)
    stats_raw = data.get("root_stats") or {}
    root_stats: dict[str, RootStat] = {}
    if isinstance(stats_raw, dict):
        for k, v in stats_raw.items():
            if not isinstance(v, dict):
                continue
            root_stats[str(k)] = RootStat(
                shallow_sig=str(v.get("shallow_sig") or ""),
                mtime=float(v.get("mtime") or 0.0),
            )
    return ScanCache(
        version=CACHE_VERSION,
        updated_at=float(data.get("updated_at") or 0.0),
        generator=str(data.get("generator") or ""),
        partial=bool(data.get("partial")),
        full_scan_counter=int(data.get("full_scan_counter") or 0),
        roots_fingerprint=str(data.get("roots_fingerprint") or ""),
        entries=entries,
        root_stats=root_stats,
    )


def save_scan_cache(
    cache: ScanCache,
    *,
    path: Path | None = None,
) -> bool:
    """Atomic write. Caller should hold the lock. Returns False on failure."""
    p = path or scan_cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _log.debug("scan_cache mkdir failed: %s", e)
        return False
    payload = {
        "version": CACHE_VERSION,
        "updated_at": float(cache.updated_at),
        "generator": cache.generator,
        "partial": bool(cache.partial),
        "full_scan_counter": int(cache.full_scan_counter),
        "roots_fingerprint": cache.roots_fingerprint,
        "entries": [_entry_to_dict(e) for e in cache.entries],
        "root_stats": {
            k: {"shallow_sig": v.shallow_sig, "mtime": v.mtime}
            for k, v in cache.root_stats.items()
        },
    }
    tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )
        os.replace(tmp, p)
        return True
    except OSError as e:
        _log.debug("scan_cache save failed: %s", e)
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


class ScanCacheLock:
    """Non-blocking lock file. Context manager; False if not acquired."""

    def __init__(self, path: Path | None = None, *, timeout_sec: float = 0.0) -> None:
        self._path = path or scan_cache_lock_path()
        self._timeout = float(timeout_sec)
        self._fd: int | None = None
        self.acquired = False

    def acquire(self) -> bool:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        deadline = time.monotonic() + max(0.0, self._timeout)
        while True:
            try:
                # O_EXCL create — portable enough on Windows for our use
                self._fd = os.open(
                    str(self._path),
                    os.O_CREAT | os.O_EXCL | os.O_RDWR,
                )
                os.write(self._fd, str(os.getpid()).encode("ascii", errors="replace"))
                self.acquired = True
                return True
            except FileExistsError:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.05)
            except OSError:
                return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        if self.acquired:
            try:
                self._path.unlink(missing_ok=True)  # type: ignore[call-arg]
            except TypeError:
                try:
                    if self._path.exists():
                        self._path.unlink()
                except OSError:
                    pass
            except OSError:
                pass
        self.acquired = False

    def __enter__(self) -> ScanCacheLock:
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


def validate_entries(entries: list[ProjectEntry]) -> list[ProjectEntry]:
    """Drop dead paths; drop git entries whose .git vanished."""
    out: list[ProjectEntry] = []
    for e in entries:
        try:
            p = Path(e.path)
            if not p.is_dir():
                continue
            if e.has_git and not (p / ".git").exists():
                continue
            out.append(e)
        except OSError:
            continue
    return out


def entry_belongs_to_roots(
    entry: ProjectEntry, roots: list[Path | str]
) -> bool:
    """True if entry path equals or is under any root."""
    try:
        ep = Path(entry.path).expanduser().resolve()
    except OSError:
        return False
    for r in roots:
        try:
            rp = Path(r).expanduser().resolve()
        except OSError:
            continue
        if ep == rp or rp in ep.parents:
            return True
    return False


def filter_entries_for_roots(
    entries: list[ProjectEntry], roots: list[Path | str]
) -> list[ProjectEntry]:
    if not roots:
        return list(entries)
    return [e for e in entries if entry_belongs_to_roots(e, roots)]


def bump_counter_after_save(
    *,
    was_full: bool,
    was_partial: bool,
    prev_counter: int,
) -> int:
    """Successful full → 0; otherwise increment (including partial saves).

    Partial saves still increment so we eventually force full (rev.2 note 1).
    """
    if was_full and not was_partial:
        return 0
    return int(prev_counter) + 1
