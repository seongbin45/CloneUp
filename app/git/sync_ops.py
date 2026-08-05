"""Sync an existing local git repo: status, pull, commit+push, merge abort."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.git.credentials import (
    credential_helper_configs,
    delete_credential_file,
    write_credential_file,
)
from app.git.publish import resolve_commit_identity
from app.git.runner import require_git, run_git
from app.git.safety import find_secret_candidates


class SyncError(Exception):
    pass


@dataclass(frozen=True)
class RepoStatus:
    folder: Path
    branch: str
    has_origin: bool
    origin_url: str
    dirty: bool
    staged: bool
    untracked: bool
    ahead: int | None
    behind: int | None
    conflict: bool
    summary: str


def _ensure_git_repo(folder: Path) -> Path:
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise SyncError(f"폴더가 없습니다: {folder}")
    if not (folder / ".git").exists():
        raise SyncError(
            "Git 저장소가 아닙니다 (.git 없음).\n"
            "받기(Clone) 탭으로 받거나, 만들고 올리기 탭으로 먼저 올리세요."
        )
    require_git()
    return folder


def get_repo_status(folder: Path) -> RepoStatus:
    folder = _ensure_git_repo(folder)

    br = run_git(["branch", "--show-current"], cwd=str(folder), check=False)
    branch = (br.stdout or "").strip() or "(detached)"

    remotes = run_git(["remote"], cwd=str(folder), check=False)
    names = {n.strip() for n in (remotes.stdout or "").splitlines() if n.strip()}
    has_origin = "origin" in names
    origin_url = ""
    if has_origin:
        u = run_git(
            ["remote", "get-url", "origin"], cwd=str(folder), check=False
        )
        origin_url = (u.stdout or "").strip()

    st = run_git(["status", "--porcelain"], cwd=str(folder), check=True)
    lines = [ln for ln in (st.stdout or "").splitlines() if ln.strip()]
    dirty = any(not ln.startswith("??") for ln in lines) or any(
        ln.startswith("??") for ln in lines
    )
    staged = any(len(ln) >= 2 and ln[0] in "MADRCU" for ln in lines)
    untracked = any(ln.startswith("??") for ln in lines)
    conflict = any(
        (len(ln) >= 2 and ln[0] == "U")
        or ln.startswith("DD")
        or ln.startswith("AU")
        or ln.startswith("UD")
        or "UU" in ln[:2]
        for ln in lines
    )
    # also unmerged
    if any("U" in ln[:2] for ln in lines if len(ln) >= 2):
        conflict = True

    ahead = behind = None
    if has_origin and branch and not branch.startswith("("):
        # try fetch-less compare
        ab = run_git(
            [
                "rev-list",
                "--left-right",
                "--count",
                f"HEAD...origin/{branch}",
            ],
            cwd=str(folder),
            check=False,
        )
        if ab.returncode == 0:
            parts = (ab.stdout or "").strip().split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])

    bits = [f"브랜치: {branch}"]
    if has_origin:
        bits.append(f"origin: {origin_url or '(있음)'}")
    else:
        bits.append("origin: 없음")
    if conflict:
        bits.append("⚠ 병합 충돌 중")
    elif dirty:
        bits.append("변경 있음")
    else:
        bits.append("깨끗함")
    if ahead is not None:
        bits.append(f"ahead {ahead} / behind {behind}")

    return RepoStatus(
        folder=folder,
        branch=branch,
        has_origin=has_origin,
        origin_url=origin_url,
        dirty=bool(lines),
        staged=staged,
        untracked=untracked,
        ahead=ahead,
        behind=behind,
        conflict=conflict,
        summary=" · ".join(bits),
    )


def pull_repo(folder: Path, *, token: str | None = None) -> str:
    folder = _ensure_git_repo(folder)
    st = get_repo_status(folder)
    if st.conflict:
        raise SyncError(
            "이미 충돌 상태입니다. 「충돌 취소 (merge --abort)」를 먼저 사용하세요."
        )
    if not st.has_origin:
        raise SyncError("origin remote 가 없습니다.")

    cred_path = None
    config = None
    try:
        if token:
            cred_path = write_credential_file(token)
            config = credential_helper_configs(cred_path)
        r = run_git(
            ["pull", "--no-rebase"],
            cwd=str(folder),
            check=False,
            config=config,
            timeout=300,
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        if r.returncode != 0:
            # conflict?
            st2 = get_repo_status(folder)
            if st2.conflict:
                raise SyncError(
                    "병합 충돌이 발생했습니다.\n"
                    "이 앱으로 충돌 내용을 해결하지 않습니다.\n"
                    "「충돌 취소」로 되돌리거나, 에디터에서 수동 해결 후 커밋하세요.\n\n"
                    + out[:800]
                )
            raise SyncError(f"pull 실패:\n{out[:800]}")
        return out or "pull 완료 (이미 최신일 수 있음)"
    finally:
        delete_credential_file(cred_path)


def abort_merge(folder: Path) -> str:
    folder = _ensure_git_repo(folder)
    r = run_git(["merge", "--abort"], cwd=str(folder), check=False)
    out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
    if r.returncode != 0:
        # maybe rebase?
        r2 = run_git(["rebase", "--abort"], cwd=str(folder), check=False)
        out2 = ((r2.stdout or "") + "\n" + (r2.stderr or "")).strip()
        if r2.returncode != 0:
            raise SyncError(
                "merge/rebase abort 실패. 충돌 중이 아니거나 이미 정리됐을 수 있습니다.\n"
                + out
                + "\n"
                + out2
            )
        return out2 or "rebase --abort 완료"
    return out or "merge --abort 완료"


def commit_and_push(
    folder: Path,
    *,
    message: str,
    token: str,
    user: dict,
    allow_secrets: bool = False,
) -> str:
    folder = _ensure_git_repo(folder)
    st = get_repo_status(folder)
    if st.conflict:
        raise SyncError("충돌 상태에서는 커밋/푸시할 수 없습니다.")
    if not st.has_origin:
        raise SyncError("origin 이 없습니다. Publish 또는 remote 설정이 필요합니다.")
    if "x-access-token" in st.origin_url.lower():
        raise SyncError("origin URL 에 토큰이 있습니다. 깨끗한 HTTPS URL 로 고치세요.")

    secrets = find_secret_candidates(folder)
    if secrets and not allow_secrets:
        raise SyncError(
            "비밀 파일로 보이는 항목이 있습니다:\n"
            + ", ".join(secrets)
            + "\n제거하거나 고급 옵션으로 허용하세요."
        )

    run_git(["add", "-A"], cwd=str(folder), check=True)
    # anything staged?
    diff = run_git(["diff", "--cached", "--quiet"], cwd=str(folder), check=False)
    if diff.returncode == 0:
        # nothing to commit — still allow push of existing commits
        print("커밋할 새 변경 없음 → push 만 시도")
    else:
        msg = (message or "").strip() or "Update"
        identity = resolve_commit_identity(folder, user)
        run_git(
            ["commit", "-m", msg],
            cwd=str(folder),
            check=True,
            config=identity or None,
        )
        print(f"commit: {msg}")

    cred_path = write_credential_file(token)
    try:
        r = run_git(
            ["push", "origin", "HEAD"],
            cwd=str(folder),
            check=False,
            config=credential_helper_configs(cred_path),
            timeout=300,
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        if r.returncode != 0:
            raise SyncError(f"push 실패:\n{out[:800]}")
        return out or "push 완료"
    finally:
        delete_credential_file(cred_path)
