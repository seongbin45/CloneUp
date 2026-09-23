"""Unit tests for home project scanner (no live git required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from app.git.project_scan import (
    HEAVY_CHILD_THRESHOLD,
    count_direct_children,
    format_relative_mtime,
    is_heavy_scan_root,
    path_norm_key,
    peek_has_origin,
    reset_a_layer_cache,
    scan_projects,
    use_legacy_tabs,
)
from app.ui.settings_store import MAX_RECENT


@pytest.fixture(autouse=True)
def _clear_a_layer() -> None:
    reset_a_layer_cache()
    yield
    reset_a_layer_cache()


def _stub_a_layer(monkeypatch, keys: set[str] | frozenset[str], *, fail_closed: bool = False):
    from app.git import project_scan as ps

    frozen = frozenset(keys)
    monkeypatch.setattr(ps, "get_a_layer_state", lambda: (frozen, fail_closed))


def test_format_relative_mtime() -> None:
    now = 1_700_000_000.0
    assert format_relative_mtime(now - 30, now=now) == "방금"
    assert "분" in format_relative_mtime(now - 120, now=now)
    assert format_relative_mtime(0, now=now) == "—"


def test_scan_finds_git_repo(tmp_path: Path, monkeypatch) -> None:
    from app.git import project_scan as ps

    root = tmp_path / "work"
    repo = root / "myapp"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "README.md").write_text("x", encoding="utf-8")
    other = root / "loose"
    other.mkdir()
    (other / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(ps, "load_recent_folders", lambda: [])
    monkeypatch.setattr(ps, "resolve_scan_roots", lambda: [root])
    _stub_a_layer(monkeypatch, set())

    entries, _partial = scan_projects(probe_dirty=False)
    paths = {e.path for e in entries}
    assert str(repo.resolve()) in paths
    git_ones = [e for e in entries if e.has_git]
    assert any(Path(e.path).name == "myapp" for e in git_ones)


def test_peek_has_origin_reads_config(tmp_path: Path) -> None:
    repo = tmp_path / "local_only"
    git = repo / ".git"
    git.mkdir(parents=True)
    (git / "config").write_text(
        "[core]\n\trepositoryformatversion = 0\n"
        "[remote \"origin\"]\n\turl = https://github.com/a/b.git\n",
        encoding="utf-8",
    )
    assert peek_has_origin(repo) is True

    bare = tmp_path / "no_remote"
    g2 = bare / ".git"
    g2.mkdir(parents=True)
    (g2 / "config").write_text(
        "[core]\n\trepositoryformatversion = 0\n[branch \"main\"]\n",
        encoding="utf-8",
    )
    assert peek_has_origin(bare) is False

    missing = tmp_path / "broken"
    (missing / ".git").mkdir(parents=True)
    # no config file
    assert peek_has_origin(missing) is None


def test_scan_sets_has_origin(tmp_path: Path, monkeypatch) -> None:
    from app.git import project_scan as ps

    root = tmp_path / "work"
    with_origin = root / "with_o"
    no_origin = root / "no_o"
    for p, cfg in (
        (
            with_origin,
            '[remote "origin"]\n\turl = https://github.com/a/b.git\n',
        ),
        (no_origin, "[core]\n\trepositoryformatversion = 0\n"),
    ):
        (p / ".git").mkdir(parents=True)
        (p / ".git" / "config").write_text(cfg, encoding="utf-8")

    monkeypatch.setattr(ps, "load_recent_folders", lambda: [])
    monkeypatch.setattr(ps, "resolve_scan_roots", lambda: [root])
    _stub_a_layer(monkeypatch, set())

    entries, _partial = scan_projects(probe_dirty=False)
    by_name = {e.name: e for e in entries}
    assert by_name["with_o"].has_origin is True
    assert by_name["no_o"].has_origin is False


def test_scan_on_found_progressive(tmp_path: Path, monkeypatch) -> None:
    """on_found fires in discovery order before the sorted return."""
    from app.git import project_scan as ps

    root = tmp_path / "work"
    a = root / "alpha"
    b = root / "beta"
    for p in (a, b):
        p.mkdir(parents=True)
        (p / ".git").mkdir()

    monkeypatch.setattr(ps, "load_recent_folders", lambda: [])
    monkeypatch.setattr(ps, "resolve_scan_roots", lambda: [root])
    _stub_a_layer(monkeypatch, set())

    progressive: list[str] = []

    def on_found(entry) -> None:
        progressive.append(entry.name)

    entries, _partial = scan_projects(probe_dirty=False, on_found=on_found)
    assert "alpha" in progressive and "beta" in progressive
    assert set(progressive) == {e.name for e in entries}
    # Callback sees each entry at least once (discovery); return is sorted.
    assert len(progressive) == len(entries)


def test_count_direct_children_early_exit(tmp_path: Path) -> None:
    root = tmp_path / "many"
    root.mkdir()
    for i in range(60):
        (root / f"c{i}").mkdir()
    assert count_direct_children(root, limit=48) == 48
    assert count_direct_children(root, limit=200) == 60


def test_c4_b_layer_threshold_47_light_48_heavy(
    tmp_path: Path, monkeypatch
) -> None:
    _stub_a_layer(monkeypatch, set())
    light = tmp_path / "light"
    light.mkdir()
    for i in range(47):
        (light / f"c{i}").mkdir()
    heavy = tmp_path / "heavy"
    heavy.mkdir()
    for i in range(48):
        (heavy / f"c{i}").mkdir()
    assert HEAVY_CHILD_THRESHOLD == 48
    assert is_heavy_scan_root(light) is False
    assert is_heavy_scan_root(heavy) is True


def test_c2_a_layer_zero_children_and_normcase(
    tmp_path: Path, monkeypatch
) -> None:
    desk = tmp_path / "DesktopEmpty"
    desk.mkdir()
    key = path_norm_key(desk)
    _stub_a_layer(monkeypatch, {key})
    assert is_heavy_scan_root(desk) is True
    # trailing separator / case variant
    mixed = str(desk.resolve()) + os.sep
    assert is_heavy_scan_root(mixed) is True
    if sys.platform == "win32":
        flipped = str(desk.resolve())
        flipped = flipped.swapcase() if flipped != flipped.swapcase() else flipped
        assert is_heavy_scan_root(flipped) is True


def test_c7_fail_closed_always_heavy(tmp_path: Path, monkeypatch) -> None:
    tiny = tmp_path / "tiny"
    tiny.mkdir()
    _stub_a_layer(monkeypatch, set(), fail_closed=True)
    assert is_heavy_scan_root(tiny) is True


def _make_junction(link: Path, target: Path) -> bool:
    import subprocess

    try:
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=True,
            capture_output=True,
        )
        return link.exists()
    except (OSError, subprocess.CalledProcessError):
        return False


def test_c3_junction_to_a_path_is_heavy(tmp_path: Path, monkeypatch) -> None:
    if sys.platform != "win32":
        pytest.skip("junction fixture is Windows-only")
    real = tmp_path / "real_desktop"
    real.mkdir()
    link = tmp_path / "alias_desktop"
    if not _make_junction(link, real):
        pytest.skip("junction creation failed (permissions?)")
    key = path_norm_key(real)
    _stub_a_layer(monkeypatch, {key})
    assert is_heavy_scan_root(link) is True


def test_c3_negative_junction_to_plain_is_light(
    tmp_path: Path, monkeypatch
) -> None:
    if sys.platform != "win32":
        pytest.skip("junction fixture is Windows-only")
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "only").mkdir()
    link = tmp_path / "alias_plain"
    if not _make_junction(link, plain):
        pytest.skip("junction creation failed")
    _stub_a_layer(monkeypatch, set())
    assert is_heavy_scan_root(link) is False


def test_heavy_parent_recent_excludes_parent(
    tmp_path: Path, monkeypatch
) -> None:
    from app.git import project_scan as ps

    parent = tmp_path / "big"
    parent.mkdir()
    for i in range(HEAVY_CHILD_THRESHOLD):
        (parent / f"noise_{i}").mkdir()
    foo = parent / "Foo"
    foo.mkdir()
    (foo / ".git").mkdir()
    _stub_a_layer(monkeypatch, set())
    monkeypatch.setattr(ps, "load_recent_folders", lambda: [str(foo)])
    monkeypatch.setattr(ps, "load_scan_roots", lambda: [])

    roots = ps.default_scan_roots()
    root_keys = {path_norm_key(r) for r in roots}
    assert path_norm_key(foo) in root_keys
    assert path_norm_key(parent) not in root_keys


def test_light_parent_is_adopted_for_siblings(
    tmp_path: Path, monkeypatch
) -> None:
    from app.git import project_scan as ps

    projects = tmp_path / "Projects"
    bar = projects / "Bar"
    bar.mkdir(parents=True)
    (bar / ".git").mkdir()
    (projects / "Sibling").mkdir()
    _stub_a_layer(monkeypatch, set())
    monkeypatch.setattr(ps, "load_recent_folders", lambda: [str(bar)])
    monkeypatch.setattr(ps, "load_scan_roots", lambda: [])

    roots = ps.default_scan_roots()
    root_keys = {path_norm_key(r) for r in roots}
    assert path_norm_key(bar) in root_keys
    assert path_norm_key(projects) in root_keys


def test_s1_t2_registered_ignores_seeds(tmp_path: Path, monkeypatch) -> None:
    from app.git import project_scan as ps

    only = tmp_path / "only_root"
    only.mkdir()
    (only / ".git").mkdir()
    monkeypatch.setattr(ps, "load_recent_folders", lambda: [])
    monkeypatch.setattr(ps, "load_scan_roots", lambda: [str(only)])
    _stub_a_layer(monkeypatch, set())

    roots = ps.resolve_scan_roots()
    assert len(roots) == 1
    assert path_norm_key(roots[0]) == path_norm_key(only)


def test_s1_t3_recent_pin_survives_max_projects_junk(
    tmp_path: Path, monkeypatch
) -> None:
    from app.git import project_scan as ps

    junk_root = tmp_path / "junk"
    junk_root.mkdir()
    for i in range(15):
        d = junk_root / f"pkg_{i:02d}"
        d.mkdir()
        (d / "package.json").write_text("{}", encoding="utf-8")

    recent = tmp_path / "important_recent"
    recent.mkdir()
    (recent / ".git").mkdir()

    monkeypatch.setattr(ps, "load_recent_folders", lambda: [str(recent)])
    monkeypatch.setattr(ps, "resolve_scan_roots", lambda: [junk_root])
    _stub_a_layer(monkeypatch, set())

    entries, _partial = scan_projects(probe_dirty=False, max_projects=5)
    paths = {path_norm_key(e.path) for e in entries}
    assert path_norm_key(recent) in paths
    assert len(entries) <= 5


def test_pass_a_respects_max_recent(tmp_path: Path, monkeypatch) -> None:
    """Pass A pins at most MAX_RECENT entries."""
    from app.git import project_scan as ps

    recents: list[str] = []
    for i in range(MAX_RECENT + 5):
        d = tmp_path / f"recent_{i:03d}"
        d.mkdir()
        (d / ".git").mkdir()
        recents.append(str(d))

    sibling_root = tmp_path / "extra_root"
    discovered = sibling_root / "from_pass_b"
    discovered.mkdir(parents=True)
    (discovered / ".git").mkdir()

    monkeypatch.setattr(ps, "load_recent_folders", lambda: recents)
    monkeypatch.setattr(ps, "resolve_scan_roots", lambda: [sibling_root])
    _stub_a_layer(monkeypatch, set())

    entries, _partial = scan_projects(probe_dirty=False, max_projects=MAX_RECENT + 5)
    paths = {path_norm_key(e.path) for e in entries}
    assert path_norm_key(discovered) in paths
    assert path_norm_key(recents[0]) in paths
    assert path_norm_key(recents[MAX_RECENT - 1]) in paths
    assert path_norm_key(recents[MAX_RECENT]) not in paths


def test_use_legacy_tabs_env(monkeypatch) -> None:
    """Env force still works via ui_mode (full matrix in test_ui_mode)."""
    monkeypatch.setenv("CLONEUP_LEGACY_TABS", "1")
    assert use_legacy_tabs() is True
    monkeypatch.setenv("CLONEUP_LEGACY_TABS", "0")
    assert use_legacy_tabs() is False


def test_list_recent_child_paths(tmp_path: Path) -> None:
    from app.git.project_scan import list_recent_child_paths

    root = tmp_path / "proj"
    (root / "app" / "ui").mkdir(parents=True)
    (root / "app" / "ui" / "main.py").write_text("x", encoding="utf-8")
    (root / "README.md").write_text("r", encoding="utf-8")
    (root / ".git").mkdir()
    hits = list_recent_child_paths(root, limit=5, max_depth=2)
    rels = {h.rel_path for h in hits}
    assert "app" in rels or "app/ui" in rels or "README.md" in rels
    assert not any(r == ".git" or r.startswith(".git/") for r in rels)


def test_s2_t1_select_dirty_enrich_paths_cap() -> None:
    from app.git.project_scan import ProjectEntry, select_dirty_enrich_paths

    entries = [
        ProjectEntry(f"/p/{i}", f"p{i}", True, float(100 - i))
        for i in range(20)
    ]
    paths = select_dirty_enrich_paths(entries, cap=8)
    assert len(paths) == 8
    assert paths[0].endswith("/0")
    paths2 = select_dirty_enrich_paths(entries, cap=8, selected_path="/p/19")
    assert len(paths2) == 9
    assert "/p/19" in paths2


def test_s2_t3_dirty_probe_ttl() -> None:
    from app.git.project_scan import dirty_probe_is_stale

    now = 1_000.0
    assert dirty_probe_is_stale(None, now=now, ttl_sec=90) is True
    assert dirty_probe_is_stale(now - 30, now=now, ttl_sec=90) is False
    assert dirty_probe_is_stale(now - 91, now=now, ttl_sec=90) is True


def test_time_bucket_and_group() -> None:
    import time

    from app.git.project_scan import (
        ProjectEntry,
        group_by_time_bucket,
        time_bucket_label,
    )

    now = time.time()
    assert time_bucket_label(now - 60, now=now) == "오늘"
    assert time_bucket_label(now - 90000, now=now) in {"어제", "이번 주", "지난주"}
    entries = [
        ProjectEntry("a", "A", True, now - 100),
        ProjectEntry("b", "B", True, now - 90000),
        ProjectEntry("c", "C", False, now - 40 * 86400),
    ]
    buckets = group_by_time_bucket(entries, now=now)
    labels = [b[0] for b in buckets]
    assert "오늘" in labels
    assert "더 오래 전" in labels
