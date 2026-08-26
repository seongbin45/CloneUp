"""Regression: ApplicationModal QDialog must not hide() during exec().

On Windows Qt, hide() ends the modal loop as Rejected — so after Google
handoff the main window never ran PatLoginWorker (no log / no success UI).
Yield with showMinimized() instead.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QVBoxLayout


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_hide_ends_application_modal_exec_as_rejected() -> None:
    _app()
    dlg = QDialog()
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    QTimer.singleShot(20, dlg.hide)
    assert int(dlg.exec()) == int(QDialog.DialogCode.Rejected)


def test_set_window_flag_while_visible_hides_and_rejects_modal() -> None:
    """Regression: toggling Maximize mid-exec hid the wizard → 「연결 안내 취소」."""
    _app()
    dlg = QDialog()
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setWindowFlags(
        Qt.WindowType.Dialog
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
    )
    dlg.show()

    def _toggle_max() -> None:
        # Same foot-gun ConnectGitHubWizard used to hit.
        dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        # Bug pattern: check isVisible() AFTER flag change → often False → no show()

    QTimer.singleShot(20, _toggle_max)
    # Give the hide a moment; if still running, accept to avoid hang
    QTimer.singleShot(200, dlg.reject)
    code = int(dlg.exec())
    assert code == int(QDialog.DialogCode.Rejected)


def test_connect_wizard_keeps_maximize_hint_without_toggling() -> None:
    """Wizard must ship with Maximize hint so Path A never setWindowFlag mid-exec."""
    from app.ui.login_dialog import ConnectGitHubWizard

    _app()
    wiz = ConnectGitHubWizard(None, reauth=False)
    assert bool(
        wiz.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint
    ), "Maximize hint must be set at construction (no mid-exec toggle)"


def test_show_minimized_keeps_exec_until_accept() -> None:
    _app()

    class Guide(QDialog):
        token_accepted = Signal(str)

        def __init__(self) -> None:
            super().__init__(None)
            self.setWindowModality(Qt.WindowModality.NonModal)
            btn = QPushButton("connect")
            btn.clicked.connect(self._go)
            QVBoxLayout(self).addWidget(btn)

        def _go(self) -> None:
            self.token_accepted.emit("ghp_" + ("x" * 36))
            self.accept()

    class Wiz(QDialog):
        def __init__(self) -> None:
            super().__init__(None)
            self.token = ""
            self.setWindowModality(Qt.WindowModality.ApplicationModal)
            btn = QPushButton("hand")
            btn.clicked.connect(self._hand)
            QVBoxLayout(self).addWidget(btn)

        def _hand(self) -> None:
            self.showMinimized()
            g = Guide()
            self._g = g
            g.token_accepted.connect(self._on_tok)
            g.show()
            QTimer.singleShot(30, lambda: g.findChild(QPushButton).click())

        def _on_tok(self, t: str) -> None:
            self.token = t
            if self.isMinimized():
                self.showNormal()
            self.done(int(QDialog.DialogCode.Accepted))

    w = Wiz()
    QTimer.singleShot(20, lambda: w.findChild(QPushButton).click())
    code = w.exec()
    assert int(code) == int(QDialog.DialogCode.Accepted)
    assert w.token.startswith("ghp_")
    assert len(w.token) >= 40
