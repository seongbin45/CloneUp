"""GitHub auth status control — status-row style (design Phase 2)."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QPushButton

from app.auth.token_store import (
    AUTH_KIND_DEVICE,
    AUTH_KIND_PAT,
    format_scopes_display,
    has_scope,
    is_scope_unknown,
    load_auth_kind,
    load_scope,
    load_token,
    token_age_info,
)
from app.ui.settings_store import load_last_github_login, save_last_github_login
from app.ui.theme import Palette, active_palette
from app.util.log_mask import mask_token


def _auth_kind_label(kind: str | None) -> str:
    if kind == AUTH_KIND_PAT:
        return "키(직접 연결)"
    if kind == AUTH_KIND_DEVICE:
        return "브라우저(이전/개발용 — 재연결 권장)"
    return "알 수 없음(이전 버전 — 키로 다시 연결 권장)"


class AuthState(Enum):
    LOGGED_OUT = "logged_out"
    LOGGED_IN = "logged_in"
    SCOPE_INSUFFICIENT = "scope_insufficient"
    TOKEN_AGING = "token_aging"  # still has token; soft/hard age warning


def _status_button_style(p: Palette, *, emphasis: str | None = None) -> str:
    """
    Status-row look: no heavy button chrome (matches desin mock).

    Uses active palette at call time so OS light/dark is respected
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
      logged out → ● GitHub: 연결 필요
      logged in  → ● GitHub: 연결됨 (user)
      aging      → ● GitHub: 키 확인 권장 (user)
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
            self.button.setText("●  GitHub: 연결 필요")
            self.button.setStyleSheet(
                _status_button_style(p, emphasis=p.warn_dot)
            )
            self.button.setToolTip(
                "클릭하여 GitHub와 연결\n"
                "GitHub에서 만든 키를 붙여 넣습니다.\n"
                "키에는 만료일이 있을 수 있습니다 (90일 등).\n"
                "연결 정보는 이 컴퓨터 안에만 저장됩니다."
            )
            return

        kind = load_auth_kind()
        kind_txt = _auth_kind_label(kind)
        store_note = "저장: 이 컴퓨터 안에만 (다른 사람에게 공유되지 않음)"
        age = token_age_info()

        who = self._login or "계정"
        # Fine-grained / unknown scopes: connected, but do not claim "repo" (M3).
        if is_scope_unknown(scope):
            if age.level in ("stale", "strong"):
                self._state = AuthState.TOKEN_AGING
                label = age.status_line or "키 확인 권장"
                self.button.setText(f"●  GitHub: {label} ({who})")
            else:
                self._state = AuthState.LOGGED_IN
                self.button.setText(f"●  GitHub: 연결됨 ({who})")
            self.button.setStyleSheet(
                _status_button_style(
                    p,
                    emphasis=p.warn_dot
                    if age.level in ("stale", "strong")
                    else p.success_dot,
                )
            )
            self.button.setToolTip(
                f"계정={who}\n"
                f"방식={kind_txt}\n"
                "권한=GitHub이 목록을 안 알려 줌 (세분 키 가능)\n"
                "올리기/받기가 실패하면 키 권한(repo 또는 저장소 접근)을 확인하세요.\n"
                f"키={mask_token(token)}\n"
                f"{store_note}\n"
                f"{age.tooltip_extra}\n"
                "클릭하면 새 키로 다시 연결합니다."
            )
            return

        if has_scope("repo"):
            if age.level in ("stale", "strong"):
                self._state = AuthState.TOKEN_AGING
                label = age.status_line or "키 확인 권장"
                self.button.setText(f"●  GitHub: {label} ({who})")
                self.button.setStyleSheet(
                    _status_button_style(p, emphasis=p.warn_dot)
                )
            else:
                self._state = AuthState.LOGGED_IN
                self.button.setText(f"●  GitHub: 연결됨 ({who})")
                self.button.setStyleSheet(
                    _status_button_style(p, emphasis=p.success_dot)
                )
            scope_disp = format_scopes_display(scope) or (scope or "")
            self.button.setToolTip(
                f"계정={who}\n"
                f"방식={kind_txt}\n"
                f"권한={scope_disp}\n"
                f"키={mask_token(token)}\n"
                f"{store_note}\n"
                f"{age.tooltip_extra}\n"
                "클릭하면 새 키로 다시 연결합니다."
            )
            return

        self._state = AuthState.SCOPE_INSUFFICIENT
        self.button.setText(f"●  GitHub: 권한 부족 ({who})")
        self.button.setStyleSheet(
            _status_button_style(p, emphasis=p.warn_dot)
        )
        self.button.setToolTip(
            f"저장소 권한이 있는 키가 필요합니다.\n"
            f"방식={kind_txt}\n"
            f"{store_note}\n"
            f"{age.tooltip_extra}\n"
            "클릭하여 키를 다시 붙여 넣으세요."
        )

    def _on_clicked(self) -> None:
        self.login_requested.emit()
