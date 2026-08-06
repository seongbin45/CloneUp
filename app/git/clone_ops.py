"""git clone with optional token (private repos) — clean remote URL left in config."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.git.credentials import (
    credential_helper_configs,
    delete_credential_file,
    write_credential_file,
)
from app.git.runner import GitError, require_git, run_git
from app.git.url_utils import NormalizedCloneUrl, UrlError, normalize_github_clone_url

# Reject leading "-" (argv injection as extra git options) and odd path tricks.
_SAFE_BRANCH_RE = re.compile(r"^(?!-)[A-Za-z0-9._][A-Za-z0-9._/-]*$")


class CloneError(Exception):
    pass


def validate_branch_name(branch: str | None) -> str | None:
    """
    Return stripped branch name or None if empty.

    Raises CloneError if the name could be mis-parsed as a git option.
    """
    name = (branch or "").strip()
    if not name:
        return None
    if name in (".", "..") or ".." in name:
        raise CloneError("branch 이름이 올바르지 않습니다.")
    if name.startswith("-") or not _SAFE_BRANCH_RE.match(name):
        raise CloneError(
            f"branch 이름 「{name[:40]}」을(를) 사용할 수 없습니다.\n"
            "목록에서 고르거나, 영문·숫자·/ · _ · . 만 쓰세요."
        )
    if len(name) > 200:
        raise CloneError("branch 이름이 너무 깁니다.")
    return name


@dataclass(frozen=True)
class CloneResult:
    clone_url: str
    target_dir: Path
    owner: str
    repo: str
    warnings: tuple[str, ...]


def resolve_clone_target(
    parent_dir: Path,
    *,
    repo_name: str,
    directory_name: str | None = None,
) -> Path:
    parent = parent_dir.expanduser().resolve()
    if not parent.is_dir():
        raise CloneError(f"저장 폴더가 없습니다: {parent}")
    name = (directory_name or repo_name).strip()
    if not name or any(c in name for c in r'<>:"/\|?*'):
        raise CloneError("폴더 이름이 올바르지 않습니다.")
    target = parent / name
    if target.exists():
        raise CloneError(
            f"이미 존재하는 경로입니다: {target}\n"
            "다른 폴더 이름을 쓰거나 비어 있는 상위 폴더를 선택하세요."
        )
    return target


def clone_repository(
    raw_url: str,
    parent_dir: Path,
    *,
    directory_name: str | None = None,
    token: str | None = None,
    branch: str | None = None,
) -> CloneResult:
    """
    Clone into parent_dir/<repo or directory_name>.

    If token is provided, use temp credential helper (for private repos).
    Remote URL stored in the new repo is always the clean HTTPS URL.
    ``branch``: if set, ``git clone -b <branch> --single-branch``.
    """
    require_git()
    try:
        norm: NormalizedCloneUrl = normalize_github_clone_url(raw_url)
    except UrlError as e:
        raise CloneError(str(e)) from e

    target = resolve_clone_target(
        parent_dir, repo_name=norm.repo, directory_name=directory_name
    )

    branch_name = validate_branch_name(branch)
    # git clone [-b branch --single-branch] <url> <target>
    cred_path: str | None = None
    config = None
    try:
        if token:
            cred_path = write_credential_file(token)
            config = credential_helper_configs(cred_path)
        if branch_name:
            print(f"clone: {norm.display_url} (branch {branch_name}) → {target}")
        else:
            print(f"clone: {norm.display_url} (default branch) → {target}")
        for w in norm.warnings:
            print(f"안내: {w}")
        args = ["clone"]
        if branch_name:
            args.extend(["-b", branch_name, "--single-branch"])
        args.extend([norm.clone_url, str(target)])
        run_git(
            args,
            cwd=str(parent_dir.resolve()),
            check=True,
            config=config,
            timeout=600,
        )
    except GitError as e:
        msg = str(e)
        if branch_name and (
            "Remote branch" in msg
            or "not found" in msg.lower()
            or "did not match" in msg.lower()
        ):
            raise CloneError(
                f"branch 「{branch_name}」을(를) 찾지 못했습니다.\n"
                "이름을 확인하거나 default branch로 받아 보세요.\n\n"
                + msg[:400]
            ) from e
        raise CloneError(msg) from e
    finally:
        delete_credential_file(cred_path)

    # Verify remote is clean
    rv = run_git(["remote", "-v"], cwd=str(target), check=True)
    out = rv.stdout or ""
    if token and token in out:
        raise CloneError("보안 문제: 연결 정보가 주소에 남아 있습니다.")
    if "x-access-token" in out.lower():
        raise CloneError("보안 문제: GitHub 주소에 비밀 정보가 남아 있습니다.")

    return CloneResult(
        clone_url=norm.clone_url,
        target_dir=target,
        owner=norm.owner,
        repo=norm.repo,
        warnings=norm.warnings,
    )
