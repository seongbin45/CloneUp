"""QToolTip must use app card color (bg_window), not native black ToolTipBase."""

from __future__ import annotations

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QToolTip

from app.ui.theme import (
    DARK,
    LIGHT,
    app_stylesheet,
    apply_palette,
    apply_tooltip_palette,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_app_stylesheet_tooltip_uses_bg_window() -> None:
    light_qss = app_stylesheet(LIGHT)
    assert f"background-color: {LIGHT.bg_window}" in light_qss
    assert "QToolTip" in light_qss
    # Must not keep the old sidebar/bar surface for tooltips.
    assert (
        f"QToolTip {{\n        background-color: {LIGHT.bg_bar}" not in light_qss
    )

    dark_qss = app_stylesheet(DARK)
    assert f"background-color: {DARK.bg_window}" in dark_qss


def test_apply_tooltip_palette_sets_card_colors() -> None:
    app = _app()
    try:
        apply_palette(LIGHT)
        apply_tooltip_palette(app, LIGHT)
        assert app.palette().color(QPalette.ColorRole.ToolTipBase).name() == LIGHT.bg_window
        assert app.palette().color(QPalette.ColorRole.ToolTipText).name() == LIGHT.text
        tip = QToolTip.palette()
        assert tip.color(QPalette.ColorRole.ToolTipBase).name() == LIGHT.bg_window
        assert tip.color(QPalette.ColorRole.Window).name() == LIGHT.bg_window

        apply_palette(DARK)
        apply_tooltip_palette(app, DARK)
        assert app.palette().color(QPalette.ColorRole.ToolTipBase).name() == DARK.bg_window
        assert app.palette().color(QPalette.ColorRole.ToolTipText).name() == DARK.text
        tip = QToolTip.palette()
        assert tip.color(QPalette.ColorRole.ToolTipBase).name() == DARK.bg_window
    finally:
        apply_palette(LIGHT)
        apply_tooltip_palette(app, LIGHT)
