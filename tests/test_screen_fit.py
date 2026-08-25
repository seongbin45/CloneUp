"""DPI / resolution helpers for connect-dialog sizing."""

from __future__ import annotations

from app.util.screen_fit import largest_16x9


def test_largest_16x9_fits_common_desktops() -> None:
    w, h = largest_16x9(1920, 1040)  # 1080p minus taskbar
    assert w <= 1920 and h <= 1040
    assert abs(w / h - 16 / 9) < 0.05


def test_largest_16x9_shrinks_on_small_scaled_laptop() -> None:
    # 1366×768 at high scale → small available area
    w, h = largest_16x9(900, 500, min_w=960, min_h=540)
    assert w <= 900 - 32
    assert h <= 500 - 32
    assert w >= 320 and h >= 240


def test_largest_16x9_ultrawide() -> None:
    w, h = largest_16x9(3440, 1400)
    assert abs(w / h - 16 / 9) < 0.05
    assert h <= 1400
