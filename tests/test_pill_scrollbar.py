"""PillScrollBar paints a fully rounded capsule; bars auto-show on hover."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QHoverEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QScrollArea

from app.ui.pill_scrollbar import PillScrollBar, wire_pill_scrollbars
from app.ui.theme import LIGHT, apply_palette


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_wire_pill_scrollbars_replaces_bars() -> None:
    _app()
    apply_palette(LIGHT)
    area = QScrollArea()
    wire_pill_scrollbars(area)
    assert isinstance(area.verticalScrollBar(), PillScrollBar)
    assert isinstance(area.horizontalScrollBar(), PillScrollBar)
    # Idempotent
    wire_pill_scrollbars(area)
    assert isinstance(area.verticalScrollBar(), PillScrollBar)


def test_pill_scrollbar_on_plain_text_edit() -> None:
    _app()
    apply_palette(LIGHT)
    ed = QPlainTextEdit("line\n" * 50)
    wire_pill_scrollbars(ed)
    bar = ed.verticalScrollBar()
    assert isinstance(bar, PillScrollBar)
    assert bar.orientation() == Qt.Orientation.Vertical


def test_scrollbars_hidden_until_hover() -> None:
    app = _app()
    apply_palette(LIGHT)
    area = QScrollArea()
    area.resize(200, 200)
    host = QPlainTextEdit("row\n" * 80)
    area.setWidget(host)
    area.setWidgetResizable(True)
    wire_pill_scrollbars(area)

    assert (
        area.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )

    from app.ui import pill_scrollbar as ps

    filt = ps._hover_filters.get(id(area))
    assert filt is not None

    # show() can synthesize Enter if the cursor sits over the window —
    # reset, then drive Enter / Leave explicitly.
    area.show()
    app.processEvents()
    filt.hide_bars()
    assert (
        area.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )

    app.sendEvent(area, QEvent(QEvent.Type.Enter))
    app.processEvents()
    assert (
        area.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )

    app.sendEvent(area, QEvent(QEvent.Type.Leave))
    area.hide()
    filt._hide_timer.stop()
    filt._hide_if_idle()
    app.processEvents()
    assert (
        area.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
