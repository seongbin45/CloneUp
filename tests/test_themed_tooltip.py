"""Themed tooltip popup must use card colors and suppress native tips."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from app.ui.theme import DARK, LIGHT, apply_palette
from app.ui import themed_tooltip as tt


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_show_themed_tooltip_uses_bg_window() -> None:
    app = _app()
    try:
        apply_palette(LIGHT)
        tt.install_themed_tooltips(app)
        tt.show_themed_tooltip("hello card", QPoint(80, 80))
        app.processEvents()
        assert tt._popup is not None
        assert tt._popup.isVisible()
        assert tt._popup._radius == tt.TIP_RADIUS_PX
        assert tt._popup._bg.name() == LIGHT.bg_window
        assert LIGHT.text in tt._popup.styleSheet()

        apply_palette(DARK)
        tt.refresh_themed_tooltip_chrome()
        assert tt._popup._bg.name() == DARK.bg_window
        assert tt._popup._border.name() == DARK.border_soft
    finally:
        tt.hide_themed_tooltip()
        apply_palette(LIGHT)
        tt.refresh_themed_tooltip_chrome()


def test_tooltip_corner_radius_matches_floating_cards() -> None:
    """Overflow / floating cards use 9px; tip must follow the same curve."""
    assert tt.TIP_RADIUS_PX == 9.0


def test_tooltip_event_is_consumed_for_widgets_with_tip() -> None:
    app = _app()
    host = QWidget()
    lab = QLabel("x", host)
    lab.setToolTip("full path here")
    try:
        apply_palette(LIGHT)
        tt.install_themed_tooltips(app)
        host.show()
        app.processEvents()

        ev = QHelpEvent(
            QEvent.Type.ToolTip,
            lab.rect().center(),
            lab.mapToGlobal(lab.rect().center()),
        )
        # Deliver via the installed app filter path.
        consumed = app.sendEvent(lab, ev)
        app.processEvents()
        assert consumed is True
        assert tt._popup is not None and tt._popup.isVisible()
        # MarqueeLabel keeps full string in `_full` (text() may be elided/cleared).
        assert "full path here" in getattr(tt._label, "_full", "") or (
            "full path here" in (tt._label.text() or "")
        )
    finally:
        tt.hide_themed_tooltip()
        host.close()
        apply_palette(LIGHT)
