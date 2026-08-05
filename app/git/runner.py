"""Synchronous git runner (spike). UI will later use QProcess + same args/env."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

from app.git.env import noninteractive_git_env
from app.util.log_mask import mask_secrets_in_text


class GitError(Exception):
    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str


_VERSION_RE = re.compile(r"git version (\d+)\.(\d+)(?:\.(\d+))?")


def git_executable() -> str:
    path = shutil.which("git")
    if not path:
        raise GitError(
            "Git이 설치되어 있지 않거나 PATH에 없습니다. "
            "https://git-scm.com/download/win 에서 설치하세요."
        )
    return path


def parse_git_version(version_stdout: str) -> tuple[int, int, int]:
    m = _VERSION_RE.search(version_stdout)
    if not m:
        raise GitError(f"Git 버전을 파싱할 수 없습니다: {version_stdout!r}")
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return major, minor, patch


def require_git() -> tuple[str, tuple[int, int, int]]:
    exe = git_executable()
    r = run_git(["--version"], cwd=None, check=True)
    ver = parse_git_version(r.stdout or r.stderr)
    return exe, ver


def run_git(
    args: list[str],
    *,
    cwd: str | None,
    check: bool = True,
    extra_env: dict[str, str] | None = None,
    config: list[tuple[str, str]] | None = None,
    timeout: int = 120,
) -> GitResult:
    """
    Run `git [ -c key=value ... ] <args>`.

    Never put secrets in `args` (visible in process lists). Tokens belong in a
    credential helper file referenced only by path.
    """
    exe = git_executable()
    cmd: list[str] = [exe]
    if config:
        for key, value in config:
            cmd.extend(["-c", f"{key}={value}"])
    cmd.extend(args)

    env = noninteractive_git_env()
    if extra_env:
        env.update(extra_env)

    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise GitError(
            f"git 시간 초과 ({timeout}s): {' '.join(args)}",
            returncode=None,
            stderr="timeout",
        ) from e
    except FileNotFoundError as e:
        raise GitError("git 실행 파일을 찾을 수 없습니다.") from e

    out = proc.stdout or ""
    err = proc.stderr or ""
    if check and proc.returncode != 0:
        msg = mask_secrets_in_text(
            err.strip() or out.strip() or f"exit {proc.returncode}"
        )
        raise GitError(
            f"git {' '.join(args)} 실패: {msg}",
            returncode=proc.returncode,
            stderr=err,
        )
    return GitResult(returncode=proc.returncode, stdout=out, stderr=err)


def git_config_get(key: str, *, cwd: str | None, global_scope: bool = False) -> str | None:
    args = ["config"]
    if global_scope:
        args.append("--global")
    args.extend(["--get", key])
    r = run_git(args, cwd=cwd, check=False)
    if r.returncode != 0:
        return None
    val = (r.stdout or "").strip()
    return val or None
