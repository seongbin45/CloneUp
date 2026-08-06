"""Synchronous git runner (spike). UI will later use QProcess + same args/env."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.git.env import noninteractive_git_env
from app.util.log_mask import mask_secrets_in_text
from app.util.winproc import hidden_run_kwargs


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
_empty_hooks_dir: Path | None = None


def empty_hooks_directory() -> Path:
    """
    Empty directory used as core.hooksPath so repo hooks never run (M4).

    CloneUp is not a full desktop client — we must not execute untrusted
    pre-commit hooks from a folder the user just opened.
    """
    global _empty_hooks_dir
    if _empty_hooks_dir is not None and _empty_hooks_dir.is_dir():
        return _empty_hooks_dir
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    d = Path(base) / "CloneUp" / "empty-hooks"
    d.mkdir(parents=True, exist_ok=True)
    _empty_hooks_dir = d
    return d


def safe_git_config_pairs() -> list[tuple[str, str]]:
    """
    Always-on -c overrides so a malicious .git/config cannot run helpers (M4).

    Caller-supplied config is merged *after* these (so identity / credential
    helpers still work).
    """
    hooks = empty_hooks_directory().resolve().as_posix()
    return [
        ("core.fsmonitor", ""),
        ("core.pager", "cat"),
        ("core.hooksPath", hooks),
        ("core.sshCommand", ""),
        # Avoid unexpected insteadOf / external tools from repo config affecting us
        # when we only operate over HTTPS github.com.
    ]


def _merge_config(
    extra: list[tuple[str, str]] | None,
) -> list[tuple[str, str]]:
    """Safe defaults first; later keys can override for the same git -c chain."""
    merged: list[tuple[str, str]] = list(safe_git_config_pairs())
    if extra:
        merged.extend(extra)
    return merged


def _with_commit_no_verify(args: list[str]) -> list[str]:
    """Append --no-verify to commit so hooksPath + hooks are both neutralized."""
    if not args:
        return args
    if args[0] != "commit":
        return args
    if "--no-verify" in args or "-n" in args:
        return args
    # insert after 'commit'
    return ["commit", "--no-verify", *args[1:]]


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
    safe_defaults: bool = True,
) -> GitResult:
    """
    Run `git [ -c key=value ... ] <args>`.

    Never put secrets in `args` (visible in process lists). Tokens belong in a
    credential helper file referenced only by path.

    ``safe_defaults`` (default True): inject core.hooksPath / pager / fsmonitor
    overrides and add ``commit --no-verify`` so untrusted repo config/hooks
    cannot run under CloneUp (M4 / CLONEUP_SECURITY_REVIEW).
    """
    exe = git_executable()
    use_args = _with_commit_no_verify(list(args)) if safe_defaults else list(args)
    cmd: list[str] = [exe]
    cfg = _merge_config(config) if safe_defaults else list(config or [])
    for key, value in cfg:
        cmd.extend(["-c", f"{key}={value}"])
    cmd.extend(use_args)

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
            **hidden_run_kwargs(),  # no black console flash under windowed .exe
        )
    except subprocess.TimeoutExpired as e:
        raise GitError(
            f"git 시간 초과 ({timeout}s): {' '.join(use_args)}",
            returncode=None,
            stderr="timeout",
        ) from e
    except FileNotFoundError as e:
        raise GitError("git 실행 파일을 찾을 수 없습니다.") from e

    out = proc.stdout or ""
    err = proc.stderr or ""
    # Never keep raw stderr that may embed credential-helper URLs
    safe_err = mask_secrets_in_text(err)
    safe_out = mask_secrets_in_text(out)
    if check and proc.returncode != 0:
        msg = (
            safe_err.strip()
            or safe_out.strip()
            or f"exit {proc.returncode}"
        )
        raise GitError(
            f"git {' '.join(use_args)} 실패: {msg}",
            returncode=proc.returncode,
            stderr=safe_err,
        )
    return GitResult(returncode=proc.returncode, stdout=safe_out, stderr=safe_err)


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
