"""
H1 re-review: first-time publish path (.git missing) must honor .gitignore.

Previous bug: safety ran before git init → filesystem walk listed ignored
files; hard content block could not be bypassed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.git.publish import ensure_repo_for_safety
from app.git.runner import run_git
from app.git.safety import list_publishable_relpaths, run_safety_checks


def _git_ok() -> bool:
    try:
        run_git(["--version"], cwd=None, check=True)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _git_ok(), reason="git required")


@requires_git
def test_h1_publish_path_ignores_gitignored_akia_without_prior_init(
    tmp_path: Path,
) -> None:
    """
    Simulate 「만들고 올리기」 on a brand-new folder (no .git yet).

    After ensure_repo_for_safety (as publish/UI now do), AKIA under an ignored
    tree must not block; only real publishable files are scanned.
    """
    (tmp_path / ".gitignore").write_text("local/\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    local = tmp_path / "local"
    local.mkdir()
    (local / "notes.txt").write_text(
        "AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n",
        encoding="utf-8",
    )

    assert not (tmp_path / ".git").exists()

    # Without prepare: may still list ignored files (documents the bug class)
    paths_before, _ = list_publishable_relpaths(tmp_path)
    # After prepare: git-aware
    ensure_repo_for_safety(tmp_path, write_gitignore=False)
    assert (tmp_path / ".git").is_dir()

    paths, _ = list_publishable_relpaths(tmp_path)
    assert "main.py" in paths or any(p.endswith("main.py") for p in paths)
    assert not any(p.replace("\\", "/").startswith("local/") for p in paths), paths

    report = run_safety_checks(
        tmp_path, allow_secrets=False, write_gitignore=False
    )
    assert report.ok, (
        "gitignored AKIA must not fail safety after ensure_repo_for_safety; "
        f"errors={report.errors!r} paths_before={paths_before!r} paths={paths!r}"
    )


@requires_git
def test_h1_github_workflows_still_blocked_after_ensure(tmp_path: Path) -> None:
    """Committed .github secrets must still hard-block after git init."""
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "deploy.yml").write_text(
        "env:\n  AWS_KEY: 'AKIAIOSFODNN7EXAMPLE'\n",
        encoding="utf-8",
    )
    ensure_repo_for_safety(tmp_path, write_gitignore=False)
    report = run_safety_checks(
        tmp_path, allow_secrets=True, write_gitignore=False
    )
    assert not report.ok
    assert report.content_secret_hits
