"""
P0 security regressions from docs/CLONEUP_SECURITY_REVIEW.md.

Expected *correct* product behavior (not today's buggy behavior):
  (a) .github/workflows AKIA must be blocked by safety
  (b) gitignored node_modules/**/credentials.js must NOT block
  (c) credential.helper must work when temp path contains spaces

Step 1 of the review: these fail on unfixed main; pass after H1/H2.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.git.credentials import (
    credential_helper_configs,
    delete_credential_file,
    write_credential_file,
)
from app.git.runner import run_git
from app.git.safety import find_secret_candidates, run_safety_checks, scan_secret_in_contents


def _git_available() -> bool:
    try:
        run_git(["--version"], cwd=None, check=True)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _git_available(), reason="git not on PATH")


# ---------------------------------------------------------------------------
# (a) H1 — real leak under .github must be blocked
# ---------------------------------------------------------------------------


def test_h1a_github_workflows_akia_is_blocked(tmp_path: Path) -> None:
    """AWS key in .github/workflows must fail safety (would be committed)."""
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "deploy.yml").write_text(
        "env:\n  AWS_KEY: 'AKIAIOSFODNN7EXAMPLE'\n",
        encoding="utf-8",
    )
    # Also a normal file so folder is not "empty"
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")

    hits = scan_secret_in_contents(tmp_path)
    kinds = {h.kind for h in hits}
    assert "aws_access_key" in kinds, (
        f"content scanner must see AKIA under .github/, got {hits!r}"
    )

    report = run_safety_checks(
        tmp_path, allow_secrets=False, write_gitignore=False
    )
    assert not report.ok, (
        "safety must FAIL when staged/publishable tree has AKIA in .github/workflows"
    )
    assert report.content_secret_hits or any(
        "비밀" in e or "내용" in e for e in report.errors
    )


# ---------------------------------------------------------------------------
# (b) H1 — gitignored credentials must not block
# ---------------------------------------------------------------------------


@requires_git
def test_h1b_gitignored_credentials_not_blocked(tmp_path: Path) -> None:
    """node_modules/.../credentials.js ignored by git must not fail safety."""
    run_git(["init", "-b", "main"], cwd=str(tmp_path), check=True)
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("app\n", encoding="utf-8")
    nm = tmp_path / "node_modules" / "foo"
    nm.mkdir(parents=True)
    (nm / "credentials.js").write_text("module.exports = {k:1}\n", encoding="utf-8")

    # Filename walk (old bug) would still list it — product must use git view
    names = find_secret_candidates(tmp_path)
    assert "node_modules/foo/credentials.js" not in names, (
        f"gitignored credentials.js must not appear in secret candidates: {names}"
    )

    report = run_safety_checks(
        tmp_path, allow_secrets=False, write_gitignore=False
    )
    assert report.ok, (
        "safety must PASS when only secret-looking path is gitignored; "
        f"errors={report.errors!r} secrets={report.secret_candidates!r}"
    )


# ---------------------------------------------------------------------------
# (c) H2 — credential helper path with spaces
# ---------------------------------------------------------------------------


@requires_git
def test_h2_credential_helper_path_with_spaces(tmp_path: Path) -> None:
    """
    git credential fill must succeed when the store file path contains spaces.

    Reproduces: store --file=/tmp/cred test dir/c.txt → usage error on git 2.x
    """
    space_dir = tmp_path / "cred test dir"
    space_dir.mkdir()
    # Use production writer pointed at spaced dir
    cred_path = write_credential_file(
        "gho_testtoken_for_space_path_only_xx",
        directory=space_dir,
    )
    try:
        assert " " in cred_path or " " in str(Path(cred_path).parent)
        helper_cfg = credential_helper_configs(cred_path)
        # Must quote the path so shell/git does not split on spaces
        store_val = helper_cfg[-1][1]
        assert "--file=" in store_val
        assert (
            "--file='" in store_val
            or '--file="' in store_val
            or "file=" in store_val and ("'" in store_val or '"' in store_val)
        ), f"path must be quoted: {store_val!r}"

        # Drive git credential fill with the same -c helper chain
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "Never"
        cmd = ["git"]
        for key, value in helper_cfg:
            cmd.extend(["-c", f"{key}={value}"])
        cmd.extend(["credential", "fill"])
        proc = subprocess.run(
            cmd,
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        assert proc.returncode == 0, (
            f"credential fill failed (rc={proc.returncode}): {out[:500]}"
        )
        assert "gho_testtoken_for_space_path_only_xx" in (proc.stdout or ""), (
            f"token not returned by helper: {proc.stdout!r}"
        )
    finally:
        delete_credential_file(cred_path)
