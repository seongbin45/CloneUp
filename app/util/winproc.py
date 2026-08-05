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
