"""
Publish a local folder to a *new empty* GitHub repo.

Security rules:
- remote URL is always clean https://github.com/owner/repo.git (no token)
- push uses a temporary credential.helper store file, deleted in finally
- token never appears in argv or .git/config
- global git config is never modified; identity injected only via -c when missing
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.git.runner import GitError, git_config_get, require_git, run_git
from app.git.safety import SafetyReport, run_safety_checks
from app.util.log_mask import mask_secrets_in_text

_TOKEN_LEAK_RE = re.compile(
    r"gho_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|x-access-token:",
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


def resolve_commit_identity(
    folder: Path,
    user: dict,
) -> list[tuple[str, str]]:
    """
    Return -c pairs for this commit only when local/global identity is missing.
    Never writes to the user's gitconfig.
    """
    # Prefer repo-local, then global (git config --get walks hierarchy if we run in repo;
    # before init, only global/system apply — we check global explicitly too).
    email = git_config_get("user.email", cwd=str(folder))
    if email is None:
        email = git_config_get("user.email", cwd=None, global_scope=True)
    name = git_config_get("user.name", cwd=str(folder))
    if name is None:
        name = git_config_get("user.name", cwd=None, global_scope=True)

    config: list[tuple[str, str]] = []
    if not name:
        config.append(("user.name", display_name(user)))
    if not email:
        config.append(("user.email", noreply_email(user)))
    return config


def assert_git_config_has_no_token(folder: Path, token: str) -> None:
    cfg = folder / ".git" / "config"
    if not cfg.is_file():
        raise PublishError(".git/config 가 없습니다 (init 실패?)")
    text = cfg.read_text(encoding="utf-8", errors="replace")
    if token and token in text:
        raise PublishError("보안 실패: 토큰이 .git/config 에 남아 있습니다.")
    if _TOKEN_LEAK_RE.search(text):
        raise PublishError("보안 실패: .git/config 에 토큰 형태 문자열이 있습니다.")
    # remote url must be clean
    if "x-access-token" in text.lower():
        raise PublishError("보안 실패: remote URL 에 x-access-token 이 있습니다.")


def _write_credential_file(token: str) -> str:
    """
    git-credential-store format (one line):
      https://x-access-token:TOKEN@github.com

    Use mkstemp (system temp). Path must be safe for git -c on Windows:
    forward slashes, no unescaped spaces issues when passed as single -c value.
    """
    fd, path = tempfile.mkstemp(prefix="cloneup-git-cred-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            # username x-access-token is GitHub's documented HTTPS token auth form
            f.write(f"https://x-access-token:{token}@github.com\n")
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def _credential_helper_configs(cred_path: str) -> list[tuple[str, str]]:
    """
    Disable inherited helpers (GCM etc.), then use store --file=<path>.

    Order matters: empty helper first clears the chain for this invocation.
    Paths: use as_posix() so git's config parser is not confused by backslashes.
    """
    posix = Path(cred_path).resolve().as_posix()
    # Single -c value: store --file=C:/Users/.../file.txt
    return [
        ("credential.helper", ""),
        ("credential.helper", f"store --file={posix}"),
    ]


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
    commit_message: str = "Initial commit",
    allow_secrets: bool = False,
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
                "이미 origin remote 가 있습니다. "
                "스파이크 3은 '새 폴더 → 새 원격' 경로만 지원합니다."
            )
        # ensure on a branch that can push; leave existing history alone
    else:
        _init_repo_main(folder)

    identity = resolve_commit_identity(folder, user)
    if identity:
        print(
            "커밋 identity 임시 주입 (-c, global 설정 변경 없음): "
            + ", ".join(f"{k}={v}" for k, v in identity)
        )
    else:
        print("기존 git user.name / user.email 사용 (존중)")

    run_git(["add", "-A"], cwd=str(folder), check=True)
    if not _has_staged_changes(folder):
        raise PublishError(
            "스테이징된 파일이 없습니다. 모든 파일이 .gitignore 되었을 수 있습니다."
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
        cred_path = _write_credential_file(token)
        helper_cfg = _credential_helper_configs(cred_path)
        print("push (임시 credential.helper store 파일, 종료 후 삭제)…")
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
            raise PublishError(
                mask_secrets_in_text(str(e))
                + " (자격증명이 필요하면 재로그인: spike_device_flow.py --force)"
            ) from e
    finally:
        if cred_path:
            try:
                os.unlink(cred_path)
            except OSError:
                pass

    assert_git_config_has_no_token(folder, token)
    # also assert remote url is clean via git remote -v
    rv = run_git(["remote", "-v"], cwd=str(folder), check=True)
    remote_out = rv.stdout or ""
    if token in remote_out or "x-access-token" in remote_out.lower():
        raise PublishError("보안 실패: git remote -v 출력에 토큰이 있습니다.")

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
    commit_message: str = "Initial commit",
    allow_secrets: bool = False,
) -> PublishResult:
    """Create empty public GitHub repo then publish_local_to_existing_remote."""
    from app.github.api_client import GitHubAPIError

    try:
        repo = create_repo_fn(
            token,
            repo_name,
            private=False,
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

    print(f"원격 저장소 생성됨: {full_name} (auto_init 없음)")
    return publish_local_to_existing_remote(
        folder,
        token=token,
        user=user,
        clone_url=clone_url,
        html_url=html_url,
        full_name=full_name,
        commit_message=commit_message,
        allow_secrets=allow_secrets,
    )
