"""Boot toast: 시안 layout + active_palette light/dark colors."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QFrame

from app.ui.boot_notify import BootNotifyToast, _toast_qss
from app.ui.boot_scan import ChangedFile, PendingFolder
from app.ui.theme import DARK, LIGHT, apply_palette


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_toast_qss_follows_active_palette(qapp) -> None:
    apply_palette(LIGHT)
    light = _toast_qss()
    assert "border-radius: 10px" in light
    assert LIGHT.bg_window in light
    assert LIGHT.primary in light
    assert "bootToastShell" in light and "bootToastCard" in light

    apply_palette(DARK)
    dark = _toast_qss()
    assert DARK.bg_window in dark
    assert DARK.bg_bar in dark
    assert DARK.primary in dark
    assert f"background: {LIGHT.bg_window}" not in dark
    assert f"background: {DARK.bg_window}" in dark


def test_toast_widget_stylesheet_tracks_dark(qapp) -> None:
    pf = PendingFolder(
        path="C:/tmp/demo",
        name="demo",
        files=(ChangedFile("M", "a.py", "#8a6d12"),),
        dirty=True,
        ahead=0,
        file_count=1,
    )
    apply_palette(DARK)
    toast = BootNotifyToast([pf])
    try:
        assert toast.objectName() == "bootToastShell"
        card = toast.findChild(QFrame, "bootToastCard")
        assert card is not None
        ss = toast.styleSheet()
        assert DARK.bg_window in ss
        assert f"background: {LIGHT.bg_window}" not in ss.split("QPushButton")[0]
        assert toast.width() == 382
    finally:
        toast.close()
        apply_palette(LIGHT)
