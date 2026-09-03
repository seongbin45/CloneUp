"""Probe CloneUp_update_manager health from the tray / main app.

Does not import the ``update_manager`` package (that binary is separate).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("cloneup.um_health")

UM_EXE_NAME = "CloneUp_update_manager.exe"
UM_RUN_VALUE = "CloneUpUpdateManager"
DIAG_OWNER = "seongbin45"
DIAG_REPO = "CloneUp"

# Log lines that mean the manager is alive but failing its job.
_ERROR_LINE_RE = re.compile(
    r"(install dir not found|cannot read installed version|"
    r"no usable release|no zip asset|github latest failed|"
    r"github latest HTTP|apply failed|could not stop CloneUp|"
    r"tick crashed|digest mismatch)",
    re.I,
)


def _local_app_data() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Local"


def manager_exe_path() -> Path:
    return _local_app_data() / "CloneUp" / "UpdateManager" / UM_EXE_NAME


def manager_log_path() -> Path:
    return _local_app_data() / "CloneUp" / "logs" / "update_manager.log"


def pending_diag_path() -> Path:
    return _local_app_data() / "CloneUp" / "logs" / "um_diag_pending.md"


@dataclass
class UpdateManagerHealth:
    exe_present: bool = False
    exe_path: str = ""
    run_key_present: bool = False
    run_key_value: str = ""
    process_running: bool = False
    log_present: bool = False
    log_tail: str = ""
    log_error_hits: list[str] = field(default_factory=list)
    app_install_guess: str = ""
    problems: list[str] = field(default_factory=list)
    restarted: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def signature(self) -> str:
        """Stable id for rate-limiting duplicate reports."""
        raw = "|".join(sorted(self.problems)) + "|" + ("run" if self.process_running else "stop")
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _process_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        # /FO CSV /NH — parse image name without depending on UI language.
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {UM_EXE_NAME}", "/FO", "CSV", "/NH"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        out = (r.stdout or b"").decode("utf-8", errors="replace")
        # Also try cp949 on Korean Windows if UTF-8 empty-ish
        if UM_EXE_NAME.lower() not in out.lower():
            out2 = (r.stdout or b"").decode("cp949", errors="replace")
            out = out + "\n" + out2
        return UM_EXE_NAME.lower() in out.lower()
    except Exception as e:
        log.debug("tasklist failed: %s", e)
        return False


def _read_run_key() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            val, _ = winreg.QueryValueEx(key, UM_RUN_VALUE)
            return str(val or "").strip()
    except OSError:
        return ""


def _guess_app_install() -> str:
    candidates = [
        _local_app_data() / "Programs" / "CloneUp",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "CloneUp",
    ]
    for c in candidates:
        if (c / "CloneUp.exe").is_file():
            return str(c)
    return ""


def _log_error_hits(tail: str) -> list[str]:
    hits: list[str] = []
    for line in tail.splitlines():
        if _ERROR_LINE_RE.search(line):
            hits.append(line.strip()[:240])
    # Keep last few unique
    out: list[str] = []
    for h in hits[-8:]:
        if h not in out:
            out.append(h)
    return out


def try_start_manager(exe: Path) -> bool:
    """Best-effort start when exe exists but process is down."""
    if sys.platform != "win32" or not exe.is_file():
        return False
    try:
        subprocess.Popen(  # noqa: S603
            [str(exe)],
            cwd=str(exe.parent),
            close_fds=True,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except OSError as e:
        log.warning("could not start update manager: %s", e)
        return False


def probe_update_manager(*, attempt_restart: bool = True) -> UpdateManagerHealth:
    """Inspect disk / Run / process / recent log; optionally restart once."""
    h = UpdateManagerHealth()
    exe = manager_exe_path()
    h.exe_path = str(exe)
    h.exe_present = exe.is_file()
    h.run_key_value = _read_run_key()
    h.run_key_present = bool(h.run_key_value)
    h.process_running = _process_running()
    h.app_install_guess = _guess_app_install()

    log_path = manager_log_path()
    h.log_present = log_path.is_file()
    if h.log_present:
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            h.log_tail = "\n".join(lines[-40:])
            h.log_error_hits = _log_error_hits("\n".join(lines[-120:]))
        except OSError as e:
            h.log_tail = f"(read failed: {e})"

    if attempt_restart and h.exe_present and not h.process_running:
        if try_start_manager(exe):
            h.restarted = True
            # Brief settle — caller may re-probe; we do a short recheck here.
            import time

            time.sleep(1.5)
            h.process_running = _process_running()

    if not h.exe_present:
        h.problems.append("exe_missing")
    if h.exe_present and not h.process_running:
        h.problems.append("process_not_running")
    if h.exe_present and not h.run_key_present:
        h.problems.append("run_key_missing")
    if h.log_error_hits:
        h.problems.append("log_errors")

    return h


def build_diagnostic_markdown(health: UpdateManagerHealth) -> str:
    """Human/support-facing report body (also used as GitHub issue body)."""
    from app import __version__

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "(unknown)"
    # Light redaction: keep folder shape, drop very long home paths mid-string already short.
    parts = [
        "## CloneUp update-manager auto-diagnosis",
        "",
        f"- **Reported at**: {now}",
        f"- **CloneUp app version**: `{__version__}`",
        f"- **Windows user**: `{user}`",
        f"- **LOCALAPPDATA**: `{_local_app_data()}`",
        f"- **Problems**: `{', '.join(health.problems) or 'none'}`",
        f"- **Signature**: `{health.signature}`",
        f"- **Restart attempted**: `{health.restarted}`",
        "",
        "### Probe",
        f"- exe_present: `{health.exe_present}`",
        f"- exe_path: `{health.exe_path}`",
        f"- process_running: `{health.process_running}`",
        f"- run_key_present: `{health.run_key_present}`",
        f"- run_key_value: `{health.run_key_value or '(none)'}`",
        f"- app_install_guess: `{health.app_install_guess or '(none)'}`",
        f"- log_present: `{health.log_present}`",
        "",
    ]
    if health.log_error_hits:
        parts.append("### Recent error-like log lines")
        parts.append("```")
        parts.extend(health.log_error_hits)
        parts.append("```")
        parts.append("")
    if health.log_tail.strip():
        parts.append("### Log tail")
        parts.append("```")
        parts.append(health.log_tail[:6000])
        parts.append("```")
        parts.append("")
    parts.append("---")
    parts.append("_Auto-filed by CloneUp tray when the independent update manager looks unhealthy._")
    return "\n".join(parts)


def issue_title(health: UpdateManagerHealth) -> str:
    tags = ",".join(health.problems[:3]) or "unknown"
    return f"[auto] update-manager unhealthy: {tags} ({health.signature})"
