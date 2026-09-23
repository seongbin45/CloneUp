"""Pill (fully rounded) scrollbars — Windows native style ignores QSS radius.

``QScrollBar::handle { border-radius }`` is a no-op under the Windows style
(and often under Fusion when a parent stylesheet is involved). Paint the
handle ourselves as a capsule.

Bars stay hidden until the pointer is over the scroll area (or a bar is
being dragged), then appear with ``ScrollBarAsNeeded``.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QScrollBar,
    QStyle,
    QStyleOptionSlider,
    QWidget,
)

# Logical thickness of the bar (handle inset leaves a soft capsule).
_BAR_PX = 12
_INSET = 2.0
_HIDE_DELAY_MS = 220

_filter: "_PillScrollBarFilter | None" = None
_wired: set[int] = set()
_hover_filters: dict[int, "_AutoShowFilter"] = {}


def _handle_color(*, hover: bool, pressed: bool) -> QColor:
    from app.ui.theme import active_palette

    p = active_palette()
    if pressed:
        return QColor(p.text_muted)
    if hover:
        return QColor(p.text_faint)
    return QColor(p.border_outline)


class PillScrollBar(QScrollBar):
    """Scroll bar whose slider is an antialiased rounded capsule."""

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Vertical,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(orientation, parent)
        self.setObjectName("cloneUpPillScrollBar")
        # Hide native groove/arrows; we paint only the capsule handle.
        if orientation == Qt.Orientation.Vertical:
            self.setStyleSheet(
                "QScrollBar:vertical {"
                f" background: transparent; width: {_BAR_PX}px;"
                " margin: 4px 1px 4px 0; border: none; }"
                "QScrollBar::handle:vertical { background: transparent; min-height: 28px; }"
                "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
                " height: 0; width: 0; border: none; background: none; }"
                "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
                " background: none; }"
            )
        else:
            self.setStyleSheet(
                "QScrollBar:horizontal {"
                f" background: transparent; height: {_BAR_PX}px;"
                " margin: 0 4px 1px 4px; border: none; }"
                "QScrollBar::handle:horizontal { background: transparent; min-width: 28px; }"
                "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {"
                " height: 0; width: 0; border: none; background: none; }"
                "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {"
                " background: none; }"
            )

    def paintEvent(self, event) -> None:  # noqa: N802
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_ScrollBar,
            opt,
            QStyle.SubControl.SC_ScrollBarSlider,
            self,
        )
        if not handle.isValid() or handle.isEmpty():
            return

        rect = QRectF(handle).adjusted(_INSET, _INSET, -_INSET, -_INSET)
        if rect.width() < 2 or rect.height() < 2:
            return

        # Full capsule: radius = half the short side.
        radius = min(rect.width(), rect.height()) / 2.0
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        pressed = bool(opt.state & QStyle.StateFlag.State_Sunken)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_handle_color(hover=hover, pressed=pressed))
        painter.drawRoundedRect(rect, radius, radius)


class _AutoShowFilter(QObject):
    """Show bars only while the pointer is inside the scroll area."""

    def __init__(self, area: QAbstractScrollArea) -> None:
        super().__init__(area)
        self._area = area
        self._shown = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_if_idle)

    def bind_bars(self) -> None:
        for bar in (self._area.verticalScrollBar(), self._area.horizontalScrollBar()):
            if bar is None:
                continue
            bar.installEventFilter(self)
            try:
                bar.sliderPressed.connect(self.show_bars)
                bar.sliderReleased.connect(self._schedule_hide)
            except Exception:
                pass

    def show_bars(self) -> None:
        self._hide_timer.stop()
        if self._shown:
            return
        self._shown = True
        self._area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

    def hide_bars(self) -> None:
        self._hide_timer.stop()
        self._shown = False
        self._area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    def _schedule_hide(self) -> None:
        self._hide_timer.start(_HIDE_DELAY_MS)

    def _pointer_inside(self) -> bool:
        area = self._area
        try:
            if not area.isVisible():
                return False
            pos = area.mapFromGlobal(QCursor.pos())
            return area.rect().contains(pos)
        except Exception:
            return False

    def _dragging(self) -> bool:
        v = self._area.verticalScrollBar()
        h = self._area.horizontalScrollBar()
        return bool(
            (v is not None and v.isSliderDown())
            or (h is not None and h.isSliderDown())
        )

    def _hide_if_idle(self) -> None:
        if self._dragging() or self._pointer_inside():
            return
        self.hide_bars()

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if et in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            self.show_bars()
        elif et in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            self._schedule_hide()
        elif et == QEvent.Type.Wheel:
            # Wheel over the area implies the pointer is on it.
            self.show_bars()
        return False


def wire_pill_scrollbars(area: QAbstractScrollArea) -> None:
    """Replace an area's bars with ``PillScrollBar`` and enable hover auto-show."""
    if area is None:
        return
    v = area.verticalScrollBar()
    if not isinstance(v, PillScrollBar):
        area.setVerticalScrollBar(PillScrollBar(Qt.Orientation.Vertical, area))
    h = area.horizontalScrollBar()
    if not isinstance(h, PillScrollBar):
        area.setHorizontalScrollBar(PillScrollBar(Qt.Orientation.Horizontal, area))

    # Hidden until hover — wheel / drag still work once shown; wheel over
    # content shows bars briefly via the filter.
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    key = id(area)
    filt = _hover_filters.get(key)
    if filt is None:
        filt = _AutoShowFilter(area)
        _hover_filters[key] = filt
        area.installEventFilter(filt)
        vp = area.viewport()
        if vp is not None:
            vp.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            vp.installEventFilter(filt)
    filt.bind_bars()
    filt.hide_bars()
    _wired.add(key)


def polish_pill_scrollbars(root: QWidget | None = None) -> None:
    """Wire every ``QAbstractScrollArea`` under *root* (or the whole app)."""
    app = QApplication.instance()
    if root is None:
        if app is None:
            return
        widgets: list[QWidget] = list(app.topLevelWidgets())
    else:
        widgets = [root]

    for w in widgets:
        if isinstance(w, QAbstractScrollArea):
            wire_pill_scrollbars(w)
        for area in w.findChildren(QAbstractScrollArea):
            wire_pill_scrollbars(area)


class _PillScrollBarFilter(QObject):
    """When new scroll areas appear, swap in pill bars."""

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if et == QEvent.Type.ChildAdded:
            try:
                child = event.child()  # type: ignore[attr-defined]
            except Exception:
                child = None
            if isinstance(child, QAbstractScrollArea):
                wire_pill_scrollbars(child)
            elif isinstance(child, QWidget):
                for area in child.findChildren(QAbstractScrollArea):
                    wire_pill_scrollbars(area)
        elif et == QEvent.Type.Polish and isinstance(obj, QAbstractScrollArea):
            wire_pill_scrollbars(obj)
        return False


def install_pill_scrollbars(app: QApplication | None = None) -> None:
    """App-wide: polish existing areas + watch for new ones."""
    global _filter
    if app is None:
        app = QApplication.instance()
    if app is None:
        return
    if _filter is None:
        _filter = _PillScrollBarFilter(app)
        app.installEventFilter(_filter)
    polish_pill_scrollbars()
