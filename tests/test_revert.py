"""Unit tests for app/git/revert.py (local half only — no network/push)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.git.revert import (
    RevertError,
    pick_backup_branch_name,
    preview_revert,
    revert_local_commit,
)
from app.git.runner import run_git

_USER = {"id": 1, "login": "tester"}


def _git_ok() -> bool:
    try:
        run_git(["--version"], cwd=None, check=True)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _git_ok(), reason="git required")


def _commit(folder: Path, message: str) -> str:
    run_git(["add", "-A"], cwd=str(folder), check=True)
    run_git(["commit", "-m", message], cwd=str(folder), check=True)
    return run_git(["rev-parse", "HEAD"], cwd=str(folder), check=True).stdout.strip()


def _init_two_commit_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """
    c1: a.txt=one, b.txt=keep-me
    c2 (HEAD): a.txt=two, b.txt deleted

    Reverting HEAD -> c1 should modify a.txt and bring b.txt back.
    """
    run_git(["init", "-b", "main"], cwd=str(tmp_path), check=True)
    run_git(["config", "user.name", "Tester"], cwd=str(tmp_path), check=True)
    run_git(
        ["config", "user.email", "tester@example.com"], cwd=str(tmp_path), check=True
    )

    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("keep-me\n", encoding="utf-8")
    c1 = _commit(tmp_path, "c1")

    (tmp_path / "a.txt").write_text("two\n", encoding="utf-8")
    (tmp_path / "b.txt").unlink()
    c2 = _commit(tmp_path, "c2")

    return tmp_path, c1, c2


@requires_git
def test_preview_revert_reports_expected_kinds(tmp_path: Path) -> None:
    folder, c1, c2 = _init_two_commit_repo(tmp_path)
    files = {f.path: f.kind for f in preview_revert(folder, c1)}
    assert files["a.txt"] == "M"
    assert files["b.txt"] == "A"  # missing from HEAD, present in target → revert adds it

    # read-only: HEAD must not move
    head = run_git(["rev-parse", "HEAD"], cwd=str(folder), check=True).stdout.strip()
    assert head == c2


@requires_git
def test_revert_local_commit_restores_tree_and_keeps_history(
    tmp_path: Path,
) -> None:
    folder, c1, c2 = _init_two_commit_repo(tmp_path)

    result = revert_local_commit(folder, c1, user=_USER)

    assert result.target_full_hash == c1
    assert (folder / "a.txt").read_text(encoding="utf-8") == "one\n"
    assert (folder / "b.txt").read_text(encoding="utf-8") == "keep-me\n"

    # New commit on top of c2 — no history rewritten.
    parent = run_git(
        ["rev-parse", "HEAD~1"], cwd=str(folder), check=True
    ).stdout.strip()
    assert parent == c2
    assert result.new_commit != c2

    # Backup branch preserves the pre-revert HEAD.
    backup_sha = run_git(
        ["rev-parse", result.backup_branch], cwd=str(folder), check=True
    ).stdout.strip()
    assert backup_sha == c2

    kinds = {f.path: f.kind for f in result.files}
    assert kinds == {"a.txt": "M", "b.txt": "A"}

    # Working tree is clean after the revert commit.
    status = run_git(["status", "--porcelain"], cwd=str(folder), check=True)
    assert not (status.stdout or "").strip()


@requires_git
def test_revert_rejects_self_revert(tmp_path: Path) -> None:
    folder, c1, c2 = _init_two_commit_repo(tmp_path)
    with pytest.raises(RevertError, match="이미 지금"):
        revert_local_commit(folder, "HEAD", user=_USER)


@requires_git
def test_revert_rejects_dirty_working_tree(tmp_path: Path) -> None:
    folder, c1, c2 = _init_two_commit_repo(tmp_path)
    (folder / "c.txt").write_text("uncommitted\n", encoding="utf-8")

    branches_before = run_git(
        ["branch", "--list"], cwd=str(folder), check=True
    ).stdout
    with pytest.raises(RevertError, match="저장하지 않은"):
        revert_local_commit(folder, c1, user=_USER)

    # Must fail before touching anything: no backup branch, file still there.
    branches_after = run_git(
        ["branch", "--list"], cwd=str(folder), check=True
    ).stdout
    assert branches_before == branches_after
    assert (folder / "c.txt").exists()


@requires_git
def test_pick_backup_branch_name_dedupes(tmp_path: Path) -> None:
    from datetime import datetime

    run_git(["init", "-b", "main"], cwd=str(tmp_path), check=True)
    run_git(["config", "user.name", "Tester"], cwd=str(tmp_path), check=True)
    run_git(
        ["config", "user.email", "tester@example.com"], cwd=str(tmp_path), check=True
    )
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    _commit(tmp_path, "c1")

    fixed_now = datetime(2026, 8, 7, 16, 15)
    first = pick_backup_branch_name(tmp_path, now=fixed_now)
    run_git(["branch", first, "HEAD"], cwd=str(tmp_path), check=True)

    second = pick_backup_branch_name(tmp_path, now=fixed_now)
    assert second != first
    assert second == f"{first}-2"
