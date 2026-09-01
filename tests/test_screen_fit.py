"""DPI / resolution helpers for connect-dialog sizing."""

from __future__ import annotations

from app.util.screen_fit import (
    accept_choice_client_size,
    center_client_in_available,
    choice_size_near,
    clear_size_locks,
    compute_choice_dialog_size,
    guard_choice_client_size,
    largest_16x9,
    sanitize_choice_chrome,
)


def test_sanitize_choice_chrome_rejects_absurd_restore_deltas() -> None:
    assert sanitize_choice_chrome(26, 71) == (26, 71)
    assert sanitize_choice_chrome(8, 20) == (8, 20)
    assert sanitize_choice_chrome(48, 120) == (48, 120)
    # Post-maximize junk → defaults
    assert sanitize_choice_chrome(1700, 900) == (26, 71)
    assert sanitize_choice_chrome(0, 10) == (26, 71)
    assert sanitize_choice_chrome(100, 50) == (26, 71)


def test_guard_choice_client_size_rejects_strip() -> None:
    assert guard_choice_client_size(508, 528) == (508, 528)
    w, h = guard_choice_client_size(320, 600)
    assert w >= 450
    assert w / h >= 0.75


def test_choice_size_near_tolerance() -> None:
    assert choice_size_near(500, 527, 500, 527)
    assert choice_size_near(500, 535, 500, 527, tol=16)
    assert not choice_size_near(500, 593, 500, 527, tol=16)


def test_accept_choice_client_size_stops_dpi_fight() -> None:
    """Windows dpr=2 often yields taller client than requested — accept it."""
    assert accept_choice_client_size(500, 527, 500, 530) == (500, 527)
    assert accept_choice_client_size(500, 527, 500, 593) == (500, 593)
    # Runaway maximize-sized actual must not lock fullscreen choice shell
    w, h = accept_choice_client_size(500, 527, 1440, 852)
    assert w <= 500 + 80
    assert h <= 527 + 120


def test_absurd_chrome_plus_center_does_not_lock_strip() -> None:
    """Simulate uncapped chrome shrinking width, then guard restores card."""
    cw, ch = sanitize_choice_chrome(1800, 40)
    x, y, w, h = center_client_in_available(
        0, 0, 1920, 1040, 508, 528, chrome_w=cw, chrome_h=ch
    )
    # With sanitized chrome, width stays compact-card sized
    assert w >= 450
    w2, h2 = guard_choice_client_size(320, 900)
    assert w2 >= 450 and w2 / h2 >= 0.75


def test_compute_choice_dialog_size_stable_across_1080p_and_ultrawide() -> None:
    """1920×1080 and 2880×1080 must both get a compact ~500× card, not a strip."""
    for aw, ah in ((1920, 1040), (1536, 864), (1280, 720), (2880, 1040)):
        w, h = compute_choice_dialog_size(aw, ah, hint_w=500, hint_h=520)
        assert 400 <= w <= 540, (aw, ah, w, h)
        assert 380 <= h <= 600, (aw, ah, w, h)
        assert w < aw * 0.5, "choice width must stay narrow vs screen"
        assert h < ah * 0.85, "choice height must not fill the screen"


def test_center_client_in_available_keeps_frame_inside() -> None:
    x, y, w, h = center_client_in_available(
        0, 0, 1920, 1040, 508, 528, chrome_w=26, chrome_h=71
    )
    assert w == 508 and h == 528
    # Frame roughly inside work area
    assert x >= 0 and y >= 0
    assert x + w + 13 <= 1920
    assert y + h + 20 <= 1040
    # Near horizontal center
    assert abs((x + w / 2) - 960) < 80


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
