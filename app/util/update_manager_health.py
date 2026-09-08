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

# Soft: transient network / no-release noise — show in log UI but do NOT
# mark the manager "unhealthy" when exe+process are otherwise fine.
_SOFT_LOG_RE = re.compile(
    r"(no usable release|github latest failed|github latest HTTP|"
    r"apply failed:.*(timed out|timeout|handshake))",
    re.I,
)
# Hard: real failures a beginner should act on (non-timeout apply failures).
_HARD_LOG_RE = re.compile(
    r"(install dir not found|cannot read installed version|"
    r"no zip asset|could not stop CloneUp|"
    r"tick crashed|digest mismatch|"
    r"apply failed(?!:.*(timed out|timeout|handshake)))",
    re.I,
)
# Union used when collecting hits for the log panel.
_ERROR_LINE_RE = re.compile(
    r"(no usable release|github latest failed|github latest HTTP|"
    r"install dir not found|cannot read installed version|"
    r"no zip asset|apply failed|could not stop CloneUp|"
    r"tick crashed|digest mismatch)",
    re.I,
)


def _local_app_data() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Local"


def _program_data() -> Path:
    base = os.environ.get("PROGRAMDATA")
    if base:
        return Path(base)
    return Path(r"C:\ProgramData")


def manager_exe_path() -> Path:
    """Prefer ProgramData (admin install), then legacy per-user LocalAppData."""
    candidates = (
        _program_data() / "CloneUp" / "UpdateManager" / UM_EXE_NAME,
        _local_app_data() / "CloneUp" / "UpdateManager" / UM_EXE_NAME,
    )
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return candidates[0]


def manager_log_path() -> Path:
    # Logs stay per-user (writable without admin).
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
    # Full layered dump (Python mirror of diagnose_update_manager.ps1 + optional PS stdout).
    extended_diag: str = ""

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
        from app.util.winproc import hidden_run_kwargs

        # /FO CSV /NH — parse image name without depending on UI language.
        # CREATE_NO_WINDOW: GUI CloneUp must not flash a black console for tasklist.
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {UM_EXE_NAME}", "/FO", "CSV", "/NH"],
            capture_output=True,
            timeout=15,
            check=False,
            **hidden_run_kwargs(),
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


def _scheduled_task_command() -> str:
    """Return TR of schtasks CloneUpUpdateManager when registered (0.1.12+)."""
    if sys.platform != "win32":
        return ""
    try:
        from app.util.winproc import hidden_run_kwargs

        r = subprocess.run(
            ["schtasks", "/Query", "/TN", "CloneUpUpdateManager", "/FO", "LIST", "/V"],
            capture_output=True,
            timeout=20,
            check=False,
            **hidden_run_kwargs(),
        )
        text = (r.stdout or b"").decode("utf-8", errors="replace")
        if r.returncode != 0:
            text += "\n" + (r.stdout or b"").decode("cp949", errors="replace")
        for line in text.splitlines():
            low = line.lower()
            # English: "Task To Run:"; Korean locale often "실행할 작업:"
            if "task to run" in low or "실행할 작업" in line or "실행할 프로그램" in line:
                _, _, rest = line.partition(":")
                return rest.strip().strip('"')
        if r.returncode == 0 and UM_EXE_NAME.lower() in text.lower():
            return f"(scheduled task present; {UM_EXE_NAME})"
    except Exception as e:
        log.debug("schtasks query failed: %s", e)
    return ""


def _read_run_key() -> str:
    """Prefer Scheduled Task (SYSTEM); fall back to HKLM/HKCU Run (legacy)."""
    task_tr = _scheduled_task_command()
    if task_tr:
        return task_tr
    if sys.platform != "win32":
        return ""
    try:
        import winreg
    except Exception:
        return ""
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(
                hive,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
            ) as key:
                val, _ = winreg.QueryValueEx(key, UM_RUN_VALUE)
                s = str(val or "").strip()
                if s:
                    return s
        except OSError:
            continue
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


def _drop_superseded_apply_failures(
    recent_lines: list[str], hard_hits: list[str]
) -> list[str]:
    """Ignore apply failures that were followed by a later ``success`` in the window."""
    if not hard_hits or not recent_lines:
        return hard_hits
    last_success = -1
    for i, line in enumerate(recent_lines):
        if " INFO success " in line or re.search(r"\bsuccess\b.+\u2192|\bsuccess\b.+->", line):
            last_success = i
    if last_success < 0:
        return hard_hits
    kept: list[str] = []
    for hit in hard_hits:
        if "apply failed" not in hit.lower():
            kept.append(hit)
            continue
        # Find last matching line index for this hit snippet
        idx = -1
        needle = hit[:60]
        for i, line in enumerate(recent_lines):
            if needle and needle in line:
                idx = i
        if idx >= 0 and idx < last_success:
            continue
        kept.append(hit)
    return kept


def try_start_manager(exe: Path, *, once: bool = False) -> bool:
    """Best-effort start when exe exists but process is down (or run ``--once``)."""
    if sys.platform != "win32" or not exe.is_file():
        return False
    try:
        from app.util.winproc import hidden_run_kwargs

        kw = hidden_run_kwargs()
        flags = int(kw.get("creationflags", 0)) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        cmd = [str(exe)]
        if once:
            cmd.append("--once")
        subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(exe.parent),
            close_fds=True,
            creationflags=flags,
            startupinfo=kw.get("startupinfo"),
        )
        return True
    except OSError as e:
        log.warning("could not start update manager: %s", e)
        return False


def _find_diagnose_script() -> Path | None:
    """Locate diagnose_update_manager.ps1 (install tree, frozen, or repo)."""
    candidates: list[Path] = []
    # Next to CloneUp.exe (we copy scripts\ into {app}\scripts on build).
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "scripts" / "diagnose_update_manager.ps1")
    # Dev / editable: repo root scripts/
    here = Path(__file__).resolve()
    # app/util/update_manager_health.py → repo root
    candidates.append(here.parents[2] / "scripts" / "diagnose_update_manager.ps1")
    # Beside guessed install
    guess = _guess_app_install()
    if guess:
        candidates.append(Path(guess) / "scripts" / "diagnose_update_manager.ps1")
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def run_diagnose_script(*, timeout_sec: int = 45) -> str:
    """
    Run scripts/diagnose_update_manager.ps1 when present; return stdout/stderr.
    Empty string if unavailable or failed hard.
    """
    script = _find_diagnose_script()
    if script is None or sys.platform != "win32":
        return ""
    try:
        from app.util.winproc import hidden_run_kwargs

        # Windowed CloneUp + bare powershell = black console flash — always hide.
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            capture_output=True,
            timeout=timeout_sec,
            check=False,
            **hidden_run_kwargs(),
        )
        out = (r.stdout or b"").decode("utf-8", errors="replace")
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        header = f"(script: {script} exit={r.returncode})\n"
        text = header + out
        if err.strip():
            text += "\n--- stderr ---\n" + err
        # Cap for GitHub issue body budget
        return text[:12000]
    except Exception as e:
        return f"(diagnose script failed: {e})"


def collect_extended_diag_text(health: UpdateManagerHealth) -> str:
    """
    Python mirror of diagnose_update_manager.ps1 layers + optional PS output.
    Always available even when the .ps1 was not bundled.
    """
    lines: list[str] = []
    lines.append("=== Extended probe (Python) ===")
    lines.append(f"Time          : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"User          : {os.environ.get('USERNAME') or '(unknown)'}")
    lines.append(f"UserProfile   : {os.environ.get('USERPROFILE') or ''}")
    lines.append(f"LOCALAPPDATA  : {_local_app_data()}")
    is_admin = False
    if sys.platform == "win32":
        try:
            import ctypes

            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            pass
    lines.append(f"IsAdmin token : {is_admin}")
    lines.append("")
    lines.append("--- Layer 1: file on disk ---")
    lines.append(f"Expected exe  : {health.exe_path}")
    lines.append(f"STATUS        : {'PRESENT' if health.exe_present else 'MISSING'}")
    lines.append("")
    lines.append("--- Layer 2: HKCU Run ---")
    lines.append(f"Run value     : {health.run_key_value or '(absent)'}")
    lines.append("")
    lines.append("--- Layer 3: process / log ---")
    lines.append(f"Process       : {'RUNNING' if health.process_running else 'not running'}")
    lines.append(f"Log present   : {health.log_present}")
    if health.log_error_hits:
        lines.append("Error-like hits:")
        lines.extend(f"  {h}" for h in health.log_error_hits)
    lines.append("")
    lines.append("--- Layer 4: app install guess ---")
    lines.append(f"app_install   : {health.app_install_guess or '(none)'}")
    # ARP
    if sys.platform == "win32":
        try:
            import winreg

            app_id = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{A7C1E0B2-4D5F-4A8E-9C3B-1F2E3D4C5B6A}_is1"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, app_id) as key:
                loc, _ = winreg.QueryValueEx(key, "InstallLocation")
                ver, _ = winreg.QueryValueEx(key, "DisplayVersion")
                lines.append(f"ARP InstallLocation: {loc}")
                lines.append(f"ARP DisplayVersion : {ver}")
        except OSError:
            lines.append("ARP HKCU uninstall key: missing")
    lines.append("")
    lines.append("--- Layer 5: other profiles / MotW hints ---")
    other: list[str] = []
    users = Path(r"C:\Users")
    if users.is_dir():
        try:
            for child in users.iterdir():
                if not child.is_dir():
                    continue
                p = child / "AppData" / "Local" / "CloneUp" / "UpdateManager" / UM_EXE_NAME
                try:
                    if not p.is_file():
                        continue
                    if health.exe_present and health.exe_path:
                        if p.resolve() == Path(health.exe_path).resolve():
                            continue
                    other.append(str(p))
                except OSError:
                    continue
        except OSError:
            pass
    if other:
        lines.append("Updater under OTHER profiles:")
        lines.extend(f"  {p}" for p in other[:8])
    else:
        lines.append("No updater under other C:\\Users\\* profiles (or access denied).")
    if health.exe_present and sys.platform == "win32":
        try:
            from app.util.winproc import hidden_run_kwargs

            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    f'Get-Item -LiteralPath "{health.exe_path}" -Stream Zone.Identifier -ErrorAction SilentlyContinue | Out-String',
                ],
                capture_output=True,
                timeout=15,
                check=False,
                **hidden_run_kwargs(),
            )
            z = (r.stdout or b"").decode("utf-8", errors="replace").strip()
            lines.append(f"Mark-of-the-Web: {'present' if z else 'none'}")
        except Exception:
            lines.append("Mark-of-the-Web: (unreadable)")
    lines.append("")
    lines.append(f"Problems: {', '.join(health.problems) or 'none'}")

    ps_out = run_diagnose_script()
    if ps_out.strip():
        lines.append("")
        lines.append("=== diagnose_update_manager.ps1 output ===")
        lines.append(ps_out)
    else:
        lines.append("")
        lines.append("(diagnose_update_manager.ps1 not found or empty — Python probe only)")
    return "\n".join(lines)


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
    recent_lines: list[str] = []
    if h.log_present:
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            h.log_tail = "\n".join(lines[-40:])
            recent_lines = lines[-120:]
            h.log_error_hits = _log_error_hits("\n".join(recent_lines))
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
    hard_hits = [
        x
        for x in h.log_error_hits
        if _HARD_LOG_RE.search(x) and not _SOFT_LOG_RE.search(x)
    ]
    hard_hits = _drop_superseded_apply_failures(recent_lines, hard_hits)
    soft_hits = [
        x
        for x in h.log_error_hits
        if _SOFT_LOG_RE.search(x) and not _HARD_LOG_RE.search(x)
    ]
    if hard_hits:
        h.problems.append("log_errors")
    elif soft_hits and not (h.exe_present and h.process_running):
        # Network noise alone while stopped — still worth a soft flag.
        h.problems.append("log_network")
    # Soft hits while running: keep in log_error_hits for the UI, not problems.

    # Expensive-ish extended dump only when we will likely report.
    if h.problems and not (
        h.problems == ["run_key_missing"] and h.process_running
    ):
        try:
            h.extended_diag = collect_extended_diag_text(h)
        except Exception as e:
            h.extended_diag = f"(extended diag failed: {e})"

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
    ext = (health.extended_diag or "").strip()
    if not ext and health.problems:
        # Lazy fill if probe skipped extended (tests / race).
        try:
            ext = collect_extended_diag_text(health)
        except Exception as e:
            ext = f"(extended diag failed: {e})"
    if ext:
        parts.append("### Full PC diagnosis")
        parts.append("```")
        parts.append(ext[:14000])
        parts.append("```")
        parts.append("")
    parts.append("---")
    parts.append("_Auto-filed by CloneUp tray when the independent update manager looks unhealthy._")
    return "\n".join(parts)


def issue_title(health: UpdateManagerHealth) -> str:
    tags = ",".join(health.problems[:3]) or "unknown"
    return f"[auto] update-manager unhealthy: {tags} ({health.signature})"
