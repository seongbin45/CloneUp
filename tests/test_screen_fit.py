"""DPI / resolution helpers for connect-dialog sizing."""

from __future__ import annotations

from app.util.screen_fit import clear_size_locks, largest_16x9


def test_clear_size_locks_resets_fixed_min_and_max() -> None:
    """Choice setFixedSize must not leave a sticky minimum after unlock."""

    class _W:
        def __init__(self) -> None:
            self.min_w = self.min_h = 0
            self.max_w = self.max_h = 0

        def setFixedSize(self, w: int, h: int) -> None:
            self.min_w = self.max_w = w
            self.min_h = self.max_h = h

        def setMinimumSize(self, w: int, h: int) -> None:
            self.min_w, self.min_h = w, h

        def setMaximumSize(self, w: int, h: int) -> None:
            self.max_w, self.max_h = w, h

    w = _W()
    w.setFixedSize(500, 527)
    clear_size_locks(w)
    assert w.min_w == 0 and w.min_h == 0
    assert w.max_w >= 10_000 and w.max_h >= 10_000


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
