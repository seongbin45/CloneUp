"""WebView wizard vs ExternalBrowserPatGuide must not nest."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog

from app.ui.external_pat_guide import ExternalBrowserPatGuide
from app.ui.login_dialog import (
    ConnectGitHubWizard,
    _WEB_PAGE_CHOICE,
    _WEB_PAGE_INTRO,
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

    # WebView page is lazy — intro + choice until Path A
    assert wiz._stack.count() == 2
    assert wiz._intro_index == _WEB_PAGE_INTRO == 0
    assert wiz._choice_index == _WEB_PAGE_CHOICE == 1
    assert wiz._web_index == -1
    # First connect starts on intro (시안 step0)
    assert wiz._stack.currentIndex() == _WEB_PAGE_INTRO

    # Choosing external must Accept with empty token + wants_external
    QTimer.singleShot(30, wiz._start_external_path)
    code = wiz.exec()
    assert int(code) == int(QDialog.DialogCode.Accepted)
    assert wiz.wants_external_browser() is True
    assert (wiz.token() or "") == ""
    # Nested guide must never have been created
    assert getattr(wiz, "_external_guide", None) is None


def test_google_oauth_auto_switches_to_external_path() -> None:
    _app()
    wiz = ConnectGitHubWizard(None, reauth=False)
    if not wiz._use_web:
        wiz.close()
        return
    wiz._ensure_web_page()
    # Google in WebView → same as clicking 「브라우저에서 로그인으로 바꾸기」
    QTimer.singleShot(
        20,
        lambda: wiz._on_google_oauth_external(
            "https://accounts.google.com/v3/signin/identifier"
        ),
    )
    code = wiz.exec()
    assert int(code) == int(QDialog.DialogCode.Accepted)
    assert wiz.wants_external_browser() is True
    assert getattr(wiz, "_external_guide", None) is None


def test_guide_connect_accepts_with_token_standalone() -> None:
    _app()
    guide = ExternalBrowserPatGuide(anchor=None, open_login_on_start=False)
    # Path B stays NonModal so the OS browser keeps keyboard focus
    # (email codes / passkeys). ApplicationModal caused focus fights.
    assert guide.windowModality() == Qt.WindowModality.NonModal
    # Stop background UIA/OCR timers — they hang/crash offscreen CI runners.
    guide._stop_timers()
    fake = "ghp_" + ("y" * 36)
    accepted: list[str] = []
    guide.token_accepted.connect(accepted.append)
    # Drive the product ingest path without exec() (Tool + NonModal +
    # offscreen has crashed nested event loops on CI/Windows).
    guide._ingest_token(fake, source="test")
    assert guide.token() == fake
    guide._finish_accept()
    assert guide.result() == int(QDialog.DialogCode.Accepted)
    assert accepted == [fake]
    assert guide.token() == fake
    guide.close()


def test_web_stack_indices_ordered() -> None:
    assert _WEB_PAGE_INTRO == 0
    assert _WEB_PAGE_CHOICE == 1
    assert _WEB_PAGE_WEB == 2


def test_reauth_also_starts_on_intro() -> None:
    """시안 step0 — 재연결이어도 「GitHub 계정을 연결할게요」부터."""
    _app()
    wiz = ConnectGitHubWizard(None, reauth=True)
    if not wiz._use_web:
        wiz.close()
        return
    assert wiz._stack.count() == 2
    assert wiz._stack.currentIndex() == _WEB_PAGE_INTRO
    wiz.close()
