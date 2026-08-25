"""WebView wizard vs ExternalBrowserPatGuide must not nest."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog

from app.ui.external_pat_guide import ExternalBrowserPatGuide
from app.ui.login_dialog import (
    ConnectGitHubWizard,
    _WEB_PAGE_CHOICE,
    _WEB_PAGE_START,
    _WEB_PAGE_WEB,
)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_wizard_external_path_closes_without_nested_guide() -> None:
    _app()
    wiz = ConnectGitHubWizard(None, reauth=False)
    if not wiz._use_web:
        wiz.close()
        return

    assert wiz._stack.count() == 3
    assert wiz._choice_index == _WEB_PAGE_CHOICE
    assert wiz._web_index == _WEB_PAGE_WEB

    # Choosing external must Accept with empty token + wants_external
    QTimer.singleShot(30, wiz._start_external_path)
    code = wiz.exec()
    assert int(code) == int(QDialog.DialogCode.Accepted)
    assert wiz.wants_external_browser() is True
    assert (wiz.token() or "") == ""
    # Nested guide must never have been created
    assert getattr(wiz, "_external_guide", None) is None


def test_google_oauth_handler_does_not_spawn_guide() -> None:
    _app()
    wiz = ConnectGitHubWizard(None, reauth=False)
    if not wiz._use_web:
        wiz.close()
        return
    wiz._on_google_oauth_external(
        "https://accounts.google.com/v3/signin/rejected"
    )
    assert getattr(wiz, "_external_guide", None) is None
    assert wiz._btn_switch_external is not None
    # Parent may be hidden in unit test; show() clears the explicit hide flag
    assert not wiz._btn_switch_external.isHidden()
    wiz.close()


def test_guide_connect_accepts_with_token_standalone() -> None:
    _app()
    guide = ExternalBrowserPatGuide(anchor=None, open_login_on_start=False)
    assert guide.windowModality() == Qt.WindowModality.ApplicationModal
    fake = "ghp_" + ("y" * 36)
    guide._edit.setText(fake)
    QTimer.singleShot(40, guide._on_connect)
    code = guide.exec()
    assert int(code) == int(QDialog.DialogCode.Accepted)
    assert guide.token() == fake


def test_web_stack_indices_ordered() -> None:
    assert _WEB_PAGE_START == 0
    assert _WEB_PAGE_CHOICE == 1
    assert _WEB_PAGE_WEB == 2
