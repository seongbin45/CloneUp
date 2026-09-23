"""Main window normal size fills availableGeometry (taskbar-safe)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QMainWindow

from app.util.screen_fit import (
    apply_work_area_normal_fill,
    read_screen_info,
    screen_for_widget,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_normal_fill_frame_inside_available() -> None:
    app = _app()
    win = QMainWindow()
    win.setWindowTitle("CloneUp work-area fill test")
    win.show()
    app.processEvents()

    apply_work_area_normal_fill(win)
    app.processEvents()

    info = read_screen_info(screen_for_widget(win))
    assert info is not None
    frame = win.frameGeometry()

    # Frame must sit inside the work area (taskbar excluded).
    assert frame.left() >= info.available_x - 2
    assert frame.top() >= info.available_y - 2
    assert frame.right() <= info.available_x + info.available_w + 2
    assert frame.bottom() <= info.available_y + info.available_h + 2

    # Nearly fills the work area (allow a few px for chrome rounding).
    assert frame.width() >= info.available_w - 16
    assert frame.height() >= info.available_h - 16

    # Stays normal — not Maximized / FullScreen.
    assert not win.isMaximized()
    assert not win.isFullScreen()

    win.close()
