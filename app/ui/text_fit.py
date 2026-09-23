"""Shrink label font until text fits a max width (home sidebar / overflow)."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QLabel

# Home sidebar is 206px; overflow panel ≈ side−16.
# Longest KO menu copy we ship (approx at 12.5px):
#   "도움말 · 시작 안내"     ~ 10em
#   "Git 없음 — 설치 방법…"  ~ 14em
# With row pad 10+10 and optional hint, label budget is often ~120–150px
# (~9.5–12em at 12.5px). Below that we shrink rather than clip.
DEFAULT_BASE_PX = 12.5
DEFAULT_MIN_PX = 9.5  # ~0.76em of base — still readable in sidebar


def _safe_pixel_size(pixel_size: float) -> int:
    """Qt forbids setPixelSize(0); always return >= 1."""
    try:
        n = int(round(float(pixel_size)))
    except (TypeError, ValueError):
        n = 1
    return max(1, n)


def measure_text_width_px(text: str, pixel_size: float, *, bold: bool = False) -> float:
    f = QFont()
    # Never call setPixelSize(0) — floods logs with QFont warnings.
    f.setPixelSize(_safe_pixel_size(pixel_size))
    if bold:
        f.setBold(True)
    return float(QFontMetrics(f).horizontalAdvance(text))


def fit_font_px(
    text: str,
    max_width_px: float,
    *,
    base_px: float = DEFAULT_BASE_PX,
    min_px: float = DEFAULT_MIN_PX,
    bold: bool = False,
) -> float:
    """Largest font size in [min_px, base_px] that fits *text* in *max_width_px*."""
    base = max(1.0, float(base_px))
    floor = max(1.0, float(min_px))
    if max_width_px <= 0 or not text:
        return base
    size = base
    while size > floor + 0.01:
        if measure_text_width_px(text, size, bold=bold) <= max_width_px:
            return max(1.0, size)
        size -= 0.5
    return floor


def apply_fitting_font(
    label: QLabel,
    text: str,
    max_width_px: float,
    *,
    base_px: float = DEFAULT_BASE_PX,
    min_px: float = DEFAULT_MIN_PX,
    bold: bool = False,
    color: str = "",
    extra_css: str = "",
) -> float:
    """Set *label* text + stylesheet font-size so it fits. Returns px used.

    If even *min_px* overflows, keep min size and elide the middle with a
    tooltip holding the full string.
    """
    from PySide6.QtCore import Qt

    px = max(
        1.0,
        fit_font_px(
            text, max_width_px, base_px=base_px, min_px=min_px, bold=bold
        ),
    )
    weight = "600" if bold else "400"
    color_css = f" color: {color};" if color else ""
    label.setText(text)
    label.setStyleSheet(
        f"font-size: {px}px; font-weight: {weight}; background: transparent;"
        f"{color_css} {extra_css}"
    )
    still_wide = measure_text_width_px(text, px, bold=bold) > max_width_px + 1.0
    if still_wide and max_width_px > 0:
        label.setMaximumWidth(max(1, int(max_width_px)))
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        from PySide6.QtGui import QFont, QFontMetrics

        f = QFont()
        f.setPixelSize(_safe_pixel_size(px))
        if bold:
            f.setBold(True)
        elided = QFontMetrics(f).elidedText(
            text, Qt.TextElideMode.ElideRight, max(1, int(max_width_px))
        )
        label.setText(elided)
        label.setToolTip(text)
    else:
        label.setMaximumWidth(16777215)
        if not label.toolTip():
            label.setToolTip(text)
    return px


def sidebar_label_budget_px(
    *,
    sidebar_w: int = 206,
    row_margin_x: int = 16,  # 8+8
    row_pad_x: int = 20,  # 10+10
    icon_w: int = 15,
    gap: int = 9,
    trailing_w: int = 0,  # count or hint
) -> float:
    """Available px for the main label inside a sidebar/overflow row."""
    return float(
        max(
            40,
            sidebar_w - row_margin_x - row_pad_x - icon_w - gap - trailing_w,
        )
    )


# --- Right detail panel (HOME_DETAIL_W = 286) ---------------------------------
# Content width ≈ 286 − 16×2 pad = 254px (~20.3em @12.5px).
# Fact value ≈ 254 − 74 key − 10 gap = 170px (~13.6em).
# Title base 15px (~1.2em of 12.5); subtitle 12px; note 11.5px; CTA 13–13.5px.
DETAIL_CONTENT_W = 254  # 286 − 32
DETAIL_FACT_VALUE_W = 170  # content − key74 − gap10
DETAIL_TITLE_BASE_PX = 15.0
DETAIL_TITLE_MIN_PX = 11.0  # ~0.73 of base
DETAIL_SUB_BASE_PX = 12.0
DETAIL_SUB_MIN_PX = 9.5
DETAIL_FACT_BASE_PX = 12.5
DETAIL_FACT_MIN_PX = 10.0  # paths stay readable; prefer wrap over tiny type
DETAIL_NOTE_BASE_PX = 11.5
DETAIL_NOTE_MIN_PX = 9.0
DETAIL_CTA_BASE_PX = 13.5
DETAIL_CTA_MIN_PX = 10.0
# Vertical caps (approx line boxes) so wrapped titles/notes don't blow the panel
DETAIL_TITLE_MAX_H = 52  # ~3 lines @15px
DETAIL_SUB_MAX_H = 36  # ~2 lines
DETAIL_NOTE_MAX_H = 120  # ~7–8 lines @11.5
DETAIL_FACT_MAX_H = 96  # ~5–6 lines for long paths / owner/repo


def breakable_path(text: str) -> str:
    """Insert zero-width spaces after path separators so QLabel can wrap."""
    if not text:
        return text
    # Normalize display separators first; ZWSP allows break *after* slash
    s = text.replace("\\", "/")
    return s.replace("/", "/\u200b").replace(".", ".\u200b")


def measure_wrapped_size_px(
    text: str,
    pixel_size: float,
    max_width_px: float,
    *,
    bold: bool = False,
) -> tuple[float, float]:
    """Return (width, height) of word-wrapped *text* at *pixel_size*."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontMetrics

    f = QFont()
    f.setPixelSize(_safe_pixel_size(pixel_size))
    if bold:
        f.setBold(True)
    fm = QFontMetrics(f)
    br = fm.boundingRect(
        0,
        0,
        max(1, int(max_width_px)),
        10000,
        int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
        text,
    )
    return float(br.width()), float(br.height())


def fit_font_px_box(
    text: str,
    max_width_px: float,
    max_height_px: float,
    *,
    base_px: float,
    min_px: float,
    bold: bool = False,
    allow_long_tokens: bool = False,
) -> float:
    """Fit font so wrapped text stays within width×height box.

    When *allow_long_tokens* is True (paths with ZWSP breaks), do not require
    the whole string to fit on one line — only the wrapped height matters.
    """
    base = max(1.0, float(base_px))
    floor = max(1.0, float(min_px))
    if not text or max_width_px <= 0:
        return base
    size = base
    while size > floor + 0.01:
        _w, h = measure_wrapped_size_px(
            text, size, max_width_px, bold=bold
        )
        if allow_long_tokens:
            if h <= max_height_px + 1.0:
                return max(1.0, size)
        else:
            unbroken = max(
                (
                    measure_text_width_px(tok, size, bold=bold)
                    for tok in text.split()
                ),
                default=0.0,
            )
            if h <= max_height_px + 1.0 and unbroken <= max_width_px + 2.0:
                return max(1.0, size)
        size -= 0.5
    return floor


def apply_fitting_font_box(
    label: QLabel,
    text: str,
    max_width_px: float,
    max_height_px: float,
    *,
    base_px: float,
    min_px: float,
    bold: bool = False,
    color: str = "",
    extra_css: str = "",
    align_center: bool = False,
    path_like: bool = False,
) -> float:
    """Word-wrap + shrink font to fit a box; tooltip keeps full text.

    *path_like*: insert break opportunities after ``/`` and keep readable size.
    """
    from PySide6.QtCore import Qt

    display = breakable_path(text) if path_like else text
    px = max(
        1.0,
        fit_font_px_box(
            display,
            max_width_px,
            max_height_px,
            base_px=base_px,
            min_px=min_px,
            bold=bold,
            allow_long_tokens=path_like,
        ),
    )
    weight = "600" if bold else "400"
    color_css = f" color: {color};" if color else ""
    label.setWordWrap(True)
    label.setText(display)
    label.setToolTip(text)  # original without ZWSP
    label.setMaximumWidth(max(1, int(max_width_px)))
    # Let height grow with wrapped lines (FactRow must not be vertically Fixed)
    label.setMinimumHeight(0)
    label.setMaximumHeight(max(1, int(max_height_px)))
    label.setStyleSheet(
        f"font-size: {px}px; font-weight: {weight}; background: transparent;"
        f"{color_css} {extra_css}"
    )
    if align_center:
        label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
    else:
        label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
    return px


def detail_content_width(detail_w: int = 286, pad_x: int = 16) -> float:
    return float(max(80, detail_w - pad_x * 2))


def detail_fact_value_width(
    detail_w: int = 286, pad_x: int = 16, key_w: int = 74, gap: int = 10
) -> float:
    return float(max(48, detail_w - pad_x * 2 - key_w - gap))
