"""App icon loading (desin/icon → assets/icons).

Loads every available size so Windows shell / Qt pick sharp icons
at 16, 24, 32, 48, 64, 128, 256, 512 (taskbar, title bar, Alt-Tab).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

from app.paths import app_root

# Sizes shipped in assets/icons (and inside CloneUp.ico for 16–256)
ICON_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256, 512)


def icons_dir() -> Path:
    return app_root() / "assets" / "icons"


def load_app_icon() -> QIcon:
    """
    Window / taskbar / application icon.

    1) Prefer multi-size CloneUp.ico (Windows native).
    2) Always layer PNG frames so Qt has exact bitmaps per size
       (ICO alone can miss a size on some DPI scales).
    """
    icon = QIcon()
    base = icons_dir()
    ico = base / "CloneUp.ico"
    if ico.is_file():
        # Base: all frames embedded in the ICO
        icon = QIcon(str(ico))

    # Explicit PNG addFile for every size — guarantees Control Panel–class
    # multi-resolution set when ICO is incomplete or Qt under-reads it.
    for size in ICON_SIZES:
        png = base / f"icon-{size}.png"
        if not png.is_file():
            continue
        qsize = QSize(size, size)
        icon.addFile(str(png), qsize, QIcon.Mode.Normal, QIcon.State.Off)
        icon.addFile(str(png), qsize, QIcon.Mode.Active, QIcon.State.Off)

    # Dark-tile variant as optional large mark (not required for shell)
    dark = base / "icon-512-dark.png"
    if dark.is_file():
        icon.addFile(str(dark), QSize(512, 512), QIcon.Mode.Normal, QIcon.State.Off)

    return icon


def ico_path() -> Path | None:
    """Path to multi-size .ico for packaging / installers."""
    p = icons_dir() / "CloneUp.ico"
    return p if p.is_file() else None
