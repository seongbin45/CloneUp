"""Migrate CloneUpUpdateManager scheduled task (Parallel + interactive Run)."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger("cloneup_update_manager")

TASK_NAME = "CloneUpUpdateManager"


def _no_window_kwargs() -> dict:
    """Suppress black console flashes for schtasks/powershell children."""
    if sys.platform != "win32":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return {"creationflags": flags, "startupinfo": si}


def _task_exists() -> bool:
    r = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        check=False,
        **_no_window_kwargs(),
    )
    return r.returncode == 0


def _parse_task_to_run(verbose_list: str) -> str:
    for line in verbose_list.splitlines():
        if "Task To Run" in line or "실행할 작업" in line or "실행할 프로그램" in line:
            _, _, rest = line.partition(":")
            return rest.strip().strip('"')
    return ""


def _split_command_args(tr: str) -> tuple[str, str]:
    """Split Task To Run into (command, arguments). Handles quoted exe paths."""
    tr = (tr or "").strip()
    if not tr:
        return "", ""
    if tr.startswith('"'):
        m = re.match(r'^"([^"]+)"\s*(.*)$', tr)
        if m:
            return m.group(1).strip(), m.group(2).strip()
    parts = tr.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _grant_interactive_run(lg: logging.Logger) -> None:
    """Allow Authenticated Users to read/run the task (schtasks /Run from tray)."""
    try:
        ps = (
            "$ErrorActionPreference='Stop'; "
            f"$n='{TASK_NAME}'; "
            "$s=New-Object -ComObject 'Schedule.Service'; "
            "$s.Connect(); "
            "$t=$s.GetFolder('\\').GetTask($n); "
            # SY+BA full; AU read+execute (enough for /Run from interactive user)
            "$sd='D:AR(A;;FA;;;SY)(A;;FA;;;BA)(A;;FRFX;;;AU)'; "
            "$t.SetSecurityDescriptor($sd, 0); "
            "Write-Output 'acl-ok'"
        )
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            **_no_window_kwargs(),
        )
        if r.returncode != 0:
            lg.warning(
                "task ACL grant failed: %s",
                ((r.stderr or r.stdout) or "")[:300],
            )
        else:
            lg.info("task ACL: Authenticated Users can Run")
    except Exception as e:
        lg.warning("task ACL grant error: %s", e)


def migrate_update_manager_task(logger: logging.Logger | None = None) -> bool:
    """
    Best-effort: re-register task as ONLOGON SYSTEM HIGHEST with Parallel instances
    and grant interactive users permission to /Run.

    Task action prefers ``wscript //B …_hidden.vbs`` so login never flashes a
    black console (direct .exe / .bat TR is rewritten when VBS is present).

    Safe to call every tick; no-op if task missing (user-mode install).
    """
    lg = logger or log
    if sys.platform != "win32":
        return False
    if not _task_exists():
        return False

    from update_manager.paths import UM_VBS_NAME, manager_hidden_vbs_path, manager_task_tr

    r = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **_no_window_kwargs(),
    )
    tr = _parse_task_to_run(r.stdout or "")
    if not tr or "cloneup_update_manager" not in tr.lower():
        lg.warning("task migrate: could not parse TR")
        return False

    # Prefer hidden VBS launcher next to the installed exe.
    vbs = manager_hidden_vbs_path()
    desired_tr = manager_task_tr()
    if vbs.is_file():
        command, arguments = _split_command_args(desired_tr)
    else:
        command, arguments = _split_command_args(tr)
        # If TR still points at bare exe/bat, keep it but log.
        if command.lower().endswith(".exe") or command.lower().endswith(".bat"):
            lg.info(
                "task migrate: %s missing — keeping TR=%s",
                UM_VBS_NAME,
                tr[:160],
            )

    if not command:
        lg.warning("task migrate: empty command")
        return False

    # Already on hidden VBS with Parallel — still refresh ACL / settings via recreate.
    args_xml = ""
    if arguments:
        args_xml = f"\n      <Arguments>{_xml_escape(arguments)}</Arguments>"

    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>CloneUp silent update manager (SYSTEM, hidden VBS)</Description>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <AllowHardTerminate>true</AllowHardTerminate>
    <Enabled>true</Enabled>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
  </Settings>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>{_xml_escape(command)}</Command>{args_xml}
    </Exec>
  </Actions>
</Task>
"""
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-16"
        ) as f:
            f.write(xml)
            xml_path = f.name
        r2 = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            **_no_window_kwargs(),
        )
        Path(xml_path).unlink(missing_ok=True)
        if r2.returncode != 0:
            lg.warning("task migrate create failed: %s", (r2.stderr or r2.stdout)[:300])
            return False
        _grant_interactive_run(lg)
        lg.info("task migrate ok (Parallel + on-demand)")
        return True
    except Exception as e:
        lg.warning("task migrate error: %s", e)
        return False


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def run_scheduled_task() -> tuple[bool, str]:
    """Trigger CloneUpUpdateManager now. Returns (ok, detail)."""
    if sys.platform != "win32":
        return False, "not windows"
    if not _task_exists():
        return False, "task_missing"
    r = subprocess.run(
        ["schtasks", "/Run", "/TN", TASK_NAME],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **_no_window_kwargs(),
    )
    detail = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        return False, detail or f"exit {r.returncode}"
    return True, detail or "ok"
