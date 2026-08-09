"""
Publish a local folder to a *new empty* GitHub repo.

Security rules:
- remote URL is always clean https://github.com/owner/repo.git (no token)
- push uses a temporary credential.helper store file, deleted in finally
- token never appears in argv or .git/config
- global git config is never modified; identity injected only via -c when missing
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.git.credentials import (
    credential_helper_configs,
    delete_credential_file,
    write_credential_file,
)
from app.git.runner import GitError, git_config_get, require_git, run_git
from app.git.safety import SafetyReport, run_safety_checks
from app.util.log_mask import mask_secrets_in_text

# Keep in sync with app.util.log_mask (classic PAT ghp_ included — M2 review)
_TOKEN_LEAK_RE = re.compile(
    r"gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|x-access-token:",
    re.I,
)


class PublishError(Exception):
    pass


@dataclass(frozen=True)
class PublishResult:
    folder: Path
    clone_url: str
    html_url: str
    full_name: str
    commit_message: str
    safety: SafetyReport
    config_clean: bool


def noreply_email(user: dict) -> str:
    """GitHub noreply so real email is not exposed; commits still link to account."""
    user_id = user.get("id")
    login = user.get("login") or "user"
    if user_id is None:
        return f"{login}@users.noreply.github.com"
    return f"{user_id}+{login}@users.noreply.github.com"


def display_name(user: dict) -> str:
    name = (user.get("name") or "").strip()
    return name or (user.get("login") or "CloneUp User")


def peek_commit_email(folder: Path | None = None) -> str:
    """
    Email from Git config that *would* be used if we do not hide it.

    Does not invent noreply; if unset, returns a plain-language placeholder.
    """
    cwd = str(folder) if folder is not None and folder.is_dir() else None
    email = git_config_get("user.email", cwd=cwd)
    if email is None:
        email = git_config_get("user.email", cwd=None, global_scope=True)
    if email and email.strip():
        return email.strip()
    return "GitHub 로그인 후 부여되는 가림 주소 (git에 이메일이 없을 때)"


def preview_commit_email(
    folder: Path | None,
    user: dict | None,
    *,
    hide_real_email: bool,
) -> str:
    """
    What the *next* commit will show (for G3 UI).

    ``hide_real_email``: use GitHub noreply for this commit only.
    """
    if hide_real_email:
        if user:
            return noreply_email(user)
        return "GitHub 가림 주소 (연결한 계정 기준 · 올리기 때 확정)"
    # Prefer configured git email; if missing, show what we will inject.
    existing = peek_commit_email(folder)
    if existing and "가림 주소" not in existing and "로그인 후" not in existing:
        return existing
    if user:
        return noreply_email(user)
    return existing


def resolve_commit_identity(
    folder: Path,
    user: dict,
    *,
    hide_real_email: bool = False,
) -> list[tuple[str, str]]:
    """
    Return -c pairs for this commit only. Never writes to the user's gitconfig.

    ``hide_real_email``: always use GitHub noreply for author email on this
    commit, even if git user.email is set (privacy option for beginners).
    """
    email = git_config_get("user.email", cwd=str(folder))
    if email is None:
        email = git_config_get("user.email", cwd=None, global_scope=True)
    name = git_config_get("user.name", cwd=str(folder))
    if name is None:
        name = git_config_get("user.name", cwd=None, global_scope=True)

    config: list[tuple[str, str]] = []
    if not name:
        config.append(("user.name", display_name(user)))
    if hide_real_email or not email:
        config.append(("user.email", noreply_email(user)))
    return config


def assert_git_config_has_no_token(folder: Path, token: str) -> None:
    cfg = folder / ".git" / "config"
    if not cfg.is_file():
        raise PublishError("폴더 준비에 실패했습니다. 다시 시도해 주세요.")
    text = cfg.read_text(encoding="utf-8", errors="replace")
    if token and token in text:
        raise PublishError(
            "보안 문제: 연결 정보가 폴더 설정에 남아 있습니다. 다시 시도해 주세요."
        )
    if _TOKEN_LEAK_RE.search(text):
        raise PublishError(
            "보안 문제: 폴더 설정에 비밀 정보처럼 보이는 값이 있습니다."
        )
    # remote url must be clean
    if "x-access-token" in text.lower():
        raise PublishError(
            "보안 문제: GitHub 주소에 비밀 정보가 들어 있습니다."
        )


# Back-compat aliases for spikes / older imports
_write_credential_file = write_credential_file
_credential_helper_configs = credential_helper_configs


def resolve_publish_branch(raw: str | None) -> str:
    """Validate publish branch; empty → main."""
    from app.git.clone_ops import CloneError, validate_branch_name

    name = (raw or "").strip() or "main"
    try:
        validated = validate_branch_name(name)
    except CloneError as e:
        raise PublishError(str(e)) from e
    return validated or "main"


def _init_repo(folder: Path, *, branch: str = "main") -> None:
    """git init with default branch (2.28+ ``-b`` or symbolic-ref fallback)."""
    branch = resolve_publish_branch(branch)
    _, ver = require_git()
    major, minor, _ = ver
    if (major, minor) >= (2, 28):
        run_git(["init", "-b", branch], cwd=str(folder), check=True)
        return
    run_git(["init"], cwd=str(folder), check=True)
    run_git(
        ["symbolic-ref", "HEAD", f"refs/heads/{branch}"],
        cwd=str(folder),
        check=True,
    )


# Back-compat alias
_init_repo_main = _init_repo


def ensure_publish_branch(folder: Path, branch: str) -> str:
    """
    Make HEAD the chosen branch name before first commit/push.

    - No commits yet: point symbolic-ref at refs/heads/<branch>
    - Has commits: ``git branch -M <branch>`` (rename current)
    """
    branch = resolve_publish_branch(branch)
    folder = folder.expanduser().resolve()
    head = run_git(["rev-parse", "--verify", "HEAD"], cwd=str(folder), check=False)
    if head.returncode != 0:
        run_git(
            ["symbolic-ref", "HEAD", f"refs/heads/{branch}"],
            cwd=str(folder),
            check=True,
        )
        return branch
    cur = run_git(["branch", "--show-current"], cwd=str(folder), check=False)
    current = (cur.stdout or "").strip()
    if current == branch:
        return branch
    # Rename current branch (covers ensure_repo that defaulted to main)
    run_git(["branch", "-M", branch], cwd=str(folder), check=True)
    return branch


def ensure_repo_for_safety(
    folder: Path,
    *,
    write_gitignore: bool = True,
    branch: str = "main",
) -> bool:
    """
    Ensure ``.git`` exists *before* safety scans (H1 / re-review).

    ``run_safety_checks`` uses ``git ls-files --exclude-standard`` only when
    ``.git`` is present. First-time publish used to scan with a filesystem
    walk that ignored ``.gitignore`` — blocking ignored secrets permanently
    (hard content) while missing committed ones under wrong ordering.

    Returns True if this call created ``.git``.
    """
    from app.git.safety import ensure_gitignore

    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise PublishError(f"폴더가 없습니다: {folder}")
    require_git()
    branch = resolve_publish_branch(branch)
    created = False
    if not (folder / ".git").exists():
        _init_repo(folder, branch=branch)
        created = True
    else:
        # Align branch name early when still unborn / first push prep
        try:
            ensure_publish_branch(folder, branch)
        except (GitError, PublishError):
            pass
    if write_gitignore:
        ensure_gitignore(folder, write_if_missing=True)
    return created

def _has_staged_changes(folder: Path) -> bool:
    # diff --cached --quiet: exit 1 if differences, 0 if empty
    r = run_git(["diff", "--cached", "--quiet"], cwd=str(folder), check=False)
    if r.returncode == 0:
        return False
    if r.returncode == 1:
        return True
    raise GitError(
        f"git diff --cached 실패: {r.stderr or r.stdout}",
        returncode=r.returncode,
        stderr=r.stderr,
    )


def publish_local_to_existing_remote(
    folder: Path,
    *,
    token: str,
    user: dict,
    clone_url: str,
    html_url: str,
    full_name: str,
    commit_message: str = "첫 업로드",
    allow_secrets: bool = False,
    hide_real_email: bool = False,
    default_branch: str = "main",
) -> PublishResult:
    """
    Init (if needed) → safety (git-aware) → add → commit → origin → push.

    Safety must run *after* ``.git`` exists so ``.gitignore`` is honored (H1).
    """
    folder = folder.resolve()
    if not clone_url.startswith("https://github.com/"):
        raise PublishError(f"지원하지 않는 clone_url: {clone_url}")

    require_git()
    branch = resolve_publish_branch(default_branch)

    git_dir = folder / ".git"
    if git_dir.exists():
        remotes = run_git(["remote"], cwd=str(folder), check=False)
        names = {n.strip() for n in (remotes.stdout or "").splitlines() if n.strip()}
        if "origin" in names:
            raise PublishError(
                "이 폴더는 이미 GitHub와 연결되어 있습니다.\n"
                "새로 만들려면 다른 폴더를 쓰거나, 「동기화」탭에서 올리고 보내기를 사용하세요."
            )
    # Init + default .gitignore *before* safety (publish primary path)
    ensure_repo_for_safety(folder, write_gitignore=True, branch=branch)
    ensure_publish_branch(folder, branch)

    safety = run_safety_checks(
        folder,
        allow_secrets=allow_secrets,
        write_gitignore=False,  # already ensured above
    )
    if not safety.ok:
        # Keep .git so the next attempt stays gitignore-aware.
        raise PublishError("; ".join(safety.errors))

    identity = resolve_commit_identity(
        folder, user, hide_real_email=hide_real_email
    )
    if identity:
        print("작성자 정보: 이번 저장에만 적용 (PC Git 설정은 그대로)")
    else:
        print("작성자 정보: 이 PC Git 설정 사용")
    print(f"branch: {branch}")

    run_git(["add", "-A"], cwd=str(folder), check=True)
    if not _has_staged_changes(folder):
        raise PublishError(
            "올릴 파일이 없습니다.\n"
            "폴더가 비었거나, 무시 목록(.gitignore) 때문에 제외됐을 수 있습니다."
        )

    run_git(
        ["commit", "-m", commit_message],
        cwd=str(folder),
        check=True,
        config=identity or None,
    )

    # Clean remote — never embed token
    run_git(["remote", "add", "origin", clone_url], cwd=str(folder), check=True)

    cred_path: str | None = None
    try:
        cred_path = write_credential_file(token)
        helper_cfg = credential_helper_configs(cred_path)
        print("GitHub로 보내는 중…")
        try:
            run_git(
                ["push", "-u", "origin", "HEAD"],
                cwd=str(folder),
                check=True,
                config=helper_cfg,
                timeout=180,
            )
        except GitError as e:
            # surface friendly text without token
            detail = mask_secrets_in_text(str(e))
            raise PublishError(
                "GitHub로 보내기에 실패했습니다."
                # No generic "check internet" guess here — the UI layer
                # (app/util/next_action.py) derives a "다음: …" line from
                # the git detail below, which is often more specific.
                + (f"\n\n(참고)\n{detail[:500]}" if detail else "")
            ) from e
    finally:
        delete_credential_file(cred_path)

    assert_git_config_has_no_token(folder, token)
    # also assert remote url is clean via git remote -v
    rv = run_git(["remote", "-v"], cwd=str(folder), check=True)
    remote_out = rv.stdout or ""
    if token in remote_out or "x-access-token" in remote_out.lower():
        raise PublishError(
            "보안 문제: GitHub 주소에 비밀 정보가 남아 있습니다.\n"
            "이 폴더로 다시 시도하기 전에 로그를 확인하세요."
        )

    return PublishResult(
        folder=folder,
        clone_url=clone_url,
        html_url=html_url,
        full_name=full_name,
        commit_message=commit_message,
        safety=safety,
        config_clean=True,
    )


def publish_folder_to_new_repo(
    folder: Path,
    *,
    token: str,
    user: dict,
    create_repo_fn,
    repo_name: str,
    description: str = "",
    commit_message: str = "첫 업로드",
    allow_secrets: bool = False,
    private: bool = True,
    hide_real_email: bool = False,
    default_branch: str = "main",
) -> PublishResult:
    """Create empty GitHub repo (public or private) then push local history."""
    from app.github.api_client import GitHubAPIError

    try:
        repo = create_repo_fn(
            token,
            repo_name,
            private=private,
            description=description,
            auto_init=False,
        )
    except GitHubAPIError as e:
        raise PublishError(f"저장소 생성 실패: {e}") from e
    except ValueError as e:
        raise PublishError(str(e)) from e

    clone_url = repo.get("clone_url") or ""
    html_url = repo.get("html_url") or ""
    full_name = repo.get("full_name") or repo_name
    if not clone_url:
        raise PublishError("API 응답에 clone_url 이 없습니다.")

    vis = "private" if private else "public"
    print(f"원격 저장소 생성됨: {full_name} ({vis}, auto_init 없음)")
    return publish_local_to_existing_remote(
        folder,
        token=token,
        user=user,
        clone_url=clone_url,
        html_url=html_url,
        full_name=full_name,
        commit_message=commit_message,
        allow_secrets=allow_secrets,
        hide_real_email=hide_real_email,
        default_branch=default_branch,
    )
