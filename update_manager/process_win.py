"""Detect CloneUp main window; kill CloneUp.exe process tree (not the manager)."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

from update_manager.config import (
    CLONEUP_EXE_NAME,
    MAIN_WINDOW_TITLE,
    PROTECTED_EXE_NAMES,
)

log = logging.getLogger("cloneup_update_manager")


def main_window_visible() -> bool:
    """True if a visible top-level window titled exactly MAIN_WINDOW_TITLE exists."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = ctypes.c_int(0)

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum(hwnd, _lparam):  # noqa: N803
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value == MAIN_WINDOW_TITLE:
                found.value = 1
                return False
            return True

        user32.EnumWindows(_enum, 0)
        return bool(found.value)
    except Exception as e:
        log.warning("EnumWindows failed: %s", e)
        return False


def _create_no_window_flags() -> int:
    # Avoid console flash for taskkill.
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def kill_cloneup_processes(*, wait_sec: float = 30.0) -> bool:
    """
    Force-stop CloneUp.exe and its children. Never targets update_manager.

    Returns True if no CloneUp.exe remains (or none existed).
    """
    if sys.platform != "win32":
        return True
    # Safety: refuse if our own image name is somehow CloneUp.exe (should not happen).
    me = Path(sys.executable).name.lower()
    if me in {n.lower() for n in PROTECTED_EXE_NAMES}:
        pass

    flags = _create_no_window_flags()
    try:
        subprocess.run(
            ["taskkill", "/IM", CLONEUP_EXE_NAME, "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=flags,
            check=False,
        )
    except Exception as e:
        log.warning("taskkill error: %s", e)

    deadline = time.time() + max(1.0, wait_sec)
    while time.time() < deadline:
        if not _cloneup_exe_running():
            return True
        time.sleep(0.4)
    still = _cloneup_exe_running()
    if still:
        log.error("CloneUp.exe still running after kill wait")
    return not still


def _cloneup_exe_running() -> bool:
    flags = _create_no_window_flags()
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {CLONEUP_EXE_NAME}", "/NH"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=flags,
            check=False,
        )
        out = (r.stdout or "").lower()
        return CLONEUP_EXE_NAME.lower() in out and "no tasks" not in out
    except Exception:
        return False


def is_tray_autostart_registered() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        from update_manager.config import CLONEUP_TRAY_RUN_VALUE

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            winreg.QueryValueEx(key, CLONEUP_TRAY_RUN_VALUE)
            return True
    except OSError:
        return False


def restart_cloneup_tray(install_dir: Path) -> None:
    exe = install_dir / CLONEUP_EXE_NAME
    if not exe.is_file():
        log.warning("cannot restart tray — missing %s", exe)
        return
    flags = _create_no_window_flags()
    try:
        subprocess.Popen(
            [str(exe), "--tray"],
            cwd=str(install_dir),
            creationflags=flags,
            close_fds=True,
        )
        log.info("restarted CloneUp --tray")
    except Exception as e:
        log.warning("restart tray failed: %s", e)
