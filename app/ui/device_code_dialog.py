"""Modal overlay: show Device Flow user_code until login finishes."""

from __future__ import annotations

import time
import webbrowser

from PySide6.QtCore import QEvent, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.auth.device_flow import format_remaining, verification_open_url
from app.ui.theme import (
    BG_HINT,
    BG_INPUT,
    BG_MUTED,
    BG_WINDOW,
    BORDER,
    BORDER_INPUT,
    BORDER_SOFT,
    DANGER,
    DANGER_HOVER,
    DANGER_SOFT_BG,
    HOVER_MUTED,
    PRIMARY,
    PRIMARY_HOVER,
    TEXT,
    TEXT_DISABLED,
    TEXT_MUTED,
    TEXT_ON_PRIMARY,
    TEXT_SECONDARY,
    WARN_DOT,
    WARN_TEXT,
)

# Dim scrim (paintEvent — more reliable than QSS rgba on Windows maximize)
_DIM = QColor(15, 18, 22, 170)


class DeviceCodeOverlay(QWidget):
    """
    Full-window dim overlay + centered code card.

    Parented to QMainWindow (not only centralWidget) so maximize covers
    the entire client area. Geometry is re-synced on every resize/state change.
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
        # Always attach to top-level main window so we cover status + tabs + log
        main = parent
        while main is not None and not isinstance(main, QMainWindow):
            main = main.parentWidget()
        if main is None:
            main = parent

        super().__init__(main)
        self._main = main
        self._user_code = str(user_code)
        self._deadline = time.monotonic() + max(1, int(expires_in))
        self._open_url = verification_open_url(verification_uri, user_code)

        self.setObjectName("deviceCodeOverlay")
        # Paint dim ourselves — more reliable than stylesheet on Windows maximize
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAutoFillBackground(False)

        # --- card (fixed width, height by content) ---
        card = QFrame()
        card.setObjectName("deviceCodeCard")
        card.setFixedWidth(440)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        # Phase 5 — warm paper card, same tokens as main window (desin palette)
        card.setStyleSheet(
            f"""
            #deviceCodeCard {{
                background: {BG_WINDOW};
                border-radius: 10px;
                border: 1px solid {BORDER};
            }}
            QLabel#title {{
                font-size: 16px;
                font-weight: 600;
                color: {TEXT};
            }}
            QLabel#hint {{
                color: {TEXT_MUTED};
                font-size: 13px;
            }}
            QLabel#code {{
                font-size: 28px;
                font-weight: 700;
                letter-spacing: 3px;
                color: {PRIMARY};
                padding: 18px 16px;
                min-height: 56px;
                background: {BG_HINT};
                border-radius: 8px;
                border: 1px dashed {WARN_DOT};
            }}
            QLabel#timer {{
                color: {WARN_TEXT};
                font-size: 12px;
            }}
            QPushButton {{
                padding: 8px 14px;
                border-radius: 6px;
                font-weight: 600;
                color: {TEXT_SECONDARY};
                background: {BG_MUTED};
                border: 1px solid {BORDER_INPUT};
                min-height: 32px;
            }}
            QPushButton#btnCopy {{
                background: {PRIMARY};
                color: {TEXT_ON_PRIMARY};
                border: 1px solid {PRIMARY};
            }}
            QPushButton#btnCopy:hover {{
                background: {PRIMARY_HOVER};
                color: {TEXT_ON_PRIMARY};
                border-color: {PRIMARY_HOVER};
            }}
            QPushButton#btnOpen {{
                background: {BG_INPUT};
                color: {TEXT};
                border: 1px solid {BORDER_INPUT};
            }}
            QPushButton#btnOpen:hover {{
                background: {HOVER_MUTED};
                color: {TEXT};
            }}
            QPushButton#btnCancel {{
                background: {BG_INPUT};
                border: 1px solid {BORDER_SOFT};
                color: {DANGER};
                font-weight: 500;
            }}
            QPushButton#btnCancel:hover {{
                background: {DANGER_SOFT_BG};
                color: {DANGER_HOVER};
            }}
            QPushButton:disabled {{
                color: {TEXT_DISABLED};
                background: {BG_MUTED};
                border-color: {BORDER_SOFT};
            }}
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
        self._code_label.setMinimumHeight(64)
        self._code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(24)
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
        btn_cancel.clicked.connect(self._on_cancel_clicked)

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

        # Center card with stretches — independent of absolute host size
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addStretch(1)
        mid = QHBoxLayout()
        mid.addStretch(1)
        mid.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        mid.addStretch(1)
        root.addLayout(mid)
        root.addStretch(1)

        # Track main window size (maximize / restore / drag-resize)
        self._main.installEventFilter(self)
        self.sync_geometry()

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_timer)
        self._tick.start(500)
        self._update_timer()

        QTimer.singleShot(0, self._copy_code)
        QTimer.singleShot(50, self._open_browser)

    # ----- geometry -----
    def _client_rect(self) -> QRect:
        """Full client area of the main window (everything inside the frame)."""
        return self._main.rect()

    def sync_geometry(self) -> None:
        r = self._client_rect()
        # Geometry is relative to parent (main window)
        self.setGeometry(0, 0, max(1, r.width()), max(1, r.height()))
        self.raise_()
        self.update()

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._main:
            et = event.type()
            if et in (
                QEvent.Type.Resize,
                QEvent.Type.Show,
                QEvent.Type.LayoutRequest,
                QEvent.Type.WindowStateChange,
            ):
                # Defer one tick so maximize layout settles
                QTimer.singleShot(0, self.sync_geometry)
        return False

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.sync_geometry()
        self.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.raise_()

    def paintEvent(self, event) -> None:  # noqa: N802
        # Full-rect dim — avoids QSS background clipping on maximize
        p = QPainter(self)
        p.fillRect(self.rect(), _DIM)
        p.end()

    # ----- actions -----
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

    def _on_cancel_clicked(self) -> None:
        self._status.setText("취소 중…")
        for child in self.findChildren(QPushButton):
            if child.objectName() == "btnCancel":
                child.setEnabled(False)
        self.cancelled.emit()

    def set_waiting_message(self, text: str) -> None:
        self._status.setText(text)
