"""GitHub auth status control — shows 미로그인/로그인됨 and triggers login on click."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QPushButton

from app.auth.token_store import has_scope, load_scope, load_token
from app.ui.settings_store import load_last_github_login, save_last_github_login
from app.ui.theme import (
    BORDER_INPUT,
    DANGER,
    PRIMARY,
    SUCCESS_DOT,
    TEXT,
    TEXT_ON_PRIMARY,
    TEXT_SECONDARY,
    WARN_DOT,
)
from app.util.log_mask import mask_token


class AuthState(Enum):
    LOGGED_OUT = "logged_out"
    LOGGED_IN = "logged_in"
    SCOPE_INSUFFICIENT = "scope_insufficient"


def _style(bg: str, fg: str, border: str) -> str:
    return f"""
    QPushButton {{
        text-align: left;
        padding: 6px 12px;
        border: 1px solid {border};
        border-radius: 6px;
        background: {bg};
        color: {fg};
        font-weight: 500;
        font-size: 12.5px;
    }}
    QPushButton:hover {{
        background: {bg};
        color: {fg};
        border-color: {PRIMARY};
    }}
    QPushButton:disabled {{
        color: #b3ac9e;
        border-color: #ddd8d0;
        background: #f2efe9;
    }}
    """


class AuthStatusButton(QObject):
    """
    Owns a QPushButton in the status bar.

    - 미로그인 → 클릭 시 로그인 요청
    - 로그인됨 → 상태 표시, 클릭 시 재로그인 요청
    """

    login_requested = Signal()

    def __init__(self, button: QPushButton, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.button = button
        self._state = AuthState.LOGGED_OUT
        self._login: str | None = load_last_github_login()
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
            # Warm paper + amber accent (design warn)
            self.button.setStyleSheet(_style("#fff8e8", TEXT_SECONDARY, WARN_DOT))
            self.button.setToolTip("Device Flow로 GitHub에 로그인합니다.")
            return

        if has_scope("repo"):
            self._state = AuthState.LOGGED_IN
            who = self._login or "로그인됨"
            self.button.setText(f"GitHub: {who}  ·  로그인됨  ·  클릭하여 재로그인")
            self.button.setStyleSheet(_style("#eef6f2", TEXT_SECONDARY, SUCCESS_DOT))
            self.button.setToolTip(
                f"scope={scope!r}\n토큰={mask_token(token)}\n클릭하면 다시 로그인합니다."
            )
            return

        self._state = AuthState.SCOPE_INSUFFICIENT
        who = self._login or "계정"
        self.button.setText(
            f"GitHub: {who}  ·  권한 부족 ({scope!r})  ·  클릭하여 재로그인"
        )
        self.button.setStyleSheet(_style("#fff8e8", TEXT_SECONDARY, WARN_DOT))
        self.button.setToolTip(
            "비공개 저장소 등에 repo 권한이 필요합니다. 클릭하여 다시 승인하세요."
        )

    def _on_clicked(self) -> None:
        self.login_requested.emit()
