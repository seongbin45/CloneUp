"""Unit tests for home project scanner (no live git required)."""

from __future__ import annotations

from pathlib import Path

from app.git.project_scan import (
    format_relative_mtime,
    scan_projects,
    use_legacy_tabs,
)


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

    entries = scan_projects(probe_dirty=False)
    paths = {e.path for e in entries}
    assert str(repo.resolve()) in paths
    git_ones = [e for e in entries if e.has_git]
    assert any(Path(e.path).name == "myapp" for e in git_ones)


def test_use_legacy_tabs_env(monkeypatch) -> None:
    monkeypatch.delenv("CLONEUP_LEGACY_TABS", raising=False)
    assert use_legacy_tabs() is False
    monkeypatch.setenv("CLONEUP_LEGACY_TABS", "1")
    assert use_legacy_tabs() is True


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
    # .git itself must not appear
    assert not any(r == ".git" or r.startswith(".git/") for r in rels)


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
