"""App icon loading (desin/icon → assets/icons)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

from app.paths import app_root


def icons_dir() -> Path:
    return app_root() / "assets" / "icons"


def load_app_icon() -> QIcon:
    """
    Window / taskbar icon.

    Prefer multi-size CloneUp.ico; fall back to PNG set if ico missing.
    """
    icon = QIcon()
    base = icons_dir()
    ico = base / "CloneUp.ico"
    if ico.is_file():
        icon = QIcon(str(ico))
        if not icon.isNull():
            return icon

    # Fallback: individual PNGs (development / incomplete assets)
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        png = base / f"icon-{size}.png"
        if png.is_file():
            icon.addFile(str(png))
    return icon
