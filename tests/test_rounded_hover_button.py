"""Home ◀/▶: 시안 5px radius, not eaten by app QPushButton QSS."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QPushButton

from app.ui.home_chrome import RoundedHoverButton
from app.ui.home_tokens import home_chrome_colors
from app.ui.theme import LIGHT, app_stylesheet, apply_palette


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_rounded_hover_is_not_qpushbutton() -> None:
    _app()
    btn = RoundedHoverButton(radius=5.0, pill=False)
    assert not isinstance(btn, QPushButton)


def test_sian_radius_is_five_px() -> None:
    _app()
    apply_palette(LIGHT)
    btn = RoundedHoverButton(radius=5.0, pill=False)
    btn.setFixedSize(24, 24)
    rect = QRectF(0.5, 0.5, 23.0, 23.0)
    assert btn._effective_radius(rect) == 5.0


def test_app_qpushbutton_qss_does_not_inflate_size() -> None:
    app = _app()
    apply_palette(LIGHT)
    app.setStyleSheet(app_stylesheet(LIGHT))
    btn = RoundedHoverButton(radius=5.0, pill=False)
    btn.setFixedSize(24, 24)
    btn.show()
    app.processEvents()
    assert btn.width() == 24
    assert btn.height() == 24


def test_idle_fill_matches_sidebar_not_black() -> None:
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QCursor

    app = _app()
    apply_palette(LIGHT)
    app.setStyleSheet(app_stylesheet(LIGHT))
    hc = home_chrome_colors()
    btn = RoundedHoverButton(radius=5.0, pill=False)
    btn.setFixedSize(24, 24)
    btn.set_chrome(idle=hc.bg_sidebar, hover=hc.nav_hover, press=hc.nav_selected)
    assert btn._idle_bg.name() == hc.bg_sidebar
    btn.show()
    app.processEvents()
    # Cursor may sit over the widget after show — force leave for idle paint.
    QCursor.setPos(0, 0)
    app.sendEvent(btn, QEvent(QEvent.Type.Leave))
    app.processEvents()
    img = btn.grab().toImage()
    c = img.pixelColor(img.width() // 2, img.height() // 2)
    assert c.name() == hc.bg_sidebar
    assert c.name() != "#000000"
    assert c.name() != LIGHT.bg_window


def test_hover_corners_stay_sidebar_not_window() -> None:
    """Hover chip is 5px-rounded; square corners must stay top-bar, not #fbfaf8."""
    app = _app()
    apply_palette(LIGHT)
    app.setStyleSheet(app_stylesheet(LIGHT))
    hc = home_chrome_colors()
    btn = RoundedHoverButton(radius=5.0, pill=False)
    btn.setFixedSize(24, 24)
    btn.set_chrome(idle=hc.bg_sidebar, hover=hc.nav_hover, press=hc.nav_selected)
    btn.setDown(True)  # force press chip without needing real cursor hover
    btn.show()
    app.processEvents()
    img = btn.grab().toImage()
    corner = img.pixelColor(0, 0)
    center = img.pixelColor(img.width() // 2, img.height() // 2)
    assert corner.name() == hc.bg_sidebar
    assert corner.name() != LIGHT.bg_window
    assert center.name() == hc.nav_selected
