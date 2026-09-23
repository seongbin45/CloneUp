"""Global pill scrollbar QSS must be present and rounded."""

from __future__ import annotations

from app.ui.theme import DARK, LIGHT, app_stylesheet, scrollbar_qss


def test_scrollbar_qss_is_pill_shaped() -> None:
    qss = scrollbar_qss(LIGHT)
    assert "QScrollBar:vertical" in qss
    assert "border-radius: 5px" in qss
    assert "width: 10px" in qss
    assert LIGHT.border_outline in qss
    # Arrow buttons removed — clean capsule track.
    assert "height: 0px" in qss

    dark = scrollbar_qss(DARK)
    assert DARK.border_outline in dark
    assert "border-radius: 5px" in dark


def test_app_stylesheet_includes_scrollbar() -> None:
    qss = app_stylesheet(LIGHT)
    assert "QScrollBar:vertical" in qss
    assert "QScrollBar::handle:vertical" in qss
