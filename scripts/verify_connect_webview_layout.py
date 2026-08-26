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
    from app.auth.pat_urls import classic_pat_create_url
    from app.ui.login_dialog import ConnectGitHubWizard

    if not webengine_available():
        print("SKIP: Qt WebEngine not available")
        return 0

    wiz = ConnectGitHubWizard(None)
    assert wiz._use_web, "expected web mode"
    wiz.show()
    wiz._start_web(classic_pat_create_url())

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
        if vw < 560 or vh < 280:
            errors.append(f"webview clipped/collapsed: {vw}x{vh}")
        if ph < 280:
            errors.append(f"web pane height too small: {ph}")
        # Fill work area (1920×1080 etc.); taskbar excluded via availableGeometry
        from PySide6.QtCore import Qt as _Qt

        screen = wiz.screen() or __import__(
            "PySide6.QtGui", fromlist=["QGuiApplication"]
        ).QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            print(
                f"avail={avail.width()}x{avail.height()} "
                f"maximized={bool(wiz.windowState() & _Qt.WindowState.WindowMaximized)}"
            )
            if dw < int(avail.width() * 0.92) or dh < int(avail.height() * 0.92):
                errors.append(
                    f"dialog not filling work-area: {dw}x{dh} vs avail "
                    f"{avail.width()}x{avail.height()}"
                )
        # Must keep normal window chrome (close button), not frameless fullscreen
        flags = int(wiz.windowFlags())

        if wiz.windowState() & _Qt.WindowState.WindowFullScreen:
            errors.append("must not use WindowFullScreen (taskbar/X would go away)")
        if flags & int(_Qt.WindowType.FramelessWindowHint):
            errors.append("must not be frameless (need title-bar X)")
        if not (flags & int(_Qt.WindowType.WindowCloseButtonHint)):
            errors.append("WindowCloseButtonHint missing (need title-bar X)")
        # sizeHint must not be the infamous tiny default
        hint = pane.sizeHint() if pane is not None else None
        if hint is not None and (hint.width() < 400 or hint.height() < 300):
            errors.append(f"pane sizeHint still tiny: {hint.width()}x{hint.height()}")

        # Body structure (no outer gray, no in-card logo header, no privacy box)
        if wiz.objectName() != "connectWebDialog":
            errors.append(f"dialog objectName={wiz.objectName()!r}")
        if "CloneUp" not in (wiz.windowTitle() or ""):
            errors.append(f"window title should include app name: {wiz.windowTitle()!r}")
        from PySide6.QtWidgets import QFrame

        card = wiz.findChild(QFrame, "connCard")
        if card is None:
            errors.append("missing connCard")
        else:
            print(f"card={card.width()}x{card.height()}")
            if card.width() < 900:
                errors.append(f"card too narrow: {card.width()}")
            # Content fills dialog (no gray outer gutters)
            if dw - card.width() > 40:
                errors.append(
                    f"card not filling dialog (unexpected gutters): "
                    f"dialog={dw} card={card.width()}"
                )
        if wiz.findChild(QFrame, "connHeader") is not None:
            errors.append("connHeader must not exist (logo/name only in window title)")
        if wiz.findChild(QFrame, "connPrivacy") is not None:
            errors.append("connPrivacy must not exist (no gray explanation box)")
        if wiz.findChild(QFrame, "connFooter") is None:
            errors.append("missing connFooter")
        if wiz.findChild(QFrame, "connTrack") is None:
            errors.append("missing connTrack")
        if wiz.findChild(QFrame, "connBrowser") is None:
            errors.append("missing connBrowser")
        if wiz.findChild(QFrame, "connWatch") is None:
            errors.append("missing connWatch")

        # Resizable: minimum must be well below current near-fullscreen size
        min_sz = wiz.minimumSize()
        print(f"min={min_sz.width()}x{min_sz.height()}")
        if min_sz.width() >= dw - 20 or min_sz.height() >= dh - 20:
            errors.append(
                f"minimum size locks near-fullscreen (not resizable): "
                f"min={min_sz.width()}x{min_sz.height()} dialog={dw}x{dh}"
            )
        if wiz.maximumWidth() < 100000 and wiz.maximumWidth() <= dw:
            errors.append(f"maximumWidth caps resize: {wiz.maximumWidth()}")

        # Step 1 defaults: key hidden, CTA disabled "다음"
        wiz._paint_web_guide(0)
        key_wrap = getattr(wiz, "_key_wrap", None)
        if key_wrap is not None and key_wrap.isVisible():
            errors.append("key row visible on step 1")
        if wiz._web_cta is None or wiz._web_cta.isEnabled():
            errors.append("CTA should be disabled on step 1")
        if wiz._web_cta is not None and wiz._web_cta.text() != "다음":
            errors.append(f"CTA text on step1={wiz._web_cta.text()!r}")
        if wiz._web_counter is not None and wiz._web_counter.text() != "1 / 4":
            errors.append(f"counter={wiz._web_counter.text()!r}")

        # Step 4: key visible, warn watch, CTA "연결"
        wiz._paint_web_guide(3)
        if key_wrap is not None and not key_wrap.isVisible():
            errors.append("key row hidden on step 4")
        if wiz._web_watch is not None and wiz._web_watch.objectName() != "connWatchWarn":
            errors.append(f"watch on step4={wiz._web_watch.objectName()!r}")
        if wiz._web_cta is not None and wiz._web_cta.text() != "연결":
            errors.append(f"CTA text on step4={wiz._web_cta.text()!r}")
        if wiz._web_counter is not None and wiz._web_counter.text() != "4 / 4":
            errors.append(f"counter step4={wiz._web_counter.text()!r}")

        wiz.close()
        app.quit()

    # Allow showEvent → showMaximized to settle before measuring
    QTimer.singleShot(400, _check)
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
