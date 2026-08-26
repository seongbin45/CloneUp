"""Windows: run console tools without flashing a black terminal window."""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def hidden_run_kwargs() -> dict[str, Any]:
    """
    Extra kwargs for subprocess.run / Popen on Windows.

    GUI apps (console=False / runw) still spawn a console for each child
    console-subsystem process (git.exe, clip.exe, winget) unless we set
    CREATE_NO_WINDOW. Do NOT use this when launching a GUI installer.
    """
    if sys.platform != "win32":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    # STARTUPINFO hide is belt-and-suspenders on older Python builds
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return {
        "creationflags": flags,
        "startupinfo": si,
    }


def run_hidden(cmd: list[str] | str, **kwargs: Any) -> subprocess.CompletedProcess:
    """subprocess.run with console window suppressed on Windows."""
    kw = {**hidden_run_kwargs(), **kwargs}
    # Caller-provided creationflags/startupinfo win if they pass them last — we merge carefully
    base = hidden_run_kwargs()
    for k, v in kwargs.items():
        base[k] = v
    return subprocess.run(cmd, **base)


def bring_window_to_front(widget: Any) -> None:
    """
    Raise a Qt window above other apps (e.g. browser after GitHub connect).

    Qt ``raise_`` / ``activateWindow`` alone often fail when another process
    holds foreground focus on Windows — use SetForegroundWindow with a brief
    AttachThreadInput dance.
    """
    if widget is None:
        return
    try:
        from PySide6.QtCore import Qt

        if hasattr(widget, "isMinimized") and widget.isMinimized():
            widget.setWindowState(
                widget.windowState() & ~Qt.WindowState.WindowMinimized
            )
            widget.showNormal()
        widget.show()
        widget.raise_()
        widget.activateWindow()
    except Exception:
        pass

    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = int(widget.winId())
        if not hwnd:
            return

        foreground = user32.GetForegroundWindow()
        if foreground == hwnd:
            return

        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)

        # Allow SetForegroundWindow by temporarily attaching input queues
        fg_tid = user32.GetWindowThreadProcessId(foreground, None)
        our_tid = kernel32.GetCurrentThreadId()
        attached = False
        if fg_tid and our_tid and fg_tid != our_tid:
            attached = bool(user32.AttachThreadInput(fg_tid, our_tid, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(fg_tid, our_tid, False)
    except Exception:
        pass


def send_window_to_back(widget: Any) -> None:
    """
    Push a Qt window behind other top-level windows (near the desktop).

    Used by the Path B browser guide so Chrome/Edge cover it until the user
    minimizes other apps or explicitly clicks the guide.
    """
    if widget is None:
        return
    try:
        widget.lower()
    except Exception:
        pass

    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = int(widget.winId())
        if not hwnd:
            return
        # HWND_BOTTOM = 1
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOACTIVATE = 0x0010
        user32.SetWindowPos(
            hwnd,
            1,  # HWND_BOTTOM
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE,
        )
    except Exception:
        pass
