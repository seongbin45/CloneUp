"""App-themed tooltips that ignore Windows native ToolTipBase.

Home (and many dialogs) set per-widget ``setStyleSheet``. On Windows that
breaks application-level ``QToolTip`` QSS, so Qt falls back to the OS tip
(often black). This module intercepts ``QEvent.ToolTip`` and shows a card-
colored rounded ``QFrame`` instead.

Corner radius matches home overflow / floating cards (9px). Long one-line
tips that exceed ``TIP_MAX_LINE_PX`` marquee RTL while the tip is shown
(same hover-driven pattern as the detail title).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from app.ui.marquee_label import MarqueeLabel, start_marquee_on, stop_marquee_on
from app.ui.text_fit import measure_text_width_px

# Match homeOverflowPanel / floating card guide (시안 gray stroke on curve).
TIP_RADIUS_PX = 9.0
TIP_MAX_LINE_PX = 360
TIP_FONT_PX = 12.0

_filter: "_ThemedToolTipFilter | None" = None
_popup: "_ThemedToolTipFrame | None" = None
_label: MarqueeLabel | QLabel | None = None
_hide_timer: QTimer | None = None
_host: QWidget | None = None


def _palette_colors() -> tuple[str, str, str]:
    from app.ui.theme import active_palette

    p = active_palette()
    return p.bg_window, p.text, p.border_soft


class _ThemedToolTipFrame(QFrame):
    """Frameless tip shell; corners clipped via translucent + painted path."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setObjectName("cloneUpThemedToolTip")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._bg = QColor("#fbfaf8")
        self._border = QColor("#e6e1d8")
        self._radius = TIP_RADIUS_PX

    def set_chrome(self, bg: str, border: str) -> None:
        self._bg = QColor(bg)
        self._border = QColor(border)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._bg)
        painter.drawPath(path)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._border, 1.0))
        painter.drawPath(path)


def _ensure_popup() -> tuple[_ThemedToolTipFrame, MarqueeLabel]:
    global _popup, _label
    if _popup is not None and isinstance(_label, MarqueeLabel):
        return _popup, _label

    tip = _ThemedToolTipFrame()
    lay = QVBoxLayout(tip)
    lay.setContentsMargins(10, 7, 10, 7)
    lay.setSpacing(0)
    lab = MarqueeLabel()
    lab.setObjectName("cloneUpThemedToolTipLabel")
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    lab.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    lay.addWidget(lab)

    _popup = tip
    _label = lab
    _apply_popup_chrome()
    return tip, lab


def _apply_popup_chrome() -> None:
    if _popup is None or _label is None:
        return
    bg, fg, border = _palette_colors()
    _popup.set_chrome(bg, border)
    _popup.setStyleSheet(
        "QFrame#cloneUpThemedToolTip { background: transparent; border: none; }"
        f"QLabel#cloneUpThemedToolTipLabel {{"
        f" background: transparent; color: {fg};"
        f" font-size: {TIP_FONT_PX}px;"
        f"}}"
    )


def hide_themed_tooltip() -> None:
    global _hide_timer, _host
    if _hide_timer is not None:
        _hide_timer.stop()
    _host = None
    if isinstance(_label, MarqueeLabel):
        stop_marquee_on(_label, reset=True)
    if _popup is not None and _popup.isVisible():
        _popup.hide()
    try:
        from PySide6.QtWidgets import QToolTip

        QToolTip.hideText()
    except Exception:
        pass


def show_themed_tooltip(
    text: str,
    global_pos: QPoint | None = None,
    *,
    host: QWidget | None = None,
) -> None:
    global _host
    text = (text or "").strip()
    if not text:
        hide_themed_tooltip()
        return

    _host = host
    tip, lab = _ensure_popup()
    _apply_popup_chrome()
    _, fg, _ = _palette_colors()

    # One-line tip: if wider than TIP_MAX_LINE_PX → hover-style marquee while shown.
    lab.set_marquee_text(
        text,
        max_width_px=float(TIP_MAX_LINE_PX),
        pixel_size=TIP_FONT_PX,
        bold=False,
        color=fg,
        align_center=False,
    )
    if lab.needs_marquee():
        tip.setFixedWidth(TIP_MAX_LINE_PX + 20)  # + horizontal margins
        start_marquee_on(lab)
    else:
        tip.setMinimumWidth(0)
        tip.setMaximumWidth(16777215)
        # Natural width for short tips
        w = int(measure_text_width_px(text, TIP_FONT_PX) + 24)
        tip.setFixedWidth(max(40, min(TIP_MAX_LINE_PX + 20, w)))

    tip.adjustSize()

    pos = global_pos if global_pos is not None else QCursor.pos()
    x = pos.x() + 12
    y = pos.y() + 18

    screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
    if screen is not None:
        geo = screen.availableGeometry()
        w = tip.width()
        h = tip.height()
        if x + w > geo.right():
            x = geo.right() - w - 4
        if y + h > geo.bottom():
            y = pos.y() - h - 8
        if x < geo.left():
            x = geo.left() + 4
        if y < geo.top():
            y = geo.top() + 4

    tip.move(x, y)
    tip.show()
    tip.raise_()

    global _hide_timer
    if _hide_timer is None:
        _hide_timer = QTimer()
        _hide_timer.setSingleShot(True)
        _hide_timer.timeout.connect(hide_themed_tooltip)
    _hide_timer.start(10_000)


class _ThemedToolTipFilter(QObject):
    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if et == QEvent.Type.ToolTip:
            if not isinstance(obj, QWidget):
                return False
            text = obj.toolTip()
            if not text:
                hide_themed_tooltip()
                return False
            # MarqueeLabel hosts already scroll their own text — skip nested tip.
            if isinstance(obj, MarqueeLabel) and obj.needs_marquee():
                return True
            gpos = None
            try:
                gpos = event.globalPos()  # type: ignore[attr-defined]
            except Exception:
                gpos = QCursor.pos()
            show_themed_tooltip(text, gpos, host=obj)
            return True

        if _popup is None or not _popup.isVisible():
            return False

        if et in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            if obj is _host:
                hide_themed_tooltip()
            return False

        if et in (
            QEvent.Type.Wheel,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.WindowDeactivate,
        ):
            hide_themed_tooltip()
            return False

        if et == QEvent.Type.Hide and obj is _host:
            hide_themed_tooltip()
        return False


def refresh_themed_tooltip_chrome() -> None:
    """Re-apply card colors after light/dark flip."""
    _apply_popup_chrome()


def install_themed_tooltips(app: QApplication | None = None) -> None:
    """Install once on the QApplication; safe to call on every theme apply."""
    global _filter
    if app is None:
        app = QApplication.instance()
    if app is None:
        return
    if _filter is None:
        _filter = _ThemedToolTipFilter(app)
        app.installEventFilter(_filter)
    refresh_themed_tooltip_chrome()
    try:
        from app.ui.theme import apply_tooltip_palette, active_palette

        apply_tooltip_palette(app, active_palette())
    except Exception:
        pass
