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
