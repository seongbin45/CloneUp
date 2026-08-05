"""Project / bundle root paths (dev tree vs PyInstaller frozen)."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """
    Directory that contains `ui/`, `assets/`, etc.

    - Dev: CloneUp repo root
    - Frozen: sys._MEIPASS (one-folder/one-file extract dir)
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # app/paths.py → parents[1] = CloneUp root
    return Path(__file__).resolve().parents[1]
