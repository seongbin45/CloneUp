"""Boot toast QSS follows active light/dark palette (no hard-locked cream)."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from app.ui.boot_notify import BootNotifyToast, _toast_qss
from app.ui.boot_scan import ChangedFile, PendingFolder
from app.ui.theme import DARK, LIGHT, apply_palette


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_toast_qss_uses_active_palette_light_and_dark(qapp) -> None:
    apply_palette(LIGHT)
    light = _toast_qss()
    assert LIGHT.bg_window in light
    assert LIGHT.bg_bar in light
    assert LIGHT.text in light
    assert "#fbfaf8" in light  # light window token
    # Must not still be "dark window as text" coincidence only — primary from light
    assert LIGHT.primary in light

    apply_palette(DARK)
    dark = _toast_qss()
    assert DARK.bg_window in dark
    assert DARK.bg_bar in dark
    assert DARK.text in dark
    assert DARK.primary in dark
    # Dark toast must not keep the light card fill as the widget background rule.
    assert f"background: {LIGHT.bg_window}" not in dark
    assert f"background: {DARK.bg_window}" in dark


def test_toast_widget_stylesheet_tracks_palette(qapp) -> None:
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
        ss = toast.styleSheet()
        assert DARK.bg_window in ss
        assert f"background: {LIGHT.bg_window}" not in ss
    finally:
        toast.close()
        apply_palette(LIGHT)
