"""Cross-check: embedded connect WebView is not collapsed by layout.

Run:
  .\\.venv\\Scripts\\python.exe scripts\\verify_connect_webview_layout.py
Exit 0 = pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from PySide6.QtCore import Qt, QCoreApplication, QTimer
    from PySide6.QtWidgets import QApplication

    try:
        QCoreApplication.setAttribute(
            Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
        )
    except Exception:
        pass

    app = QApplication.instance() or QApplication(sys.argv)

    from app.ui.connect_webview import webengine_available
    from app.ui.login_dialog import PAT_CREATE_URL, ConnectGitHubWizard

    if not webengine_available():
        print("SKIP: Qt WebEngine not available")
        return 0

    wiz = ConnectGitHubWizard(None)
    assert wiz._use_web, "expected web mode"
    wiz.show()
    wiz._start_web(PAT_CREATE_URL)

    errors: list[str] = []

    def _check() -> None:
        pane = wiz._web_pane
        view = pane._view if pane is not None else None
        dw, dh = wiz.width(), wiz.height()
        vw = view.width() if view is not None else 0
        vh = view.height() if view is not None else 0
        pw = pane.width() if pane is not None else 0
        ph = pane.height() if pane is not None else 0
        print(f"dialog={dw}x{dh} pane={pw}x{ph} view={vw}x{vh}")
        if dw < 900 or dh < 600:
            errors.append(f"dialog too small: {dw}x{dh}")
        if vw < 640 or vh < 400:
            errors.append(f"webview clipped/collapsed: {vw}x{vh}")
        if ph < 400:
            errors.append(f"web pane height too small: {ph}")
        # Nearly work-area sized (taskbar excluded via availableGeometry)
        screen = wiz.screen() or __import__(
            "PySide6.QtGui", fromlist=["QGuiApplication"]
        ).QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            if dw < int(avail.width() * 0.85) or dh < int(avail.height() * 0.85):
                errors.append(
                    f"dialog not near work-area: {dw}x{dh} vs avail {avail.width()}x{avail.height()}"
                )
        # Must keep normal window chrome (close button), not frameless fullscreen
        flags = int(wiz.windowFlags())
        from PySide6.QtCore import Qt as _Qt

        if wiz.windowState() & _Qt.WindowState.WindowFullScreen:
            errors.append("must not use WindowFullScreen (taskbar/X would go away)")
        if flags & int(_Qt.WindowType.FramelessWindowHint):
            errors.append("must not be frameless (need title-bar X)")
        # sizeHint must not be the infamous tiny default
        hint = pane.sizeHint() if pane is not None else None
        if hint is not None and (hint.width() < 400 or hint.height() < 300):
            errors.append(f"pane sizeHint still tiny: {hint.width()}x{hint.height()}")
        wiz.close()
        app.quit()

    QTimer.singleShot(200, _check)
    app.exec()
    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        return 1
    print("OK: connect WebView layout cross-check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
