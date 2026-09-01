"""DPI-aware window sizing helpers for varying monitor resolutions/scales.

Qt logical pixels already incorporate devicePixelRatio when High DPI is on.
Prefer ``availableGeometry()`` (taskbar-safe work area) over ``geometry()``
+ FullScreen, which mis-sizes on scaled displays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Qt default max widget size
_QWIDGETSIZE_MAX = 16777215


@dataclass(frozen=True)
class ScreenInfo:
    """Snapshot of the screen the dialog should use (logical pixels)."""

    available_x: int
    available_y: int
    available_w: int
    available_h: int
    full_w: int
    full_h: int
    dpr: float  # devicePixelRatio

    @property
    def available(self) -> tuple[int, int, int, int]:
        return (
            self.available_x,
            self.available_y,
            self.available_w,
            self.available_h,
        )


def screen_for_widget(widget: Any = None, *, anchor: Any = None) -> Any:
    """Best QScreen for a dialog (anchor → widget → primary)."""
    from PySide6.QtGui import QGuiApplication

    screen = None
    if anchor is not None and hasattr(anchor, "screen"):
        try:
            screen = anchor.screen()
        except Exception:
            screen = None
    if screen is None and widget is not None and hasattr(widget, "screen"):
        try:
            screen = widget.screen()
        except Exception:
            screen = None
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    return screen


def read_screen_info(screen: Any) -> ScreenInfo | None:
    if screen is None:
        return None
    try:
        avail = screen.availableGeometry()
        full = screen.geometry()
        dpr = float(screen.devicePixelRatio())
        return ScreenInfo(
            available_x=int(avail.x()),
            available_y=int(avail.y()),
            available_w=max(1, int(avail.width())),
            available_h=max(1, int(avail.height())),
            full_w=max(1, int(full.width())),
            full_h=max(1, int(full.height())),
            dpr=dpr if dpr > 0 else 1.0,
        )
    except Exception:
        return None


def largest_16x9(
    avail_w: int,
    avail_h: int,
    *,
    inset: float = 0.90,
    min_w: int = 960,
    min_h: int = 540,
) -> tuple[int, int]:
    """
    Largest 16:9 client size that fits in the work area.

    Mins shrink on small / highly-scaled displays so the window still fits.
    """
    margin = 32
    fit_w = max(320, avail_w - margin)
    fit_h = max(240, avail_h - margin)
    # Soft floors — never exceed the work area
    floor_w = min(min_w, fit_w)
    floor_h = min(min_h, fit_h)
    box_w = max(floor_w, int(avail_w * inset))
    box_h = max(floor_h, int(avail_h * inset))
    box_w = min(box_w, fit_w)
    box_h = min(box_h, fit_h)
    if box_w / max(box_h, 1) >= 16 / 9:
        h = box_h
        w = int(h * 16 / 9)
    else:
        w = box_w
        h = int(w * 9 / 16)
    w = max(floor_w, min(w, fit_w))
    h = max(floor_h, min(h, fit_h))
    # Re-clamp ratio after mins
    if w / max(h, 1) > 16 / 9:
        w = max(floor_w, int(h * 16 / 9))
    else:
        h = max(floor_h, int(w * 9 / 16))
    w = min(w, fit_w)
    h = min(h, fit_h)
    return w, h


def compute_choice_dialog_size(
    avail_w: int,
    avail_h: int,
    *,
    hint_w: int = 500,
    hint_h: int = 480,
) -> tuple[int, int]:
    """
    Compact intro/choice dialog client size (logical px).

    Keeps the 시안 ~500× card on both ultrawide (2880×1080) and standard
    1080p (1920×1080), including common DPI scales (125%/150%).
    """
    pw = max(1, int(hint_w))
    phh = max(1, int(hint_h))
    w = max(500, min(540, max(pw + 8, 500)))
    h = max(400, min(600, phh + 8))
    aw = max(1, int(avail_w))
    ah = max(1, int(avail_h))
    w = min(w, max(400, aw - 48))
    h = min(h, max(380, ah - 48))
    # Never taller/wider than the work area itself.
    w = max(320, min(w, aw - 16))
    h = max(280, min(h, ah - 16))
    return int(w), int(h)


def center_client_in_available(
    avail_x: int,
    avail_y: int,
    avail_w: int,
    avail_h: int,
    client_w: int,
    client_h: int,
    *,
    chrome_w: int = 26,
    chrome_h: int = 71,
) -> tuple[int, int, int, int]:
    """
    Return ``(client_x, client_y, client_w, client_h)`` centered in the work area.

    ``chrome_*`` approximates Win10/11 frame (title + borders) so the *frame*
    stays inside availableGeometry. Used to avoid: resize() while still
    Maximized / restore of a remembered tall-thin "normal" geometry, which
    left the intro card as a vertical strip on 1920×1080.
    """
    cw = max(320, int(client_w))
    ch = max(280, int(client_h))
    aw = max(1, int(avail_w))
    ah = max(1, int(avail_h))
    # Shrink client if frame would not fit.
    max_cw = max(320, aw - max(0, int(chrome_w)) - 8)
    max_ch = max(280, ah - max(0, int(chrome_h)) - 8)
    cw = min(cw, max_cw)
    ch = min(ch, max_ch)
    frame_w = cw + max(0, int(chrome_w))
    frame_h = ch + max(0, int(chrome_h))
    frame_x = int(avail_x) + max(0, (aw - frame_w) // 2)
    frame_y = int(avail_y) + max(0, (ah - frame_h) // 2)
    # Clamp frame inside work area.
    if frame_x + frame_w > int(avail_x) + aw:
        frame_x = int(avail_x) + aw - frame_w
    if frame_y + frame_h > int(avail_y) + ah:
        frame_y = int(avail_y) + ah - frame_h
    frame_x = max(int(avail_x), frame_x)
    frame_y = max(int(avail_y), frame_y)
    # Client origin ≈ frame + left/top chrome; use half chrome as approx.
    left = max(0, int(chrome_w) // 2)
    top = max(0, int(chrome_h) - max(0, int(chrome_w) // 2))
    return frame_x + left, frame_y + top, cw, ch


def clear_size_locks(widget: Any) -> None:
    """Remove fixed / min / max size locks that block maximize or resize.

    ``setFixedSize`` sets both min and max. Clearing only max left a sticky
    minimum (e.g. choice 500×527) that fought WebView maximize and flooded
    the console with ``QWindowsWindow::setGeometry`` warnings.
    """
    try:
        widget.setMinimumSize(0, 0)
    except Exception:
        pass
    try:
        widget.setMaximumSize(_QWIDGETSIZE_MAX, _QWIDGETSIZE_MAX)
    except Exception:
        pass


def apply_work_area_maximized(widget: Any, *, anchor: Any = None) -> None:
    """
    Maximize into the taskbar-safe work area (DPI-aware).

    Uses ``showMaximized()`` so the window manager places the frame correctly
    under the current display scale — avoids FullScreen + raw geometry bugs.
    """
    from PySide6.QtCore import Qt

    clear_size_locks(widget)
    # Drop FullScreen / Maximized so we can re-apply cleanly
    try:
        st = widget.windowState()
        if st & Qt.WindowState.WindowFullScreen:
            widget.setWindowState(st & ~Qt.WindowState.WindowFullScreen)
        if st & Qt.WindowState.WindowMaximized:
            widget.setWindowState(
                widget.windowState() & ~Qt.WindowState.WindowMaximized
            )
    except Exception:
        pass
    try:
        widget.showNormal()
    except Exception:
        pass
    # Soft floor only — do not force 960×540 (that inflated frames on
    # scaled displays and triggered setGeometry warnings before maximize).
    screen = screen_for_widget(widget, anchor=anchor)
    info = read_screen_info(screen)
    if info is not None:
        try:
            mw = min(640, max(320, info.available_w - 48))
            mh = min(360, max(240, info.available_h - 48))
            widget.setMinimumSize(mw, mh)
        except Exception:
            pass
    try:
        widget.showMaximized()
    except Exception:
        if info is not None:
            widget.setGeometry(
                info.available_x,
                info.available_y,
                info.available_w,
                info.available_h,
            )


def fit_client_in_available(
    widget: Any,
    width: int,
    height: int,
    *,
    anchor: Any = None,
    keep_16x9: bool = False,
    lock_height: bool = False,
) -> None:
    """
    Resize/move so the window frame sits inside availableGeometry.

    On Windows ``setGeometry`` is the *client* rect — account for frame chrome.
    """
    from PySide6.QtWidgets import QApplication

    screen = screen_for_widget(widget, anchor=anchor)
    info = read_screen_info(screen)
    if info is None:
        widget.resize(width, height)
        return

    clear_size_locks(widget)
    widget.resize(width, height)
    app = QApplication.instance()
    if app is not None:
        app.processEvents()

    fg = widget.frameGeometry()
    geo = widget.geometry()
    chrome_l = max(0, geo.x() - fg.x())
    chrome_t = max(0, geo.y() - fg.y())
    chrome_r = max(0, fg.right() - geo.right())
    chrome_b = max(0, fg.bottom() - geo.bottom())

    avail_w, avail_h = info.available_w, info.available_h
    max_cw = max(320, avail_w - chrome_l - chrome_r - 8)
    max_ch = max(240, avail_h - chrome_t - chrome_b - 8)
    cw = min(width, max_cw)
    ch = min(height, max_ch)

    if keep_16x9 and width > 0 and height > 0:
        if cw / max(ch, 1) > 16 / 9:
            cw = max(320, int(ch * 16 / 9))
        else:
            ch = max(240, int(cw * 9 / 16))
        cw = min(cw, max_cw)
        ch = min(ch, max_ch)
        if cw / max(ch, 1) > 16 / 9:
            cw = int(ch * 16 / 9)
        else:
            ch = int(cw * 9 / 16)

    if cw != widget.width() or ch != widget.height():
        widget.resize(cw, ch)
        if app is not None:
            app.processEvents()
        fg = widget.frameGeometry()
        geo = widget.geometry()
        chrome_l = max(0, geo.x() - fg.x())
        chrome_t = max(0, geo.y() - fg.y())
        chrome_r = max(0, fg.right() - geo.right())
        chrome_b = max(0, fg.bottom() - geo.bottom())
        cw, ch = widget.width(), widget.height()

    frame_w = cw + chrome_l + chrome_r
    frame_h = ch + chrome_t + chrome_b
    frame_x = info.available_x + max(0, (avail_w - frame_w) // 2)
    frame_y = info.available_y + max(0, (avail_h - frame_h) // 2)
    if frame_x + frame_w - 1 > info.available_x + avail_w - 1:
        frame_x = info.available_x + avail_w - frame_w
    if frame_y + frame_h - 1 > info.available_y + avail_h - 1:
        frame_y = info.available_y + avail_h - frame_h
    frame_x = max(frame_x, info.available_x)
    frame_y = max(frame_y, info.available_y)

    widget.setGeometry(frame_x + chrome_l, frame_y + chrome_t, cw, ch)
    if lock_height:
        try:
            widget.setMaximumHeight(ch)
        except Exception:
            pass


def place_normal_16x9(widget: Any, *, anchor: Any = None) -> None:
    """□ restore: largest 16:9 in the work area, centered."""
    screen = screen_for_widget(widget, anchor=anchor)
    info = read_screen_info(screen)
    if info is None:
        widget.resize(1280, 720)
        return
    w, h = largest_16x9(info.available_w, info.available_h)
    # Soft floor — keep ≤640×360 so □-restore does not fight maximize
    # with a sticky 960×540 minimum (setGeometry spam on scaled displays).
    try:
        widget.setMinimumSize(min(640, w), min(360, h))
    except Exception:
        pass
    fit_client_in_available(
        widget, w, h, anchor=anchor, keep_16x9=True, lock_height=True
    )
