"""Phase B: home shell installs as default stack page."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_home_is_default_stack(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLONEUP_LEGACY_TABS", raising=False)
    # Avoid slow dirty probes during scan in CI
    monkeypatch.setattr(
        "app.git.project_scan.scan_projects",
        lambda **_k: [],
    )
    from app.ui.main_window import load_main_window

    w = load_main_window()
    try:
        stack = w.findChild(QStackedWidget, "mainUiStack")
        assert stack is not None
        assert stack.currentIndex() == 0
        home = w.findChild(QWidget, "homeShell")
        assert home is not None
        assert getattr(w, "_cloneup_controller")._home_shell is not None
    finally:
        w.close()


def test_legacy_tabs_skips_home(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLONEUP_LEGACY_TABS", "1")
    from app.ui.main_window import load_main_window

    w = load_main_window()
    try:
        assert w.findChild(QStackedWidget, "mainUiStack") is None
        assert w.findChild(QWidget, "homeShell") is None
    finally:
        w.close()
