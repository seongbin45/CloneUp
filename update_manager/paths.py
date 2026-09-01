"""Locate the installed CloneUp application directory (before any update)."""

from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path

from update_manager.config import INNO_APP_ID


def _local_app_data() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Local"


def manager_install_dir() -> Path:
    """Where CloneUp_update_manager.exe lives (separate from the app)."""
    return _local_app_data() / "CloneUp" / "UpdateManager"


def _looks_like_cloneup_dir(folder: Path) -> bool:
    """True if folder appears to be a CloneUp onedir install."""
    try:
        if not folder.is_dir():
            return False
    except OSError:
        return False
    exe = folder / "CloneUp.exe"
    if not exe.is_file():
        return False
    # Frozen onedir usually has _internal; portable/dev may not.
    return True


def _uninstall_display_icon_dir(icon_path: str) -> Path | None:
    # UninstallDisplayIcon={app}\CloneUp.ico
    p = Path(icon_path.strip().strip('"'))
    if p.suffix.lower() in {".ico", ".exe"}:
        parent = p.parent
        if _looks_like_cloneup_dir(parent):
            return parent.resolve()
    return None


def _read_uninstall_install_location() -> Path | None:
    """Read Inno / ARP uninstall keys for CloneUp InstallLocation or icon path."""
    if sys.platform != "win32":
        return None
    # Inno with PrivilegesRequired=lowest writes under HKCU.
    roots = (
        (
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
    )
    app_id_keys = {
        INNO_APP_ID,
        INNO_APP_ID.strip("{}"),
        f"{{{INNO_APP_ID.strip('{}')}}}",
    }
    for hive, base in roots:
        # Direct AppId subkey (Inno often uses AppId as key name).
        for key_name in app_id_keys:
            try:
                with winreg.OpenKey(hive, f"{base}\\{key_name}") as key:
                    got = _parse_uninstall_key(key)
                    if got is not None:
                        return got
            except OSError:
                pass
        # Scan by DisplayName.
        try:
            with winreg.OpenKey(hive, base) as root:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(root, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        with winreg.OpenKey(root, name) as key:
                            try:
                                display, _ = winreg.QueryValueEx(key, "DisplayName")
                            except OSError:
                                continue
                            if str(display).strip() not in ("CloneUp", "클론업"):
                                # Allow "CloneUp 0.1.8" style
                                if not str(display).strip().startswith("CloneUp"):
                                    continue
                            got = _parse_uninstall_key(key)
                            if got is not None:
                                return got
                    except OSError:
                        continue
        except OSError:
            continue
    return None


def _parse_uninstall_key(key) -> Path | None:
    for value_name in ("InstallLocation", "Inno Setup: App Path"):
        try:
            val, _ = winreg.QueryValueEx(key, value_name)
            p = Path(str(val).strip().strip('"'))
            if _looks_like_cloneup_dir(p):
                return p.resolve()
        except OSError:
            pass
    try:
        icon, _ = winreg.QueryValueEx(key, "DisplayIcon")
        got = _uninstall_display_icon_dir(str(icon))
        if got is not None:
            return got
    except OSError:
        pass
    try:
        uni, _ = winreg.QueryValueEx(key, "UninstallString")
        # "C:\...\unins000.exe" → parent is often {app}
        p = Path(str(uni).strip().strip('"').split(" /")[0].strip('"'))
        if p.name.lower().startswith("unins") and _looks_like_cloneup_dir(p.parent):
            return p.parent.resolve()
    except OSError:
        pass
    return None


def _candidate_dirs() -> list[Path]:
    local = _local_app_data()
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    return [
        local / "Programs" / "CloneUp",
        Path(pf) / "CloneUp",
        Path(pf86) / "CloneUp",
        local / "CloneUp",  # mistaken / legacy
    ]


def find_cloneup_install_dir() -> Path | None:
    """
    Resolve the folder that contains ``CloneUp.exe`` (the app onedir).

    Order:
      1. ``CLONEUP_INSTALL_DIR`` env (tests / override)
      2. Uninstall / ARP registry (Inno AppId + DisplayName)
      3. Well-known default paths with ``CloneUp.exe`` present
    """
    env = os.environ.get("CLONEUP_INSTALL_DIR", "").strip()
    if env:
        p = Path(env).expanduser()
        if _looks_like_cloneup_dir(p):
            return p.resolve()
        # Explicit override that is not a valid onedir → do not fall through
        # to a different real install (keeps tests / misconfig predictable).
        return None

    from_reg = _read_uninstall_install_location()
    if from_reg is not None:
        return from_reg

    for cand in _candidate_dirs():
        if _looks_like_cloneup_dir(cand):
            return cand.resolve()
    return None
