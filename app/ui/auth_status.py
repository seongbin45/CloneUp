"""GitHub auth status control — status-row style (design Phase 2)."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QPushButton

from app.auth.token_store import has_scope, load_scope, load_token
from app.ui.settings_store import load_last_github_login, save_last_github_login
from app.ui.theme import Palette, active_palette
from app.util.log_mask import mask_token


class AuthState(Enum):
    LOGGED_OUT = "logged_out"
    LOGGED_IN = "logged_in"
    SCOPE_INSUFFICIENT = "scope_insufficient"


def _status_button_style(p: Palette, *, emphasis: str | None = None) -> str:
    """
    Status-row look: no heavy button chrome (matches desin mock).

    Uses active palette at call time so OS dark/light is respected
    (import-time PRIMARY/TEXT_SECONDARY would stay stuck on light).
    """
    body = emphasis or p.text_secondary
    return f"""
    QPushButton#btnAuthStatus {{
        background: transparent;
        border: none;
        color: {body};
        font-size: 12.5px;
        font-weight: 500;
        padding: 2px 4px;
        text-align: left;
        min-height: 0;
    }}
    QPushButton#btnAuthStatus:hover {{
        color: {p.primary};
        background: transparent;
        border: none;
    }}
    QPushButton#btnAuthStatus:disabled {{
        color: {p.text_disabled};
        background: transparent;
        border: none;
    }}
    """


class AuthStatusButton(QObject):
    """
    Status-bar GitHub control (click to login / re-login).

    Design copy:
      logged out → ● GitHub: 로그인 필요
      logged in  → ● GitHub: 로그인됨 (user)
    """

    login_requested = Signal()

    def __init__(self, button: QPushButton, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.button = button
        self.button.setObjectName("btnAuthStatus")
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
        p = active_palette()
        token = load_token()
        scope = load_scope()
        if not token:
            self._state = AuthState.LOGGED_OUT
            # Amber status (design authDot when logged out)
            self.button.setText("●  GitHub: 로그인 필요")
            self.button.setStyleSheet(
                _status_button_style(p, emphasis=p.warn_dot)
            )
            self.button.setToolTip("클릭하여 GitHub 로그인 (Device Flow)")
            return

        if has_scope("repo"):
            self._state = AuthState.LOGGED_IN
            who = self._login or "계정"
            self.button.setText(f"●  GitHub: 로그인됨 ({who})")
            self.button.setStyleSheet(
                _status_button_style(p, emphasis=p.success_dot)
            )
            self.button.setToolTip(
                f"scope={scope!r}\n토큰={mask_token(token)}\n클릭하면 재로그인합니다."
            )
            return

        self._state = AuthState.SCOPE_INSUFFICIENT
        who = self._login or "계정"
        self.button.setText(f"●  GitHub: 권한 부족 ({who})")
        self.button.setStyleSheet(
            _status_button_style(p, emphasis=p.warn_dot)
        )
        self.button.setToolTip(
            f"현재 scope={scope!r}. repo 권한이 필요합니다. 클릭하여 재로그인."
        )

    def _on_clicked(self) -> None:
        self.login_requested.emit()
