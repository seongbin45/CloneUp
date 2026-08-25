"""Small floating guide after Google SSO is handed off to the OS browser.

No OAuth token exchange here — user finishes Google + PAT create in Chrome/Edge,
copies the key, and this dialog stores it via the same keyring path as the wizard.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_GUIDE_OPACITY = 0.88
_TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")

_CHECKLIST = (
    "Google 로그인",
    "GitHub으로 돌아오기",
    "Generate new token → 키 만들기",
    "키 복사",
)


def _looks_like_token(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 20 or " " in t or "\n" in t:
        return False
    return any(t.startswith(p) for p in _TOKEN_PREFIXES)


class ExternalBrowserPatGuide(QDialog):
    """Bottom-right translucent helper: checklist + paste + connect."""

    token_accepted = Signal(str)
    cancelled = Signal()

    def __init__(self, anchor: QWidget | None = None) -> None:
        super().__init__(None)  # independent of main window stacking
        self._anchor = anchor
        self._clip_seen = ""
        self._done = False
        self._check_labels: list[QLabel] = []

        self.setWindowTitle("CloneUp — 외부 브라우저 안내")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowOpacity(_GUIDE_OPACITY)
        self.setMinimumWidth(360)
        self.setMaximumWidth(420)

        title = QLabel("외부 브라우저에서 이어가세요")
        title.setStyleSheet(
            "font-size:15px;font-weight:600;color:#232019;border:none;"
        )
        title.setWordWrap(True)

        lead = QLabel(
            "Google 로그인은 앱 안에서 막힙니다. "
            "연 브라우저에서 로그인한 뒤 키를 만들어 복사하세요."
        )
        lead.setWordWrap(True)
        lead.setStyleSheet("font-size:12.5px;color:#4a453b;border:none;")

        # Expected steps (not live URL sniffing)
        steps_box = QWidget()
        steps_lay = QVBoxLayout(steps_box)
        steps_lay.setContentsMargins(0, 4, 0, 4)
        steps_lay.setSpacing(4)
        hint = QLabel("예상 순서 (주소는 읽지 않습니다)")
        hint.setStyleSheet("font-size:11.5px;color:#6d675c;border:none;")
        steps_lay.addWidget(hint)
        for i, label in enumerate(_CHECKLIST):
            row = QLabel(f"○  {label}")
            row.setStyleSheet("font-size:12.5px;color:#4a453b;border:none;")
            row.setWordWrap(True)
            self._check_labels.append(row)
            steps_lay.addWidget(row)

        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("키가 여기 채워지거나, 직접 붙여 넣으세요")
        self._edit.setClearButtonEnabled(True)
        self._edit.setMinimumHeight(36)
        self._edit.textChanged.connect(self._on_text)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size:11.5px;color:#1f6f5c;border:none;")

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self._on_cancel)
        self._btn_connect = QPushButton("연결")
        self._btn_connect.setEnabled(False)
        self._btn_connect.setDefault(True)
        self._btn_connect.clicked.connect(self._on_connect)

        nav = QHBoxLayout()
        nav.addWidget(btn_cancel)
        nav.addStretch(1)
        nav.addWidget(self._btn_connect)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)
        root.addWidget(title)
        root.addWidget(lead)
        root.addWidget(steps_box)
        root.addWidget(self._edit)
        root.addWidget(self._status)
        root.addLayout(nav)

        self._clip_timer = QTimer(self)
        self._clip_timer.setInterval(500)
        self._clip_timer.timeout.connect(self._poll_clipboard)
        self._clip_timer.start()

        self._place_bottom_right()

    def _place_bottom_right(self) -> None:
        margin = 24
        self.adjustSize()
        try:
            screen = None
            if self._anchor is not None:
                screen = self._anchor.screen()
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is None:
                return
            avail = screen.availableGeometry()
            g = self.frameGeometry()
            x = avail.right() - g.width() - margin + 1
            y = avail.bottom() - g.height() - margin + 1
            self.move(max(avail.left() + margin, x), max(avail.top() + margin, y))
        except Exception:
            pass

    def _on_text(self, text: str) -> None:
        has = bool((text or "").strip())
        self._btn_connect.setEnabled(has)
        if _looks_like_token(text or ""):
            self._mark_checklist_done(3)
            self._status.setText("키를 인식했습니다. 「연결」을 누르세요.")
        elif has:
            self._status.setText("")

    def _mark_checklist_done(self, up_to: int) -> None:
        for i, lab in enumerate(self._check_labels):
            prefix = "✓  " if i <= up_to else "○  "
            base = _CHECKLIST[i]
            lab.setText(prefix + base)
            if i <= up_to:
                lab.setStyleSheet(
                    "font-size:12.5px;color:#1f6f5c;font-weight:600;border:none;"
                )

    def _poll_clipboard(self) -> None:
        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        text = (clip.text() or "").strip()
        if not _looks_like_token(text) or text == self._clip_seen:
            return
        self._clip_seen = text
        self._edit.setText(text)
        self._mark_checklist_done(3)
        self.raise_()
        self.activateWindow()

    def _on_connect(self) -> None:
        raw = (self._edit.text() or "").strip()
        if not _looks_like_token(raw):
            self._status.setText("GitHub 키 형식이 아닙니다. 전체를 복사했는지 확인하세요.")
            self._status.setStyleSheet(
                "font-size:11.5px;color:#8a6d12;border:none;"
            )
            return
        self._clip_timer.stop()
        self._done = True
        self.token_accepted.emit(raw)
        self.accept()

    def _on_cancel(self) -> None:
        self._clip_timer.stop()
        self._done = True
        self.cancelled.emit()
        self.reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._clip_timer.stop()
        if not self._done:
            self._done = True
            self.cancelled.emit()
        super().closeEvent(event)

    def token(self) -> str:
        return (self._edit.text() or "").strip()
