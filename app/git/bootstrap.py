"""
Git presence helpers for first-run bootstrap (plan D).

DG1: detect + open download page / optional winget install.
DG2: download official Git-*-64-bit.exe and launch installer.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.util.winproc import hidden_run_kwargs

GIT_DOWNLOAD_URL = "https://git-scm.com/download/win"
GITHUB_RELEASES_API = (
    "https://api.github.com/repos/git-for-windows/git/releases/latest"
)
_USER_AGENT = "CloneUp/0.1 (Git bootstrap; +https://github.com/seongbin45/CloneUp)"


@dataclass(frozen=True)
class GitProbe:
    ok: bool
    path: str | None = None
    version: tuple[int, int, int] | None = None
    message: str = ""


def probe_git() -> GitProbe:
    """Non-raising check: is git on PATH and runnable?"""
    # Re-scan common install dirs (PATH may lag after installer)
    _augment_path_with_common_git()
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


def _augment_path_with_common_git() -> None:
    """Prepend typical Git for Windows locations if missing from PATH."""
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "cmd",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Git"
        / "cmd",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "cmd",
    ]
    path = os.environ.get("PATH", "")
    parts = path.split(os.pathsep)
    for c in candidates:
        if not c.is_dir():
            continue
        s = str(c)
        if s not in parts and (c / "git.exe").is_file():
            os.environ["PATH"] = s + os.pathsep + path
            path = os.environ["PATH"]
            parts = path.split(os.pathsep)


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
            **hidden_run_kwargs(),
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        if r.returncode == 0:
            return True, out or "winget 설치가 완료된 것 같습니다."
        if "already installed" in out.lower() or "이미 설치" in out:
            return True, out
        return False, out or f"winget 종료 코드 {r.returncode}"
    except subprocess.TimeoutExpired:
        return False, "winget 설치 시간이 초과되었습니다."
    except Exception as e:
        return False, str(e)


# ----- DG2: download official installer -----


def resolve_latest_git_installer_url() -> tuple[str, str]:
    """
    Resolve (download_url, filename) for latest Git-*-64-bit.exe
    from git-for-windows GitHub releases.
    """
    req = urllib.request.Request(
        GITHUB_RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub releases API HTTP {e.code}") from e
    except Exception as e:
        raise RuntimeError(f"최신 Git 설치 파일 URL을 가져오지 못했습니다: {e}") from e

    assets = data.get("assets") or []
    # Prefer 64-bit setup exe (not PortableGit, not MinGit)
    preferred: list[dict] = []
    for a in assets:
        name = a.get("name") or ""
        url = a.get("browser_download_url") or ""
        if not name.endswith(".exe") or not url:
            continue
        if "Portable" in name or "MinGit" in name or "BusyBox" in name:
            continue
        if "64-bit.exe" in name and name.startswith("Git-"):
            preferred.append(a)
    if not preferred:
        # fallback: any Git-*-64-bit*
        for a in assets:
            name = a.get("name") or ""
            if "64-bit" in name and name.endswith(".exe") and "Git" in name:
                preferred.append(a)
    if not preferred:
        raise RuntimeError(
            "릴리스에서 Git 64-bit 설치 파일을 찾지 못했습니다. "
            f"브라우저에서 받아 주세요: {GIT_DOWNLOAD_URL}"
        )
    # pick first (latest release assets order is usually fine)
    a = preferred[0]
    return str(a["browser_download_url"]), str(a["name"])


def download_git_installer(
    dest_dir: Path | None = None,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    timeout: int = 120,
) -> Path:
    """
    Download latest Git for Windows installer to dest_dir (or temp).
    on_progress(bytes_read, total_or_-1).
    Returns path to .exe.
    """
    url, filename = resolve_latest_git_installer_url()
    dest_dir = dest_dir or Path(tempfile.gettempdir()) / "CloneUp-git-setup"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename

    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = -1
        cl = resp.headers.get("Content-Length")
        if cl and cl.isdigit():
            total = int(cl)
        # stream to file
        tmp = dest.with_suffix(dest.suffix + ".part")
        read = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                read += len(chunk)
                if on_progress:
                    on_progress(read, total)
        tmp.replace(dest)
    if on_progress:
        on_progress(dest.stat().st_size, dest.stat().st_size)
    return dest


def run_git_installer(installer: Path, *, silent: bool = False) -> tuple[bool, str]:
    """
    Launch Git for Windows installer.
    silent=False: normal GUI wizard (safer for beginners).
    silent=True: /VERYSILENT (may need admin).
    Returns (started_ok, message) — does not wait for full install if GUI.
    """
    if not installer.is_file():
        return False, f"설치 파일이 없습니다: {installer}"
    if sys.platform != "win32":
        return False, "Windows 전용 설치 파일입니다."

    args = [str(installer)]
    if silent:
        # Git for Windows Inno Setup flags
        args.extend(
            [
                "/VERYSILENT",
                "/NORESTART",
                "/NOCANCEL",
                "/SP-",
                "/CLOSEAPPLICATIONS",
                "/RESTARTAPPLICATIONS",
            ]
        )
    try:
        # Don't wait forever on GUI installer — start process
        if silent:
            r = subprocess.run(
                args,
                timeout=900,
                capture_output=True,
                text=True,
                **hidden_run_kwargs(),
            )
            ok = r.returncode == 0
            msg = (r.stdout or "") + (r.stderr or "") or f"exit {r.returncode}"
            return ok, msg.strip()
        # GUI installer must show its own window — do not CREATE_NO_WINDOW
        subprocess.Popen(args, shell=False)
        return True, f"설치 프로그램을 실행했습니다: {installer.name}"
    except Exception as e:
        return False, str(e)


def download_and_run_git_installer(
    *,
    silent: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """DG2 pipeline: resolve → download → run installer."""
    try:
        if log:
            log("최신 Git for Windows 설치 파일 주소를 확인합니다…")
        url, name = resolve_latest_git_installer_url()
        if log:
            log(f"다운로드: {name}")
        path = download_git_installer(on_progress=on_progress)
        if log:
            log(f"저장됨: {path} ({path.stat().st_size // (1024 * 1024)} MB)")
        ok, msg = run_git_installer(path, silent=silent)
        return ok, msg
    except Exception as e:
        return False, str(e)
