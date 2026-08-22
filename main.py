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
        from PySide6.QtCore import Qt, QCoreApplication
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 가 필요합니다:\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install PySide6\n",
            file=sys.stderr,
        )
        return 2

    # Required before QApplication when Qt WebEngine may be used (connect wizard).
    try:
        QCoreApplication.setAttribute(
            Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
        )
    except Exception:
        pass

    from app import __version__
    from app.ui.icons import load_app_icon
    from app.ui.main_window import load_main_window
    from app.ui.theme import apply_system_theme

    app = QApplication(sys.argv)
    app.setApplicationName("CloneUp")
    app.setApplicationVersion(__version__)

    # I3 — window / taskbar icon (assets/icons from desin/icon)
    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    # D1 — OS light/dark → desin LIGHT / DARK stylesheet (no manual toggle yet)
    apply_system_theme(app)
    try:
        app.styleHints().colorSchemeChanged.connect(
            lambda _scheme=None: apply_system_theme(app)
        )
    except Exception:
        # Older Qt / platform without colorSchemeChanged — keep startup theme only
        pass

    # M1 — wipe leftover push credential temp files from a previous crash
    try:
        from app.git.credentials import cleanup_orphan_credential_files

        cleanup_orphan_credential_files(max_age_sec=0)
    except Exception:
        pass

    win = load_main_window()
    if not app_icon.isNull():
        win.setWindowIcon(app_icon)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
