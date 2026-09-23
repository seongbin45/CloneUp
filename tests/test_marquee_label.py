"""MarqueeLabel: elide at rest, RTL scroll on hover when still overflowing."""

from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from app.ui.marquee_label import MarqueeLabel
from app.ui.text_fit import measure_text_width_px
from app.ui.theme import LIGHT, apply_palette
from app.ui import themed_tooltip as tt


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_short_text_does_not_need_marquee() -> None:
    _app()
    apply_palette(LIGHT)
    lab = MarqueeLabel()
    lab.set_marquee_text(
        "짧은 제목",
        max_width_px=200,
        pixel_size=15,
        bold=True,
        color=LIGHT.text,
    )
    assert lab.needs_marquee() is False
    assert lab.text() == "짧은 제목"


def test_long_text_elides_and_marquees_on_hover() -> None:
    app = _app()
    apply_palette(LIGHT)
    lab = MarqueeLabel()
    long_name = "아주-긴-프로젝트-폴더-이름-" * 6
    lab.setFixedWidth(180)
    lab.set_marquee_text(
        long_name,
        max_width_px=180,
        pixel_size=11,
        bold=True,
        color=LIGHT.text,
    )
    assert lab.needs_marquee() is True
    assert lab.text() != long_name
    assert "…" in lab.text() or len(lab.text()) < len(long_name)

    lab.show()
    app.processEvents()
    app.sendEvent(lab, QEvent(QEvent.Type.Enter))
    app.processEvents()
    assert lab._scrolling is True
    assert lab.text() == ""

    app.sendEvent(lab, QEvent(QEvent.Type.Leave))
    app.processEvents()
    assert lab._scrolling is False
    assert lab.text() != ""


def test_long_tooltip_uses_marquee_while_shown() -> None:
    app = _app()
    apply_palette(LIGHT)
    tt.install_themed_tooltips(app)
    long_path = "C:\\Users\\seong\\Desktop\\" + ("VeryLongFolderName\\" * 8)
    assert measure_text_width_px(long_path, tt.TIP_FONT_PX) > tt.TIP_MAX_LINE_PX

    try:
        tt.show_themed_tooltip(long_path)
        app.processEvents()
        assert tt._popup is not None and tt._popup.isVisible()
        assert isinstance(tt._label, MarqueeLabel)
        assert tt._label.needs_marquee() is True
        assert tt._label._scrolling is True
    finally:
        tt.hide_themed_tooltip()
        assert not getattr(tt._label, "_scrolling", False)
