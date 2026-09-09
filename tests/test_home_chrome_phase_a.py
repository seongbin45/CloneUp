"""Phase A home chrome: overflow reachability, banner object names."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton, QWidget


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_phase_a_overflow_and_hidden_legacy(qapp: QApplication) -> None:
    from app.ui.main_window import load_main_window

    w = load_main_window()
    try:
        # Off-screen: isVisible() is False until show(); use isHidden() instead.
        overflow = w.findChild(QPushButton, "btnOverflowMenu")
        assert overflow is not None
        assert not overflow.isHidden()

        # Legacy chrome hidden (still in .ui until Phase B)
        for name in ("btnSettings", "btnHelpOnboarding", "btnLogout", "labelStatusGit"):
            child = w.findChild(QWidget, name)
            if child is not None:
                assert child.isHidden(), name

        ctrl = getattr(w, "_cloneup_controller", None)
        assert ctrl is not None
        assert getattr(ctrl, "git_banner", None) is not None
        banner = w.findChild(QWidget, "gitMissingBanner")
        assert banner is not None
    finally:
        w.close()


def test_settings_help_reachable_helpers(qapp: QApplication) -> None:
    from pathlib import Path

    from app.ui import main_window as mw_mod
    from app.ui.home_chrome import help_reachable, settings_reachable
    from app.ui.main_window import load_main_window

    w = load_main_window()
    try:
        src = Path(mw_mod.__file__).read_text(encoding="utf-8")
        assert settings_reachable(w, src)
        assert help_reachable(w, src)
    finally:
        w.close()
