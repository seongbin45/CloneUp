"""
Unit tests for app/git/revert.revert_remote_commit — orchestration only.

clone_repository and revert_to_commit each have their own coverage
elsewhere (and revert_to_commit's push is untested everywhere in this repo,
same as commit_and_push — no test hits real GitHub). What's new and worth
testing here is the glue: temp dir created and always cleaned up, push_backup_branch
threaded through, CloneError turned into RevertError.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.git.revert as revert_module
from app.git.clone_ops import CloneError, CloneResult
from app.git.revert import RevertError, RevertResult, revert_remote_commit

_USER = {"id": 1, "login": "tester"}


def test_revert_remote_commit_cleans_up_and_forwards_push_backup_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_tmp_parents: list[Path] = []
    seen_revert_kwargs: dict = {}

    def fake_clone_repository(url, parent_dir, *, directory_name=None, token=None, branch=None):
        seen_tmp_parents.append(parent_dir)
        target = parent_dir / "repo"
        target.mkdir()
        (target / "marker.txt").write_text("x", encoding="utf-8")
        return CloneResult(
            clone_url=url, target_dir=target, owner="o", repo="repo", warnings=()
        )

    def fake_revert_to_commit(folder, target_rev, *, token, user, hide_real_email=False, push_backup_branch=False):
        seen_revert_kwargs.update(
            folder=folder,
            target_rev=target_rev,
            token=token,
            user=user,
            hide_real_email=hide_real_email,
            push_backup_branch=push_backup_branch,
        )
        return RevertResult(
            folder=folder,
            target_full_hash="target123",
            target_short_hash="target1",
            target_message="m",
            new_commit="new456",
            backup_branch="cloneup-backup-x",
            files=[],
        )

    monkeypatch.setattr(revert_module, "clone_repository", fake_clone_repository)
    monkeypatch.setattr(revert_module, "revert_to_commit", fake_revert_to_commit)

    result = revert_remote_commit(
        "https://github.com/o/repo.git",
        "target-rev",
        token="tok",
        user=_USER,
        hide_real_email=True,
    )

    assert result.new_commit == "new456"
    assert seen_revert_kwargs["push_backup_branch"] is True
    assert seen_revert_kwargs["target_rev"] == "target-rev"
    assert seen_revert_kwargs["hide_real_email"] is True

    assert len(seen_tmp_parents) == 1
    assert not seen_tmp_parents[0].exists(), "temp clone must be deleted after success"


def test_revert_remote_commit_cleans_up_temp_dir_on_revert_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_tmp_parents: list[Path] = []

    def fake_clone_repository(url, parent_dir, *, directory_name=None, token=None, branch=None):
        seen_tmp_parents.append(parent_dir)
        target = parent_dir / "repo"
        target.mkdir()
        return CloneResult(
            clone_url=url, target_dir=target, owner="o", repo="repo", warnings=()
        )

    def fake_revert_to_commit(*args, **kwargs):
        raise RevertError("boom")

    monkeypatch.setattr(revert_module, "clone_repository", fake_clone_repository)
    monkeypatch.setattr(revert_module, "revert_to_commit", fake_revert_to_commit)

    with pytest.raises(RevertError, match="boom"):
        revert_remote_commit(
            "https://github.com/o/repo.git", "target-rev", token="tok", user=_USER
        )

    assert not seen_tmp_parents[0].exists(), "temp clone must be deleted even on failure"


def test_revert_remote_commit_wraps_clone_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_clone_repository(*args, **kwargs):
        raise CloneError("network down")

    monkeypatch.setattr(revert_module, "clone_repository", fake_clone_repository)

    with pytest.raises(RevertError, match="임시로 받는 중"):
        revert_remote_commit(
            "https://github.com/o/repo.git", "target-rev", token="tok", user=_USER
        )
