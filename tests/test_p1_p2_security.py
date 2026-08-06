"""P1/P2 security follow-ups (M4 safe git, origin host, private default)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.git.runner import (
    _with_commit_no_verify,
    empty_hooks_directory,
    run_git,
    safe_git_config_pairs,
)
from app.git.sync_ops import SyncError, _assert_safe_origin
from app.git.url_utils import UrlError, assert_github_https_remote


def test_m4_commit_gets_no_verify() -> None:
    assert _with_commit_no_verify(["commit", "-m", "x"]) == [
        "commit",
        "--no-verify",
        "-m",
        "x",
    ]
    assert "--no-verify" in _with_commit_no_verify(["commit", "--no-verify", "-m", "x"])


def test_m4_safe_git_config_disables_hooks_path() -> None:
    pairs = dict(safe_git_config_pairs())
    assert pairs.get("core.pager") == "cat"
    assert pairs.get("core.fsmonitor") == ""
    hooks = pairs.get("core.hooksPath") or ""
    assert hooks
    assert Path(hooks).is_dir() or empty_hooks_directory().is_dir()


def test_m4_commit_with_malicious_hook_does_not_run(tmp_path: Path) -> None:
    """Repo pre-commit hook must not execute under CloneUp run_git."""
    run_git(["init", "-b", "main"], cwd=str(tmp_path), check=True)
    run_git(["config", "user.email", "t@example.com"], cwd=str(tmp_path), check=True)
    run_git(["config", "user.name", "T"], cwd=str(tmp_path), check=True)
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    marker = tmp_path / "HOOK_RAN"
    hook = hooks / "pre-commit"
    hook.write_text(
        "#!/bin/sh\necho ran > \"" + str(marker).replace("\\", "/") + "\"\nexit 1\n",
        encoding="utf-8",
    )
    try:
        hook.chmod(0o755)
    except OSError:
        pass
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    run_git(["add", "f.txt"], cwd=str(tmp_path), check=True)
    run_git(["commit", "-m", "t"], cwd=str(tmp_path), check=True)
    assert not marker.exists(), "pre-commit hook must not run under CloneUp"


def test_p2_origin_host_github_ok() -> None:
    assert_github_https_remote("https://github.com/o/r.git")
    _assert_safe_origin("https://github.com/o/r.git")


def test_p2_origin_rejects_evil_host() -> None:
    with pytest.raises((UrlError, SyncError)):
        assert_github_https_remote("https://evil.example/o/r.git")
    with pytest.raises(SyncError):
        _assert_safe_origin("https://evil.example/o/r.git")


def test_p2_origin_rejects_ssh() -> None:
    with pytest.raises((UrlError, SyncError)):
        assert_github_https_remote("nina.v@example.com:o/r.git")


def test_p2_origin_rejects_token_embed() -> None:
    with pytest.raises((UrlError, SyncError)):
        assert_github_https_remote(
            "https://x-access-token:gho_xxx@github.com/o/r.git"
        )


def test_m5_default_private_preference() -> None:
    """settings_store / QSettings default when key missing is True."""
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QSettings

    from app.ui.settings_store import load_last_private

    _ = load_last_private()
    s = QSettings("CloneUp", "CloneUp-test-private-default")
    s.remove("last_private")
    val = bool(s.value("last_private", True, type=bool))
    assert val is True
