"""
Revert a local repo's working tree to a past commit — desin/CloneUp 커밋 내역.dc.html.

History is never rewritten:
- the current HEAD survives as (a) the new commit's parent and (b) a backup
  branch, created before anything else moves
- the target commit's *tree* is applied via ``read-tree --reset -u`` and
  committed on top of the current branch as one new commit
- push reuses the same temporary credential-file mechanism as
  app/git/sync_ops.py — token never touches argv or .git/config
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.git.credentials import (
    credential_helper_configs,
    delete_credential_file,
    write_credential_file,
)
from app.git.history import ChangedFile, changed_files_between
from app.git.publish import (
    PublishError,
    assert_git_config_has_no_token,
    resolve_commit_identity,
)
from app.git.runner import GitError, require_git, run_git
from app.git.sync_ops import SyncError, assert_safe_github_origin
from app.util.log_mask import mask_secrets_in_text


class RevertError(Exception):
    pass


@dataclass(frozen=True)
class RevertResult:
    folder: Path
    target_full_hash: str
    target_short_hash: str
    target_message: str
    new_commit: str
    backup_branch: str
    files: list[ChangedFile] = field(default_factory=list)


def _ensure_git_repo(folder: Path) -> Path:
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise RevertError(f"폴더가 없습니다: {folder}")
    if not (folder / ".git").exists():
        raise RevertError("Git 저장소가 아닙니다 (.git 없음).")
    require_git()
    return folder


def _branch_exists(folder: Path, name: str) -> bool:
    r = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{name}"],
        cwd=str(folder),
        check=False,
    )
    return r.returncode == 0


def pick_backup_branch_name(folder: Path, *, now: datetime | None = None) -> str:
    """cloneup-backup-YYYYmmdd-HHMM, de-duplicated with -2/-3/… if it exists."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    base = f"cloneup-backup-{stamp}"
    name = base
    n = 2
    while _branch_exists(folder, name):
        name = f"{base}-{n}"
        n += 1
    return name


def preview_revert(folder: str | Path, target_rev: str) -> list[ChangedFile]:
    """Files that would change if *folder* were reverted to *target_rev* now."""
    root = _ensure_git_repo(Path(folder))
    return changed_files_between(root, "HEAD", target_rev)


def revert_local_commit(
    folder: str | Path,
    target_rev: str,
    *,
    user: dict,
    hide_real_email: bool = False,
) -> RevertResult:
    """
    Local half of a revert: backup branch → read-tree reset → new commit.

    No network access (no push, no origin check) — split out from
    ``revert_to_commit`` so it can be unit-tested without a GitHub remote.
    ``RevertResult.new_commit`` is set; push is the caller's job.
    """
    root = _ensure_git_repo(Path(folder))

    status = run_git(["status", "--porcelain"], cwd=str(root), check=True)
    if (status.stdout or "").strip():
        raise RevertError(
            "저장하지 않은 변경이 있습니다.\n"
            "동기화 탭에서 먼저 올리거나 정리한 뒤 다시 시도하세요."
        )

    head = run_git(["rev-parse", "HEAD"], cwd=str(root), check=True).stdout.strip()
    try:
        target_full = run_git(
            ["rev-parse", f"{target_rev}^{{commit}}"], cwd=str(root), check=True
        ).stdout.strip()
    except GitError as e:
        raise RevertError(f"대상 커밋을 찾을 수 없습니다: {target_rev}") from e

    if target_full == head:
        raise RevertError("이미 지금 이 상태입니다.")

    files = changed_files_between(root, head, target_full)
    if not files:
        raise RevertError("바뀌는 파일이 없습니다.")

    target_short = run_git(
        ["rev-parse", "--short", target_full], cwd=str(root), check=True
    ).stdout.strip()
    target_message = run_git(
        ["log", "-1", "--format=%s", target_full], cwd=str(root), check=True
    ).stdout.strip()

    backup_branch = pick_backup_branch_name(root)
    run_git(["branch", backup_branch, head], cwd=str(root), check=True)

    try:
        run_git(["read-tree", "--reset", "-u", target_full], cwd=str(root), check=True)
    except GitError as e:
        # Best-effort: put the working tree back the way it was.
        run_git(["read-tree", "--reset", "-u", head], cwd=str(root), check=False)
        raise RevertError(f"되돌리기 실패 (작업 폴더 복구 시도함): {e}") from e

    identity = resolve_commit_identity(root, user, hide_real_email=hide_real_email)
    message = f'"{target_message}" 시점으로 되돌림 ({target_short})'
    try:
        run_git(
            ["commit", "-m", message],
            cwd=str(root),
            check=True,
            config=identity or None,
        )
    except GitError as e:
        run_git(["read-tree", "--reset", "-u", head], cwd=str(root), check=False)
        raise RevertError(f"되돌리기 커밋 실패 (작업 폴더 복구 시도함): {e}") from e

    new_commit = run_git(["rev-parse", "HEAD"], cwd=str(root), check=True).stdout.strip()

    return RevertResult(
        folder=root,
        target_full_hash=target_full,
        target_short_hash=target_short,
        target_message=target_message,
        new_commit=new_commit,
        backup_branch=backup_branch,
        files=files,
    )


def revert_to_commit(
    folder: str | Path,
    target_rev: str,
    *,
    token: str,
    user: dict,
    hide_real_email: bool = False,
) -> RevertResult:
    """
    Revert *folder* to *target_rev*'s tree as one new commit, then push.

    Requires a clean working tree first, so the tree swap can't silently
    discard unsaved work — callers should point the user at the sync tab.
    """
    root = _ensure_git_repo(Path(folder))
    try:
        assert_safe_github_origin(root)
    except SyncError as e:
        raise RevertError(str(e)) from e

    result = revert_local_commit(
        root, target_rev, user=user, hide_real_email=hide_real_email
    )

    cred_path = write_credential_file(token)
    try:
        r = run_git(
            ["push", "origin", "HEAD"],
            cwd=str(root),
            check=False,
            config=credential_helper_configs(cred_path),
            timeout=300,
        )
        if r.returncode != 0:
            out = mask_secrets_in_text(
                ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
            )
            raise RevertError(
                "되돌린 내용을 새 커밋으로 저장했지만 GitHub로 보내지 못했습니다.\n"
                f"새 커밋: {result.new_commit[:7]} · 백업 브랜치: {result.backup_branch}\n"
                "인터넷 연결을 확인한 뒤 동기화 탭의 「올리고 보내기」로 다시 보내세요."
                + (f"\n\n(참고)\n{out[:400]}" if out else "")
            )
    finally:
        delete_credential_file(cred_path)

    try:
        assert_git_config_has_no_token(root, token)
    except PublishError as e:
        raise RevertError(str(e)) from e

    return result
