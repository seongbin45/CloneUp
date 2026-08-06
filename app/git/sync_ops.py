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
from app.git.url_utils import UrlError, assert_github_https_remote


class SyncError(Exception):
    pass


def _assert_safe_origin(origin_url: str) -> None:
    """URL-string check only (no local url.* rewrite detection)."""
    try:
        assert_github_https_remote(origin_url, what="origin")
    except UrlError as e:
        raise SyncError(str(e)) from e


def assert_safe_github_origin(folder: Path) -> None:
    """
    Block push/pull when origin is not clean GitHub HTTPS (P2 re-review).

    - Inspect both fetch and push URLs (``get-url`` / ``get-url --push``).
      ``pushInsteadOf`` rewrites only the push URL and bypasses fetch-only checks.
    - Reject any local ``url.*`` config (insteadOf / pushInsteadOf).
    """
    folder = folder.expanduser().resolve()
    # Local rewrite rules — any url.<base>.insteadOf / pushInsteadOf
    reg = run_git(
        ["config", "--local", "--get-regexp", r"^url\."],
        cwd=str(folder),
        check=False,
    )
    if reg.returncode == 0 and (reg.stdout or "").strip():
        raise SyncError(
            "이 폴더의 Git 설정에 url.* 주소 바꾸기(insteadOf/pushInsteadOf)가 있습니다.\n"
            "CloneUp은 안전을 위해 동기화를 막습니다.\n"
            "의심되면 다른 폴더에서 다시 받거나, 해당 url.* 설정을 제거하세요."
        )

    fetch = run_git(
        ["remote", "get-url", "origin"], cwd=str(folder), check=False
    )
    push = run_git(
        ["remote", "get-url", "--push", "origin"], cwd=str(folder), check=False
    )
    fetch_url = (fetch.stdout or "").strip()
    push_url = (push.stdout or "").strip() or fetch_url
    if not fetch_url and not push_url:
        raise SyncError("origin 주소를 읽을 수 없습니다.")
    try:
        if fetch_url:
            assert_github_https_remote(fetch_url, what="origin(fetch)")
        if push_url:
            assert_github_https_remote(push_url, what="origin(push)")
    except UrlError as e:
        raise SyncError(str(e)) from e


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

    # Beginner-facing summary (branch is shown separately in UI as 「현재 branch」)
    bits: list[str] = []

    if has_origin:
        bits.append("GitHub와 연결됨")
    else:
        bits.append("GitHub 연결 없음")

    if conflict:
        bits.append("⚠ 변경이 겹쳐 막힘")
    elif dirty:
        bits.append("저장할 변경 있음")
    else:
        bits.append("로컬 변경 없음")

    if ahead is not None and behind is not None:
        if ahead == 0 and behind == 0:
            bits.append("GitHub와 같음")
        else:
            parts_ab: list[str] = []
            if ahead:
                parts_ab.append(f"올릴 내용 {ahead}개")
            if behind:
                parts_ab.append(f"받을 내용 {behind}개")
            if parts_ab:
                bits.append(" · ".join(parts_ab))

    if not bits:
        bits.append("상태 확인됨")

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


def _git_detail(out: str, *, limit: int = 500) -> str:
    """Short optional technical detail for dialogs (not the main sentence)."""
    text = (out or "").strip()
    if not text:
        return ""
    return "\n\n(참고)\n" + text[:limit]


def pull_repo(folder: Path, *, token: str | None = None) -> str:
    folder = _ensure_git_repo(folder)
    st = get_repo_status(folder)
    if st.conflict:
        raise SyncError(
            "이미 변경이 겹쳐 막힌 상태입니다.\n"
            "먼저 「충돌 취소」로 되돌린 뒤 다시 받아 오세요."
        )
    if not st.has_origin:
        raise SyncError(
            "이 폴더는 아직 GitHub와 연결되어 있지 않습니다.\n"
            "「만들고 올리기」로 먼저 올리거나, 「받기」로 받은 폴더를 선택하세요."
        )
    assert_safe_github_origin(folder)

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
                    "GitHub 내용과 이 폴더 내용이 겹쳐 자동으로 합치지 못했습니다.\n"
                    "「충돌 취소」로 되돌리거나, 다른 프로그램에서 파일을 고친 뒤 다시 올리세요."
                    + _git_detail(out)
                )
            raise SyncError(
                "GitHub에서 받아오기에 실패했습니다.\n"
                "인터넷과 「GitHub: 연결」을 확인한 뒤 다시 시도하세요."
                + _git_detail(out)
            )
        if out and ("Already up to date" in out or "이미 업데이트" in out):
            return "이미 최신입니다. 받을 새 내용이 없습니다."
        return "받아오기가 끝났습니다." if not out else f"받아오기 완료.\n{out[:400]}"
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
                "겹친 상태를 되돌리지 못했습니다.\n"
                "이미 정리됐거나, 충돌 중이 아닐 수 있습니다."
                + _git_detail(out + "\n" + out2)
            )
        return "겹친 상태를 되돌렸습니다."
    return "겹친 상태를 되돌렸습니다."


def commit_and_push(
    folder: Path,
    *,
    message: str,
    token: str,
    user: dict,
    allow_secrets: bool = False,
    hide_real_email: bool = False,
) -> str:
    folder = _ensure_git_repo(folder)
    st = get_repo_status(folder)
    if st.conflict:
        raise SyncError(
            "변경이 겹쳐 막힌 상태에서는 올릴 수 없습니다.\n"
            "「충돌 취소」로 되돌린 뒤 다시 시도하세요."
        )
    if not st.has_origin:
        raise SyncError(
            "이 폴더는 아직 GitHub와 연결되어 있지 않습니다.\n"
            "「만들고 올리기」로 먼저 올리거나, 「받기」로 받은 폴더를 선택하세요."
        )
    assert_safe_github_origin(folder)

    # Prefer full safety report (publishable paths + hard content keys).
    from app.git.safety import run_safety_checks

    safety = run_safety_checks(
        folder,
        allow_secrets=allow_secrets,
        write_gitignore=False,
        scan_pii=False,
    )
    if not safety.ok:
        raise SyncError(
            "비밀 파일·내용 검사에 걸렸습니다:\n"
            + "\n".join(safety.errors[:5])
            + "\n파일을 고친 뒤 다시 시도하세요."
            + (
                ""
                if not allow_secrets
                else "\n(고급 허용이 켜져 있어도 키·인증서 내용은 막을 수 없습니다.)"
            )
        )

    run_git(["add", "-A"], cwd=str(folder), check=True)
    # anything staged?
    diff = run_git(["diff", "--cached", "--quiet"], cwd=str(folder), check=False)
    if diff.returncode == 0:
        # nothing to commit — still allow push of existing commits
        print("새로 저장할 변경 없음 → GitHub로 보내기만 시도")
    else:
        msg = (message or "").strip() or "변경 사항 반영"
        identity = resolve_commit_identity(
            folder, user, hide_real_email=hide_real_email
        )
        run_git(
            ["commit", "-m", msg],
            cwd=str(folder),
            check=True,
            config=identity or None,
        )
        print(f"저장 완료: {msg}")

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
            raise SyncError(
                "GitHub로 보내기에 실패했습니다.\n"
                "인터넷과 「GitHub: 연결」을 확인한 뒤 다시 시도하세요."
                + _git_detail(out)
            )
        return "GitHub로 보내기가 끝났습니다."
    finally:
        delete_credential_file(cred_path)
