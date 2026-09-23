"""Publish must work for local-only git (has commits, no origin)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.git.runner import run_git
from app.git.publish import PublishError, publish_local_to_existing_remote


def _local_only_repo(tmp: Path) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    run_git(["init"], cwd=str(tmp), check=True)
    run_git(["config", "user.email", "t@example.com"], cwd=str(tmp), check=True)
    run_git(["config", "user.name", "Test"], cwd=str(tmp), check=True)
    (tmp / "readme.txt").write_text("hello\n", encoding="utf-8")
    run_git(["add", "readme.txt"], cwd=str(tmp), check=True)
    run_git(["commit", "-m", "init"], cwd=str(tmp), check=True)
    # no origin
    return tmp


def test_publish_local_only_skips_empty_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clean local history + no origin must not raise '올릴 파일이 없습니다'."""
    repo = _local_only_repo(tmp_path / "proj")

    pushes: list[list[str]] = []

    def fake_run_git(args, *, cwd=None, check=True, config=None, timeout=None):
        from app.git.runner import GitResult, run_git as real

        cmd = list(args)
        if cmd[:1] == ["push"] or (len(cmd) >= 1 and cmd[0] == "push"):
            pushes.append(cmd)
            return GitResult(0, "", "")
        if cmd[:2] == ["remote", "add"] or cmd[:2] == ["remote", "set-url"]:
            return real(cmd, cwd=cwd, check=check)
        return real(cmd, cwd=cwd, check=check, config=config, timeout=timeout)

    monkeypatch.setattr("app.git.publish.run_git", fake_run_git)
    monkeypatch.setattr(
        "app.git.publish.write_credential_file", lambda _t: None
    )
    monkeypatch.setattr(
        "app.git.publish.credential_helper_configs", lambda _p: []
    )
    monkeypatch.setattr(
        "app.git.publish.delete_credential_file", lambda _p: None
    )
    monkeypatch.setattr(
        "app.git.publish.assert_git_config_has_no_token",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "app.git.publish.run_safety_checks",
        lambda *_a, **_k: type("R", (), {"ok": True, "errors": []})(),
    )
    monkeypatch.setattr(
        "app.git.publish.resolve_commit_identity", lambda *_a, **_k: None
    )

    result = publish_local_to_existing_remote(
        repo,
        token="ghp_testtoken_not_real_xxxxxx",
        user={"login": "me", "id": 1},
        clone_url="https://github.com/me/proj.git",
        html_url="https://github.com/me/proj",
        full_name="me/proj",
        commit_message="첫 업로드",
        allow_secrets=True,
    )
    assert result.full_name == "me/proj"
    assert pushes, "expected a push of existing HEAD"
    # origin should now be set
    r = run_git(["remote", "get-url", "origin"], cwd=str(repo), check=False)
    assert "github.com/me/proj" in (r.stdout or "")


def test_publish_reuses_empty_existing_github_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """422 name-exists + empty remote → push into that repo (retry path)."""
    from app.github.api_client import GitHubAPIError
    from app.git.publish import publish_folder_to_new_repo

    repo = _local_only_repo(tmp_path / "proj2")
    pushes: list[list[str]] = []

    def boom_create(*_a, **_k):
        raise GitHubAPIError(422, "same name already exists on this account")

    def fake_run_git(args, *, cwd=None, check=True, config=None, timeout=None):
        from app.git.runner import GitResult, run_git as real

        cmd = list(args)
        if cmd and cmd[0] == "push":
            pushes.append(cmd)
            return GitResult(0, "", "")
        if cmd[:2] in (["remote", "add"], ["remote", "set-url"]):
            return real(cmd, cwd=cwd, check=check)
        return real(cmd, cwd=cwd, check=check, config=config, timeout=timeout)

    monkeypatch.setattr("app.git.publish.run_git", fake_run_git)
    monkeypatch.setattr("app.git.publish.write_credential_file", lambda _t: None)
    monkeypatch.setattr(
        "app.git.publish.credential_helper_configs", lambda _p: []
    )
    monkeypatch.setattr(
        "app.git.publish.delete_credential_file", lambda _p: None
    )
    monkeypatch.setattr(
        "app.git.publish.assert_git_config_has_no_token",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "app.git.publish.run_safety_checks",
        lambda *_a, **_k: type("R", (), {"ok": True, "errors": []})(),
    )
    monkeypatch.setattr(
        "app.git.publish.resolve_commit_identity", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "app.github.api_client.get_repo",
        lambda owner, name, access_token=None: {
            "full_name": f"{owner}/{name}",
            "clone_url": f"https://github.com/{owner}/{name}.git",
            "html_url": f"https://github.com/{owner}/{name}",
            "size": 0,
        },
    )

    result = publish_folder_to_new_repo(
        repo,
        token="ghp_testtoken_not_real_xxxxxx",
        user={"login": "me", "id": 1},
        create_repo_fn=boom_create,
        repo_name="proj2",
        allow_secrets=True,
    )
    assert result.full_name == "me/proj2"
    assert pushes


def test_publish_still_errors_when_no_commits_and_no_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    run_git(["init"], cwd=str(empty), check=True)
    run_git(["config", "user.email", "t@example.com"], cwd=str(empty), check=True)
    run_git(["config", "user.name", "Test"], cwd=str(empty), check=True)

    monkeypatch.setattr(
        "app.git.publish.run_safety_checks",
        lambda *_a, **_k: type("R", (), {"ok": True, "errors": []})(),
    )
    monkeypatch.setattr(
        "app.git.publish.resolve_commit_identity", lambda *_a, **_k: None
    )
    # Do not auto-create .gitignore — keep the tree truly empty of tracked files.
    monkeypatch.setattr(
        "app.git.publish.ensure_repo_for_safety",
        lambda folder, **_k: False,
    )
    monkeypatch.setattr(
        "app.git.publish.ensure_publish_branch",
        lambda folder, branch: branch,
    )

    with pytest.raises(PublishError, match="올릴 파일"):
        publish_local_to_existing_remote(
            empty,
            token="ghp_testtoken_not_real_xxxxxx",
            user={"login": "me", "id": 1},
            clone_url="https://github.com/me/empty.git",
            html_url="https://github.com/me/empty",
            full_name="me/empty",
            allow_secrets=True,
        )
