"""Home search wrap must paint a full capsule (Win QSS radius is ignored)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app.ui.home_chrome import PillFrame
from app.ui.home_tokens import HOME_COLORS as hc
from app.ui.theme import LIGHT, apply_palette


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_pill_frame_corners_match_outer_not_fill() -> None:
    app = _app()
    apply_palette(LIGHT)
    pill = PillFrame()
    pill.setFixedSize(216, 28)
    pill.set_pill_chrome(
        fill=hc.bg_window,
        border=hc.cta_quiet_border,
        outer=hc.bg_sidebar,
    )
    pill.show()
    app.processEvents()
    img = pill.grab().toImage()
    # Sharp QSS rect would leave fill cream at (0,0). Capsule leaves outer bar.
    corner = img.pixelColor(0, 0)
    center = img.pixelColor(img.width() // 2, img.height() // 2)
    assert corner.name() == hc.bg_sidebar
    assert center.name() == hc.bg_window
    assert corner.name() != center.name()
