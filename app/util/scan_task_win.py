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


def _hidden_kwargs() -> dict:
    from app.util.winproc import hidden_run_kwargs

    return hidden_run_kwargs()


def _launcher_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMP") or "."
    d = Path(base) / "CloneUp" / "scan_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _launcher_cmd_path() -> Path:
    return _launcher_dir() / "run_scan.cmd"


def _launcher_vbs_path() -> Path:
    return _launcher_dir() / "run_scan_hidden.vbs"


def write_launcher_cmd() -> Path:
    """Write a tiny .cmd (legacy); prefer ``write_launcher_vbs`` for the task TR."""
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


def write_launcher_vbs() -> Path:
    """Hidden VBS launcher for schtasks (no black console when scan fires)."""
    path = _launcher_vbs_path()
    if getattr(sys, "frozen", False):
        target = str(Path(sys.executable).resolve())
        args = "--scan-cache"
        # Optional working directory = install dir
        work = str(Path(sys.executable).resolve().parent)
    else:
        root = Path(__file__).resolve().parents[2]
        target = str(Path(sys.executable).resolve())
        args = f'-m app.scan_worker'
        work = str(root)

    # Escape for VBScript string literals
    def _vq(s: str) -> str:
        return s.replace('"', '""')

    body = (
        "Option Explicit\r\n"
        "Dim sh, cmd\r\n"
        "Set sh = CreateObject(\"WScript.Shell\")\r\n"
        f'sh.CurrentDirectory = "{_vq(work)}"\r\n'
        f'cmd = """{_vq(target)}"" {_vq(args)}"\r\n'
        "sh.Run cmd, 0, False\r\n"
    )
    path.write_text(body, encoding="utf-8")
    # Keep .cmd in sync for diagnostics / older docs
    write_launcher_cmd()
    return path


def _task_tr() -> str:
    """schtasks /TR: wscript //B //Nologo <run_scan_hidden.vbs>."""
    vbs = write_launcher_vbs()
    windir = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    wscript = str(Path(windir) / "System32" / "wscript.exe")
    return f'"{wscript}" //B //Nologo "{vbs}"'


def task_exists() -> bool:
    r = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        check=False,
        **_hidden_kwargs(),
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
        **_hidden_kwargs(),
    )
    if r.returncode == 0:
        return True, "deleted"
    msg = (r.stderr or r.stdout or "").strip() or f"exit {r.returncode}"
    return False, msg


def _current_task_tr() -> str:
    if not task_exists():
        return ""
    r = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **_hidden_kwargs(),
    )
    for line in (r.stdout or "").splitlines():
        low = line.lower()
        if "task to run" in low or "실행할 작업" in line or "실행할 프로그램" in line:
            _, _, rest = line.partition(":")
            return rest.strip().strip('"')
    return ""


def ensure_scan_task(*, enabled: bool) -> tuple[bool, str]:
    """Create hourly + logon(+5m) task, or remove when disabled.

    Avoids delete+recreate on every app launch when the task already points at
    the current hidden VBS launcher (was causing 3–4 black console flashes).
    """
    if not enabled:
        return remove_scan_task()

    desired_tr = _task_tr()
    # Normalize for compare: strip outer quotes / whitespace
    def _norm(s: str) -> str:
        return " ".join(s.replace('"', "").split()).lower()

    if task_exists() and _norm(_current_task_tr()) == _norm(desired_tr):
        return True, "already-current"

    remove_scan_task()

    # XML: LOGON +5m and hourly repetition — Command=wscript, Arguments=//B …
    # Split TR into Command + Arguments for Task Scheduler XML.
    # desired_tr like: "C:\Windows\System32\wscript.exe" //B //Nologo "C:\...\run_scan_hidden.vbs"
    import re

    m = re.match(r'^"([^"]+)"\s+(.*)$', desired_tr.strip())
    if m:
        command, arguments = m.group(1), m.group(2)
    else:
        parts = desired_tr.split(None, 1)
        command = parts[0]
        arguments = parts[1] if len(parts) > 1 else ""

    def _xml_esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    args_xml = ""
    if arguments:
        args_xml = f"\n      <Arguments>{_xml_esc(arguments)}</Arguments>"

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
      <Command>{_xml_esc(command)}</Command>{args_xml}
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
            **_hidden_kwargs(),
        )
        if r.returncode != 0:
            # Fallback: simple hourly task with full TR string
            r2 = subprocess.run(
                [
                    "schtasks",
                    "/Create",
                    "/TN",
                    TASK_NAME,
                    "/TR",
                    desired_tr,
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
                **_hidden_kwargs(),
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
