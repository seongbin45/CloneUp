"""Constants for the silent background updater."""

from __future__ import annotations

GITHUB_OWNER = "seongbin45"
GITHUB_REPO = "CloneUp"
API_LATEST = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)

# Poll interval (seconds).
INTERVAL_SEC = 600

# Preferred release asset names (first match wins). Never use Setup.exe —
# running the installer would show a GUI; we zip-copy onedir files instead.
ASSET_NAME_CANDIDATES = (
    "CloneUp-win64.zip",
    "CloneUp.zip",
    "CloneUp-windows.zip",
)

# Main window title used by CloneUp (exact).
MAIN_WINDOW_TITLE = "클론업 (CloneUp)"

# Process image to stop before replacing files.
CLONEUP_EXE_NAME = "CloneUp.exe"

# Never kill these.
PROTECTED_EXE_NAMES = frozenset(
    {
        "CloneUp_update_manager.exe",
        "CloneUp-Setup.exe",
    }
)

# HKCU Run value that means user wants tray after update.
CLONEUP_TRAY_RUN_VALUE = "CloneUpTray"

# Inno AppId (without outer braces variant used under Uninstall keys).
INNO_APP_ID = "{A7C1E0B2-4D5F-4A8E-9C3B-1F2E3D4C5B6A}"

USER_AGENT = "CloneUp-UpdateManager/0.1.0"
