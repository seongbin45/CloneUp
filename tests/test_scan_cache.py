"""Unit tests for scan_cache + nested-git discovery (plan rev.2 S0/S1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.git.project_scan import (
    path_norm_key,
    peek_has_origin,
    scan_projects,
)
from app.git.scan_cache import (
    CACHE_VERSION,
    RootStat,
    ScanCache,
    ScanCacheLock,
    bump_counter_after_save,
    compute_shallow_sig,
    filter_entries_for_roots,
    load_scan_cache,
    roots_fingerprint,
    save_scan_cache,
    validate_entries,
)
from app.git.project_scan import ProjectEntry


def _git_repo(path: Path, *, with_origin: bool = False) -> None:
    git = path / ".git"
    git.mkdir(parents=True)
    cfg = "[core]\n\trepositoryformatversion = 0\n"
    if with_origin:
        cfg += '[remote "origin"]\n\turl = https://github.com/a/b.git\n'
    (git / "config").write_text(cfg, encoding="utf-8")


def test_bump_counter_partial_still_increments() -> None:
    assert bump_counter_after_save(was_full=True, was_partial=False, prev_counter=5) == 0
    assert bump_counter_after_save(was_full=True, was_partial=True, prev_counter=5) == 6
    assert bump_counter_after_save(was_full=False, was_partial=True, prev_counter=2) == 3


def test_scan_cache_roundtrip(tmp_path: Path) -> None:
    cache_file = tmp_path / "projects.json"
    entries = [
        ProjectEntry(str(tmp_path / "a"), "a", True, 1.0, has_origin=False),
        ProjectEntry(str(tmp_path / "b"), "b", False, 2.0),
    ]
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    cache = ScanCache(
        version=CACHE_VERSION,
        updated_at=100.0,
        generator="ui",
        partial=False,
        full_scan_counter=2,
        roots_fingerprint="x",
        entries=entries,
        root_stats={"k": RootStat(shallow_sig="abc", mtime=1.0)},
    )
    assert save_scan_cache(cache, path=cache_file)
    loaded = load_scan_cache(cache_file)
    assert loaded is not None
    assert loaded.full_scan_counter == 2
    assert len(loaded.entries) == 2
    assert loaded.root_stats["k"].shallow_sig == "abc"


def test_scan_cache_corrupt_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "projects.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_scan_cache(p) is None
    p.write_text('{"version": 99, "entries": []}', encoding="utf-8")
    assert load_scan_cache(p) is None


def test_lock_exclusive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # Force lock path under tmp via explicit path
    lock_path = tmp_path / "scan_cache" / ".lock"
    a = ScanCacheLock(lock_path)
    b = ScanCacheLock(lock_path)
    assert a.acquire()
    assert not b.acquire()
    a.release()
    assert b.acquire()
    b.release()


def test_filter_entries_intersection(tmp_path: Path) -> None:
    r1 = tmp_path / "r1"
    r2 = tmp_path / "r2"
    r1.mkdir()
    r2.mkdir()
    e1 = ProjectEntry(str(r1 / "p"), "p", True, 1.0)
    (r1 / "p").mkdir()
    e2 = ProjectEntry(str(r2 / "q"), "q", True, 1.0)
    (r2 / "q").mkdir()
    kept = filter_entries_for_roots([e1, e2], [r1])
    assert [e.name for e in kept] == ["p"]


def test_nested_git_registered_one_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.git import project_scan as ps

    root = tmp_path / "reg"
    parent = root / "mono"
    child = parent / "pkg"
    grand = child / "fixture"
    parent.mkdir(parents=True)
    child.mkdir()
    grand.mkdir()
    _git_repo(parent)
    _git_repo(child)
    _git_repo(grand)

    monkeypatch.setattr(ps, "load_recent_folders", lambda: [])
    monkeypatch.setattr(ps, "load_scan_roots", lambda: [str(root)])
    monkeypatch.setattr(ps, "resolve_scan_roots", lambda: [root])
    # Treat as registered via load_scan_roots keys
    monkeypatch.setattr(
        ps, "get_a_layer_state", lambda: (frozenset(), False)
    )

    entries, partial = scan_projects(roots=[root], probe_dirty=False)
    assert partial is False
    names = {Path(e.path).name for e in entries}
    assert "mono" in names
    assert "pkg" in names
    # 3rd level must NOT appear (1-level nested only)
    assert "fixture" not in names


def test_nested_git_hybrid_stops_at_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.git import project_scan as ps

    root = tmp_path / "hyb"
    parent = root / "mono"
    child = parent / "pkg"
    parent.mkdir(parents=True)
    child.mkdir()
    _git_repo(parent)
    _git_repo(child)

    monkeypatch.setattr(ps, "load_recent_folders", lambda: [])
    monkeypatch.setattr(ps, "load_scan_roots", lambda: [])  # not registered
    monkeypatch.setattr(ps, "get_a_layer_state", lambda: (frozenset(), False))

    entries, _ = scan_projects(roots=[root], probe_dirty=False)
    names = {Path(e.path).name for e in entries}
    assert "mono" in names
    assert "pkg" not in names


def test_shallow_sig_changes_on_direct_child(tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    s0 = compute_shallow_sig(root)
    (root / "new").mkdir()
    s1 = compute_shallow_sig(root)
    assert s0 != s1


def test_registered_depth_four_finds_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A4: registered non-heavy root reaches depth 4."""
    from app.git import project_scan as ps

    root = tmp_path / "reg"
    # root / d1 / d2 / d3 / deep  → deep is depth 4 from root
    deep = root / "d1" / "d2" / "d3" / "deep"
    deep.mkdir(parents=True)
    _git_repo(deep)

    monkeypatch.setattr(ps, "load_recent_folders", lambda: [])
    monkeypatch.setattr(ps, "load_scan_roots", lambda: [str(root)])
    monkeypatch.setattr(ps, "get_a_layer_state", lambda: (frozenset(), False))
    # Force non-heavy so REGISTERED_MAX_DEPTH=4 applies
    monkeypatch.setattr(ps, "is_heavy_scan_root", lambda _p: False)

    entries, partial = scan_projects(roots=[root], probe_dirty=False)
    assert partial is False
    assert any(Path(e.path).name == "deep" for e in entries)


def test_incremental_partial_keeps_prev_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """partial walk must not wipe prior cache entries (cross-verify Must-1)."""
    from app.git import project_scan as ps
    from app.git.project_scan import scan_projects_incremental
    from app.git.scan_cache import (
        CACHE_VERSION,
        RootStat,
        ScanCache,
        save_scan_cache,
    )

    root = tmp_path / "r"
    a = root / "keep_me"
    a.mkdir(parents=True)
    _git_repo(a)
    cache_file = tmp_path / "projects.json"
    prev = ScanCache(
        version=CACHE_VERSION,
        updated_at=1.0,
        generator="ui",
        partial=False,
        full_scan_counter=0,
        roots_fingerprint=roots_fingerprint([root]),
        entries=[
            ProjectEntry(str(a), "keep_me", True, 1.0, has_origin=False)
        ],
        root_stats={
            path_norm_key(root): RootStat(shallow_sig="old", mtime=0.0)
        },
    )
    assert save_scan_cache(prev, path=cache_file)

    monkeypatch.setattr(ps, "load_recent_folders", lambda: [])
    monkeypatch.setattr(ps, "load_scan_roots", lambda: [str(root)])
    monkeypatch.setattr(ps, "resolve_scan_roots", lambda: [root])
    monkeypatch.setattr(ps, "get_a_layer_state", lambda: (frozenset(), False))
    monkeypatch.setattr(ps, "is_heavy_scan_root", lambda _p: False)

    # Force immediate time-box so walk is partial
    entries, partial, cache = scan_projects_incremental(
        force_full=True,
        probe_dirty=False,
        timebox_sec=0.0,
        cache_path=cache_file,
    )
    assert partial is True
    names = {e.name for e in entries}
    assert "keep_me" in names
    assert cache.partial is True
