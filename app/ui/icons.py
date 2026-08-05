"""App icon loading (desin/icon → assets/icons)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

# CloneUp/ root (…/app/ui/icons.py → parents[2])
_ROOT = Path(__file__).resolve().parents[2]
_ICONS_DIR = _ROOT / "assets" / "icons"


def icons_dir() -> Path:
    return _ICONS_DIR


def load_app_icon() -> QIcon:
    """
    Window / taskbar icon.

    Prefer multi-size CloneUp.ico; fall back to PNG set if ico missing.
    """
    icon = QIcon()
    ico = _ICONS_DIR / "CloneUp.ico"
    if ico.is_file():
        icon = QIcon(str(ico))
        if not icon.isNull():
            return icon

    # Fallback: individual PNGs (development / incomplete assets)
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        png = _ICONS_DIR / f"icon-{size}.png"
        if png.is_file():
            icon.addFile(str(png))
    return icon
