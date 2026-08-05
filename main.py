#!/usr/bin/env python3
"""CloneUp GUI entry — Publish tab skeleton."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 가 필요합니다:\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install PySide6\n",
            file=sys.stderr,
        )
        return 2

    from app.ui.main_window import load_main_window

    app = QApplication(sys.argv)
    app.setApplicationName("CloneUp")
    from app.ui.theme import app_stylesheet

    app.setStyleSheet(app_stylesheet())
    win = load_main_window()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
