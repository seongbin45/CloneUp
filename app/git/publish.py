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


def _init_repo_main(folder: Path) -> None:
    """git init with default branch main (2.28+ or symbolic-ref fallback)."""
    _, ver = require_git()
    major, minor, _ = ver
    if (major, minor) >= (2, 28):
        run_git(["init", "-b", "main"], cwd=str(folder), check=True)
        return
    run_git(["init"], cwd=str(folder), check=True)
    run_git(["symbolic-ref", "HEAD", "refs/heads/main"], cwd=str(folder), check=True)


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
) -> PublishResult:
    """
    Init (if needed) → add → commit → remote add origin (clean) → push with temp creds.
    """
    folder = folder.resolve()
    if not clone_url.startswith("https://github.com/"):
        raise PublishError(f"지원하지 않는 clone_url: {clone_url}")

    # Git available
    require_git()

    safety = run_safety_checks(
        folder,
        allow_secrets=allow_secrets,
        write_gitignore=True,
    )
    if not safety.ok:
        raise PublishError("; ".join(safety.errors))

    git_dir = folder / ".git"
    if git_dir.exists():
        # Already a repo: only allow if no origin yet (spike path for fresh publish)
        remotes = run_git(["remote"], cwd=str(folder), check=False)
        names = {n.strip() for n in (remotes.stdout or "").splitlines() if n.strip()}
        if "origin" in names:
            raise PublishError(
                "이 폴더는 이미 GitHub와 연결되어 있습니다.\n"
                "새로 만들려면 다른 폴더를 쓰거나, 「동기화」탭에서 올리고 보내기를 사용하세요."
            )
        # ensure on a branch that can push; leave existing history alone
    else:
        _init_repo_main(folder)

    identity = resolve_commit_identity(
        folder, user, hide_real_email=hide_real_email
    )
    if identity:
        print("작성자 정보: 이번 저장에만 적용 (PC Git 설정은 그대로)")
    else:
        print("작성자 정보: 이 PC Git 설정 사용")

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
                "GitHub로 보내기에 실패했습니다.\n"
                "인터넷과 「GitHub: 연결」을 확인한 뒤 다시 올려 보세요."
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
    private: bool = False,
    hide_real_email: bool = False,
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
    )
