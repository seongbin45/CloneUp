"""Modal overlay: show Device Flow user_code until login finishes."""

from __future__ import annotations

import time
import webbrowser

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.auth.device_flow import format_remaining, verification_open_url


def _host_widget(parent: QWidget) -> QWidget:
    if isinstance(parent, QMainWindow) and parent.centralWidget() is not None:
        return parent.centralWidget()
    return parent


class DeviceCodeOverlay(QWidget):
    """
    Full-area dim overlay + centered card with copyable user code.

    Non-blocking (show()) so the login QThread can keep polling.
    """

    cancelled = Signal()

    def __init__(
        self,
        parent: QWidget,
        *,
        user_code: str,
        verification_uri: str,
        expires_in: int,
    ) -> None:
        host = _host_widget(parent)
        super().__init__(host)
        self._user_code = str(user_code)
        self._verification_uri = str(verification_uri)
        self._deadline = time.monotonic() + max(1, int(expires_in))
        self._open_url = verification_open_url(verification_uri, user_code)

        self.setObjectName("deviceCodeOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "#deviceCodeOverlay { background-color: rgba(15, 18, 22, 160); }"
        )
        self.setGeometry(host.rect())
        self.raise_()

        card = QFrame(self)
        card.setObjectName("deviceCodeCard")
        card.setStyleSheet(
            """
            #deviceCodeCard {
                background: #ffffff;
                border-radius: 14px;
                border: 1px solid #d0d7de;
            }
            QLabel#title { font-size: 16px; font-weight: 600; color: #1f2328; }
            QLabel#hint { color: #656d76; font-size: 13px; }
            QLabel#code {
                font-size: 32px;
                font-weight: 700;
                letter-spacing: 3px;
                color: #0969da;
                padding: 12px;
                background: #f6f8fa;
                border-radius: 8px;
                border: 1px dashed #d0d7de;
            }
            QLabel#timer { color: #9a6700; font-size: 12px; }
            /* Explicit colors — Windows dark-mode inheritance can force light text. */
            QPushButton {
                padding: 8px 14px;
                border-radius: 6px;
                font-weight: 600;
                color: #1f2328;
                background: #f6f8fa;
                border: 1px solid #d0d7de;
            }
            QPushButton#btnCopy {
                background: #0969da;
                color: #ffffff;
                border: 1px solid #0969da;
            }
            QPushButton#btnCopy:hover {
                background: #0860ca;
                color: #ffffff;
                border-color: #0860ca;
            }
            QPushButton#btnOpen {
                background: #ffffff;
                color: #1f2328;
                border: 1px solid #d0d7de;
            }
            QPushButton#btnOpen:hover {
                background: #f3f4f6;
                color: #1f2328;
            }
            QPushButton#btnCancel {
                background: #ffffff;
                border: 1px solid #d0d7de;
                color: #cf222e;
            }
            QPushButton#btnCancel:hover {
                background: #fff5f5;
                color: #a40e26;
            }
            """
        )

        title = QLabel("GitHub 장치 코드", card)
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel(
            "브라우저에서 계정 선택 후, 아래 코드를 입력하세요.\n"
            "이 창은 로그인될 때까지 유지됩니다.",
            card,
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._code_label = QLabel(self._user_code, card)
        self._code_label.setObjectName("code")
        self._code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(26)
        mono.setBold(True)
        self._code_label.setFont(mono)

        self._timer_label = QLabel("", card)
        self._timer_label.setObjectName("timer")
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._status = QLabel("", card)
        self._status.setObjectName("hint")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)

        btn_copy = QPushButton("코드 복사", card)
        btn_copy.setObjectName("btnCopy")
        btn_copy.clicked.connect(self._copy_code)

        btn_open = QPushButton("브라우저 열기", card)
        btn_open.setObjectName("btnOpen")
        btn_open.clicked.connect(self._open_browser)

        btn_cancel = QPushButton("로그인 취소", card)
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.clicked.connect(self.cancelled.emit)

        row = QHBoxLayout()
        row.addWidget(btn_copy)
        row.addWidget(btn_open)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addWidget(self._code_label)
        lay.addWidget(self._timer_label)
        lay.addWidget(self._status)
        lay.addLayout(row)
        lay.addWidget(btn_cancel)

        self._card = card
        self._layout_card()

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_timer)
        self._tick.start(500)
        self._update_timer()

        # After shown: copy + open browser on UI thread (avoid worker COM errors)
        QTimer.singleShot(0, self._copy_code)
        QTimer.singleShot(50, self._open_browser)

    def _layout_card(self) -> None:
        w, h = 440, 360
        x = max(0, (self.width() - w) // 2)
        y = max(0, (self.height() - h) // 2)
        self._card.setGeometry(x, y, w, h)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(p.rect())
        self._layout_card()

    def _update_timer(self) -> None:
        left = self._deadline - time.monotonic()
        if left <= 0:
            self._timer_label.setText(
                "코드가 만료되었을 수 있습니다. 다시 로그인해 주세요."
            )
            return
        self._timer_label.setText(f"남은 시간: 약 {format_remaining(left)}")

    def _copy_code(self) -> None:
        try:
            QGuiApplication.clipboard().setText(self._user_code)
            self._status.setText("클립보드에 복사됨 — 입력란에서 Ctrl+V")
        except Exception as e:
            self._status.setText(f"복사 실패: {e} (코드를 드래그해 복사하세요)")

    def _open_browser(self) -> None:
        try:
            webbrowser.open(self._open_url)
            self._status.setText(
                "브라우저를 열었습니다. 계정 선택 후 코드를 붙여넣으세요."
            )
        except Exception as e:
            self._status.setText(f"브라우저 열기 실패: {e}")
