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


def test_home_is_default_stack(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from pathlib import Path

    from PySide6.QtCore import QSettings

    monkeypatch.delenv("CLONEUP_LEGACY_TABS", raising=False)
    ini = tmp_path / "home_default.ini"

    def _factory() -> QSettings:
        return QSettings(str(ini), QSettings.Format.IniFormat)

    monkeypatch.setattr("app.ui.settings_store._settings", _factory)
    # Avoid slow dirty probes during scan in CI
    monkeypatch.setattr(
        "app.git.project_scan.scan_projects",
        lambda **_k: ([], False),
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


def test_filter_no_remote_membership(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import MagicMock

    from app.git.project_scan import ProjectEntry
    from app.ui.home_shell import FILTER_NO_REMOTE, HomeShellWidget

    monkeypatch.setattr(HomeShellWidget, "refresh_projects", lambda self: None)
    w = HomeShellWidget(MagicMock())
    try:
        w._entries = [
            ProjectEntry(
                r"C:\a\with", "with", True, 3.0, has_origin=True
            ),
            ProjectEntry(
                r"C:\a\local", "local", True, 2.0, has_origin=False
            ),
            ProjectEntry(
                r"C:\a\unknown", "unknown", True, 1.0, has_origin=None
            ),
            ProjectEntry(
                r"C:\a\plain", "plain", False, 0.5, has_origin=None
            ),
        ]
        w._select_filter(FILTER_NO_REMOTE, refresh=True)
        names = [e.name for e in w._filtered()]
        assert names == ["local"]
    finally:
        w.close()


def test_leaving_time_filter_exits_timeline(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """사이드바에서 시간순 → 다른 패널: 목록 모드로 돌아와야 한다."""
    from unittest.mock import MagicMock

    from app.git.project_scan import ProjectEntry
    from app.ui.home_shell import (
        FILTER_ALL,
        FILTER_DIRTY,
        FILTER_TIME,
        HomeShellWidget,
    )

    monkeypatch.setattr(HomeShellWidget, "refresh_projects", lambda self: None)
    w = HomeShellWidget(MagicMock())
    try:
        w._entries = [
            ProjectEntry(
                path=r"C:\proj\one", name="one", has_git=True, last_mtime=1.0
            )
        ]
        w._select_filter(FILTER_TIME, refresh=True)
        assert w._view_timeline is True
        assert w._filter == FILTER_TIME

        w._select_filter(FILTER_ALL, refresh=True)
        assert w._view_timeline is False
        assert w._filter == FILTER_ALL
        assert w._btn_list_mode.isChecked()
        assert not w._btn_time_mode.isChecked()

        w._select_filter(FILTER_TIME, refresh=True)
        w._select_filter(FILTER_DIRTY, refresh=True)
        assert w._view_timeline is False
        assert w._filter == FILTER_DIRTY
    finally:
        w.close()
