"""Windows scheduled task for CloneUp project-scan worker (plan D2)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger("cloneup.scan_task")

TASK_NAME = "CloneUpProjectScan"


def _launcher_cmd_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMP") or "."
    d = Path(base) / "CloneUp" / "scan_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / "run_scan.cmd"


def write_launcher_cmd() -> Path:
    """Write a tiny .cmd the task runs (sets cwd / PYTHONPATH for -m)."""
    path = _launcher_cmd_path()
    if getattr(sys, "frozen", False):
        body = f'@echo off\r\n"{sys.executable}" --scan-cache\r\n'
    else:
        root = Path(__file__).resolve().parents[2]
        exe = sys.executable
        body = (
            "@echo off\r\n"
            f'cd /d "{root}"\r\n'
            f'"{exe}" -m app.scan_worker\r\n'
        )
    path.write_text(body, encoding="utf-8")
    return path


def task_exists() -> bool:
    r = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        check=False,
    )
    return r.returncode == 0


def remove_scan_task() -> tuple[bool, str]:
    if not task_exists():
        return True, "already absent"
    r = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if r.returncode == 0:
        return True, "deleted"
    msg = (r.stderr or r.stdout or "").strip() or f"exit {r.returncode}"
    return False, msg


def ensure_scan_task(*, enabled: bool) -> tuple[bool, str]:
    """Create hourly + logon(+5m) task, or remove when disabled."""
    if not enabled:
        return remove_scan_task()

    launcher = write_launcher_cmd()
    tr = str(launcher)
    remove_scan_task()

    # XML: LOGON +5m and hourly repetition
    tr_esc = (
        tr.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT5M</Delay>
    </LogonTrigger>
    <CalendarTrigger>
      <Repetition>
        <Interval>PT1H</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2020-01-01T00:15:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{tr_esc}</Command>
    </Exec>
  </Actions>
</Task>
"""
    fd, name = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    path = Path(name)
    try:
        path.write_text(xml, encoding="utf-16")
        r = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(path), "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if r.returncode != 0:
            # Fallback: simple hourly task
            r2 = subprocess.run(
                [
                    "schtasks",
                    "/Create",
                    "/TN",
                    TASK_NAME,
                    "/TR",
                    tr,
                    "/SC",
                    "HOURLY",
                    "/MO",
                    "1",
                    "/F",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if r2.returncode != 0:
                msg = (r.stderr or r.stdout or r2.stderr or r2.stdout or "").strip()
                log.warning("ensure_scan_task failed: %s", msg)
                return False, msg or "schtasks failed"
            return True, "created-hourly-fallback"
        return True, "created"
    finally:
        try:
            path.unlink()
        except OSError:
            pass
