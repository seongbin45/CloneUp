"""GitHub auth status control — shows 미로그인/로그인됨 and triggers login on click."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QPushButton

from app.auth.token_store import has_scope, load_scope, load_token
from app.ui.settings_store import load_last_github_login, save_last_github_login
from app.util.log_mask import mask_token


class AuthState(Enum):
    LOGGED_OUT = "logged_out"
    LOGGED_IN = "logged_in"
    SCOPE_INSUFFICIENT = "scope_insufficient"


# Distinct but calm styles for status-as-button
_STYLE_OUT = """
QPushButton {
    text-align: left;
    padding: 6px 12px;
    border: 1px solid #c45c26;
    border-radius: 6px;
    background: #fff4ee;
    color: #8a3b12;
}
QPushButton:hover { background: #ffe8db; }
QPushButton:disabled { color: #999; border-color: #ccc; background: #f5f5f5; }
"""

_STYLE_IN = """
QPushButton {
    text-align: left;
    padding: 6px 12px;
    border: 1px solid #2f6f3e;
    border-radius: 6px;
    background: #eef8f0;
    color: #1e4d2b;
}
QPushButton:hover { background: #e2f3e6; }
QPushButton:disabled { color: #999; border-color: #ccc; background: #f5f5f5; }
"""

_STYLE_WARN = """
QPushButton {
    text-align: left;
    padding: 6px 12px;
    border: 1px solid #a67c00;
    border-radius: 6px;
    background: #fff8e6;
    color: #6b5200;
}
QPushButton:hover { background: #fff1cc; }
QPushButton:disabled { color: #999; border-color: #ccc; background: #f5f5f5; }
"""


class AuthStatusButton(QObject):
    """
    Owns a QPushButton in the status bar.

    - 미로그인 → 클릭 시 로그인 요청
    - 로그인됨 → 상태 표시, 클릭 시 재로그인 요청
    """

    login_requested = Signal()  # user clicked (login or re-login)

    def __init__(self, button: QPushButton, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.button = button
        self._state = AuthState.LOGGED_OUT
        self._login: str | None = load_last_github_login()
        self.button.setCursor(self.button.cursor())
        self.button.setToolTip("")
        self.button.clicked.connect(self._on_clicked)
        self.refresh()

    @property
    def state(self) -> AuthState:
        return self._state

    def set_enabled(self, enabled: bool) -> None:
        self.button.setEnabled(enabled)

    def set_login_name(self, login: str | None) -> None:
        self._login = (login or "").strip() or None
        if self._login:
            save_last_github_login(self._login)
        self.refresh()

    def refresh(self) -> None:
        token = load_token()
        scope = load_scope()
        if not token:
            self._state = AuthState.LOGGED_OUT
            self.button.setText("GitHub: 미로그인  ·  클릭하여 로그인")
            self.button.setStyleSheet(_STYLE_OUT)
            self.button.setToolTip("Device Flow로 GitHub에 로그인합니다.")
            return

        if has_scope("repo"):
            self._state = AuthState.LOGGED_IN
            who = self._login or "로그인됨"
            self.button.setText(f"GitHub: {who}  ·  로그인됨  ·  클릭하여 재로그인")
            self.button.setStyleSheet(_STYLE_IN)
            self.button.setToolTip(
                f"scope={scope!r}\n토큰={mask_token(token)}\n클릭하면 다시 로그인합니다."
            )
            return

        self._state = AuthState.SCOPE_INSUFFICIENT
        who = self._login or "계정"
        self.button.setText(
            f"GitHub: {who}  ·  권한 부족 ({scope!r})  ·  클릭하여 재로그인"
        )
        self.button.setStyleSheet(_STYLE_WARN)
        self.button.setToolTip(
            "비공개 저장소 등에 repo 권한이 필요합니다. 클릭하여 다시 승인하세요."
        )

    def _on_clicked(self) -> None:
        self.login_requested.emit()
