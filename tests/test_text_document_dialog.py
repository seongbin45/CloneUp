"""이용약관 / legal text dialog must stay inside the taskbar-safe work area."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog

from app.ui.text_document_dialog import show_text_document_dialog
from app.util.screen_fit import read_screen_info, screen_for_widget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_text_document_dialog_fits_available_geometry() -> None:
    app = _app()
    long_text = "약관 줄\n" * 800
    seen: dict[str, object] = {}

    def _probe() -> None:
        for w in app.topLevelWidgets():
            if (
                isinstance(w, QDialog)
                and w.objectName() == "textDocumentDialog"
                and w.isVisible()
            ):
                info = read_screen_info(screen_for_widget(w))
                assert info is not None
                frame = w.frameGeometry()
                # Frame must sit inside availableGeometry (taskbar excluded).
                assert frame.top() >= info.available_y - 2
                assert frame.left() >= info.available_x - 2
                assert frame.bottom() <= info.available_y + info.available_h + 2
                assert frame.right() <= info.available_x + info.available_w + 2
                assert frame.height() <= info.available_h
                seen["ok"] = True
                w.accept()
                return
        # Dialog not up yet — try again shortly.
        QTimer.singleShot(20, _probe)

    QTimer.singleShot(0, _probe)
    # Cap wait so a hang cannot stall CI.
    QTimer.singleShot(3000, app.quit)
    show_text_document_dialog(None, "이용약관", long_text)
    assert seen.get("ok") is True
