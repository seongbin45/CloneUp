"""Font fitting for sidebar / overflow labels."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from app.ui.text_fit import (
    apply_fitting_font,
    fit_font_px,
    measure_text_width_px,
    sidebar_label_budget_px,
)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_longest_overflow_copy_metrics(qapp: QApplication) -> None:
    # Sidebar 206px → overflow panel ~190; label budget ~170 before safety.
    budget = sidebar_label_budget_px(
        sidebar_w=190, row_margin_x=0, row_pad_x=16, icon_w=0, gap=0
    )
    assert 140 <= budget <= 180
    long = "Git 없음 — 설치 방법…"
    at_base = measure_text_width_px(long, 12.5)
    # Document: longest menu title is ~11–14em at 12.5px depending on face.
    em = at_base / 12.5
    assert 9.0 <= em <= 16.0
    tight = 100.0
    shrunk = fit_font_px(long, tight, base_px=12.5, min_px=9.0)
    assert shrunk <= 12.5
    # At min size Korean may still exceed a very tight budget — elide handles it.
    lab = QLabel()
    apply_fitting_font(lab, long, tight, base_px=12.5, min_px=9.0)
    assert lab.toolTip() == long
    assert len(lab.text()) <= len(long)


def test_breakable_path_wraps_and_keeps_readable_size(qapp: QApplication) -> None:
    from app.ui.text_fit import (
        DETAIL_FACT_VALUE_W,
        breakable_path,
        fit_font_px_box,
        measure_wrapped_size_px,
    )

    path = r"C:\Users\seong\Desktop\ProJect\Codyssey_2+1_ProJect\CloneUp"
    broken = breakable_path(path)
    assert "\u200b" in broken
    px = fit_font_px_box(
        broken,
        DETAIL_FACT_VALUE_W,
        96,
        base_px=12.5,
        min_px=10.0,
        allow_long_tokens=True,
    )
    assert px >= 10.0
    _w, h = measure_wrapped_size_px(broken, px, DETAIL_FACT_VALUE_W)
    assert h <= 96 + 2
    assert h > 14  # more than one line


def test_detail_panel_budgets(qapp: QApplication) -> None:
    from app.ui.text_fit import (
        DETAIL_CONTENT_W,
        DETAIL_FACT_VALUE_W,
        DETAIL_TITLE_BASE_PX,
        DETAIL_TITLE_MIN_PX,
        detail_content_width,
        detail_fact_value_width,
        fit_font_px_box,
        measure_wrapped_size_px,
    )

    assert detail_content_width(286, 16) == DETAIL_CONTENT_W
    assert detail_fact_value_width(286, 16, 74, 10) == DETAIL_FACT_VALUE_W
    # em at 12.5px
    assert abs(DETAIL_CONTENT_W / 12.5 - 20.32) < 0.1
    assert abs(DETAIL_FACT_VALUE_W / 12.5 - 13.6) < 0.1
    long_name = "VeryLongProjectNameWithoutSpaces12345"
    px = fit_font_px_box(
        long_name,
        DETAIL_CONTENT_W,
        52,
        base_px=DETAIL_TITLE_BASE_PX,
        min_px=DETAIL_TITLE_MIN_PX,
        bold=True,
    )
    assert DETAIL_TITLE_MIN_PX <= px <= DETAIL_TITLE_BASE_PX
    _w, h = measure_wrapped_size_px(long_name, px, DETAIL_CONTENT_W, bold=True)
    assert h <= 52 + 2


def test_apply_fitting_font_sets_smaller_css(qapp: QApplication) -> None:
    lab = QLabel()
    full = "도움말 · 시작 안내"
    px = apply_fitting_font(
        lab, full, 70.0, base_px=12.5, min_px=9.0, color="#232019"
    )
    assert px <= 12.5
    assert "font-size:" in lab.styleSheet()
    # May elide when budget is tighter than min font allows
    assert lab.toolTip() == full
    assert full.startswith(lab.text().rstrip("…").rstrip(".")) or "…" in lab.text()
