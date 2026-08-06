"""P2 re-review: pushInsteadOf must not bypass origin host checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.git.runner import run_git
from app.git.sync_ops import SyncError, assert_safe_github_origin


def _git_ok() -> bool:
    try:
        run_git(["--version"], cwd=None, check=True)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _git_ok(), reason="git required")


@requires_git
def test_pushinsteadof_is_rejected(tmp_path: Path) -> None:
    run_git(["init", "-b", "main"], cwd=str(tmp_path), check=True)
    run_git(
        ["remote", "add", "origin", "https://github.com/victim/repo.git"],
        cwd=str(tmp_path),
        check=True,
    )
    evil = tmp_path / "evil2"
    evil.mkdir()
    # Local rewrite: fetch URL stays github.com, push goes elsewhere
    run_git(
        [
            "config",
            "--local",
            f"url.{evil.as_posix()}.pushInsteadOf",
            "https://github.com/victim/repo.git",
        ],
        cwd=str(tmp_path),
        check=True,
    )
    # fetch get-url still looks fine
    u = run_git(
        ["remote", "get-url", "origin"], cwd=str(tmp_path), check=True
    )
    assert "github.com" in (u.stdout or "")

    with pytest.raises(SyncError) as ei:
        assert_safe_github_origin(tmp_path)
    msg = str(ei.value)
    assert "url" in msg.lower() or "instead" in msg.lower() or "막" in msg


@requires_git
def test_clean_github_origin_allowed(tmp_path: Path) -> None:
    run_git(["init", "-b", "main"], cwd=str(tmp_path), check=True)
    run_git(
        ["remote", "add", "origin", "https://github.com/o/r.git"],
        cwd=str(tmp_path),
        check=True,
    )
    assert_safe_github_origin(tmp_path)  # no raise
