"""
Git presence helpers for first-run bootstrap (plan D).

DG1: detect + open download page / optional winget install.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

GIT_DOWNLOAD_URL = "https://git-scm.com/download/win"


@dataclass(frozen=True)
class GitProbe:
    ok: bool
    path: str | None = None
    version: tuple[int, int, int] | None = None
    message: str = ""


def probe_git() -> GitProbe:
    """Non-raising check: is git on PATH and runnable?"""
    from app.git.runner import GitError, require_git

    try:
        path, ver = require_git()
        return GitProbe(
            ok=True,
            path=path,
            version=ver,
            message=f"Git {ver[0]}.{ver[1]}.{ver[2]}",
        )
    except GitError as e:
        return GitProbe(ok=False, message=str(e))
    except Exception as e:
        return GitProbe(ok=False, message=str(e))


def open_git_download_page() -> bool:
    """Open official Git for Windows download page in the default browser."""
    import webbrowser

    try:
        webbrowser.open(GIT_DOWNLOAD_URL)
        return True
    except Exception:
        return False


def winget_available() -> bool:
    return shutil.which("winget") is not None


def try_install_git_via_winget(*, timeout: int = 600) -> tuple[bool, str]:
    """
    Best-effort: winget install Git.Git (Windows).
    Returns (success, log_text). May require elevation / user consent in winget UI.
    """
    if sys.platform != "win32":
        return False, "winget 설치는 Windows 에서만 지원합니다."
    if not winget_available():
        return False, "winget 을 찾을 수 없습니다. 설치 페이지를 이용해 주세요."

    cmd = [
        "winget",
        "install",
        "--id",
        "Git.Git",
        "-e",
        "--source",
        "winget",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        # winget exit 0 = ok; also "already installed" often 0 or -1978335189
        if r.returncode == 0:
            return True, out or "winget 설치가 완료된 것 같습니다."
        # already installed
        if "already installed" in out.lower() or "이미 설치" in out:
            return True, out
        return False, out or f"winget 종료 코드 {r.returncode}"
    except subprocess.TimeoutExpired:
        return False, "winget 설치 시간이 초과되었습니다."
    except Exception as e:
        return False, str(e)
