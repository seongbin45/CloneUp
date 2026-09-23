"""Single-line label that marquees RTL on hover when text still overflows.

Used after ``text_fit`` has already shrunk px/em to the floor: idle shows an
elided line; hover scrolls the full string right→left and loops.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from app.ui.text_fit import _safe_pixel_size, measure_text_width_px

# px / frame at ~60fps · gap between loop copies
_DEFAULT_SPEED_PPS = 48.0
_LOOP_GAP_PX = 36.0


class MarqueeLabel(QLabel):
    """QLabel with optional hover marquee when *full* text exceeds *max_width*."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full = text or ""
        self._max_w = 0
        self._px = 12.5
        self._bold = False
        self._color = QColor("#232019")
        self._offset = 0.0
        self._scrolling = False
        self._needs = False
        self._speed = _DEFAULT_SPEED_PPS
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setWordWrap(False)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_marquee_text(
        self,
        text: str,
        *,
        max_width_px: float,
        pixel_size: float,
        bold: bool = False,
        color: str = "",
        align_center: bool = True,
    ) -> None:
        """Configure full text + viewport. Elides when overflowing; marquees on hover."""
        self._stop_scroll(reset=True)
        self._full = text or ""
        self._max_w = max(1, int(max_width_px))
        self._px = max(1.0, float(pixel_size))
        self._bold = bool(bold)
        if color:
            self._color = QColor(color)
        self.setMaximumWidth(self._max_w)
        self.setMinimumWidth(0)

        f = QFont(self.font())
        f.setPixelSize(_safe_pixel_size(self._px))
        f.setBold(self._bold)
        self.setFont(f)

        weight = "600" if self._bold else "400"
        color_css = f" color: {self._color.name()};" if self._color.isValid() else ""
        align = "center" if align_center else "left"
        self.setStyleSheet(
            f"font-size: {self._px}px; font-weight: {weight};"
            f" background: transparent;{color_css}"
        )
        h = (
            Qt.AlignmentFlag.AlignHCenter
            if align_center
            else Qt.AlignmentFlag.AlignLeft
        )
        self.setAlignment(h | Qt.AlignmentFlag.AlignVCenter)

        full_w = measure_text_width_px(
            self._full, self._px, bold=self._bold
        )
        self._needs = bool(self._full) and full_w > self._max_w + 1.0
        if self._needs:
            fm = QFontMetrics(f)
            elided = fm.elidedText(
                self._full,
                Qt.TextElideMode.ElideRight,
                self._max_w,
            )
            self.setText(elided)
            # Hover marquee replaces a static tip for overflowing titles.
            self.setToolTip("")
        else:
            self.setText(self._full)
            self.setToolTip("")
        self.updateGeometry()
        self.update()

    def needs_marquee(self) -> bool:
        return self._needs

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        if self._needs and self._full:
            self._start_scroll()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._stop_scroll(reset=True)

    def _start_scroll(self) -> None:
        self._scrolling = True
        self._offset = 0.0
        # Clear QLabel text so super paint does not fight custom draw
        self.setText("")
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def _stop_scroll(self, *, reset: bool) -> None:
        self._scrolling = False
        self._timer.stop()
        if reset:
            self._offset = 0.0
            if self._needs and self._full:
                f = self.font()
                fm = QFontMetrics(f)
                elided = fm.elidedText(
                    self._full,
                    Qt.TextElideMode.ElideRight,
                    max(1, self._max_w),
                )
                self.setText(elided)
            elif self._full:
                self.setText(self._full)
        self.update()

    def _tick(self) -> None:
        if not self._scrolling:
            return
        dt = self._timer.interval() / 1000.0
        self._offset += self._speed * dt
        text_w = measure_text_width_px(self._full, self._px, bold=self._bold)
        loop = text_w + _LOOP_GAP_PX
        if loop > 0 and self._offset >= loop:
            self._offset -= loop
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._scrolling:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self.font())
        painter.setPen(self._color)
        painter.setClipRect(QRectF(self.rect()))

        fm = QFontMetrics(self.font())
        text_w = float(fm.horizontalAdvance(self._full))
        y = (self.height() + fm.ascent() - fm.descent()) / 2.0
        x = -self._offset
        painter.drawText(int(round(x)), int(round(y)), self._full)
        # Second copy for seamless loop
        painter.drawText(
            int(round(x + text_w + _LOOP_GAP_PX)),
            int(round(y)),
            self._full,
        )

    def sizeHint(self):  # noqa: N802
        sh = super().sizeHint()
        if self._max_w > 0:
            sh.setWidth(min(sh.width(), self._max_w) if sh.width() > 0 else self._max_w)
        # One line height from font
        fm = QFontMetrics(self.font())
        sh.setHeight(max(sh.height(), fm.height() + 2))
        return sh


def start_marquee_on(widget: MarqueeLabel) -> None:
    """Start scroll without a real enter (e.g. tooltip while tip is shown)."""
    if widget.needs_marquee():
        widget._start_scroll()


def stop_marquee_on(widget: MarqueeLabel, *, reset: bool = True) -> None:
    widget._stop_scroll(reset=reset)
