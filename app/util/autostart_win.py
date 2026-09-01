"""Windows: register / unregister CloneUp tray at user logon (HKCU Run)."""

from __future__ import annotations

import sys
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "CloneUpTray"


def _tray_command() -> str:
    """Command line that starts CloneUp in tray mode."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return f'"{exe}" --tray'
    # Dev: python main.py --tray
    root = Path(__file__).resolve().parents[2]
    main_py = root / "main.py"
    py = Path(sys.executable).resolve()
    return f'"{py}" "{main_py}" --tray'


def is_autostart_registered() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            try:
                winreg.QueryValueEx(key, _VALUE_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception:
        return False


def set_autostart_registered(enabled: bool) -> bool:
    """Create or delete HKCU Run value. Returns True on success."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, _VALUE_NAME, 0, winreg.REG_SZ, _tray_command()
                )
            else:
                try:
                    winreg.DeleteValue(key, _VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False
