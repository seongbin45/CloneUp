"""Compact post-action next-steps dialog."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import active_palette


class NextStepAction(Enum):
    CLOSE = "close"
    OPEN_BROWSER = "open_browser"
    GO_SYNC = "go_sync"
    COPY_URL = "copy_url"


@dataclass(frozen=True)
class SuccessNextSteps:
    action: NextStepAction
    open_browser: bool = False
    go_sync: bool = False
    url_copied: bool = False


class SuccessNextDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        headline: str,
        detail_lines: list[str],
        next_lines: list[str],
        url: str = "",
        show_open_browser: bool = True,
        show_go_sync: bool = True,
        open_browser_on_close: bool = False,
    ) -> None:
        super().__init__(parent)
        p = active_palette()
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMaximumWidth(460)
        self._url = (url or "").strip()
        self._open_browser_on_close = open_browser_on_close and bool(self._url)
        self._browser_opened = False
        self._result = SuccessNextSteps(action=NextStepAction.CLOSE)

        head = QLabel(headline)
        head.setWordWrap(True)
        head.setStyleSheet(
            f"color: {p.success_dot}; font-size: 14px; font-weight: 600;"
        )

        # One short detail block (url + one vis line)
        detail_text = "\n".join(line for line in detail_lines if line)
        detail = QLabel(detail_text)
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail.setStyleSheet(f"color: {p.text}; font-size: 12.5px;")

        # Max 2 next lines to keep height down
        short_next = [ln for ln in next_lines if ln][:2]
        next_body = QLabel("\n".join(f"· {line}" for line in short_next))
        next_body.setWordWrap(True)
        next_body.setStyleSheet(f"color: {p.text_muted}; font-size: 12px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)
        layout.addWidget(head)
        layout.addWidget(detail)
        if short_next:
            layout.addWidget(next_body)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        if show_open_browser and self._url:
            b_open = QPushButton("GitHub 열기")
            b_open.setDefault(True)
            b_open.clicked.connect(self._on_open)
            btn_row.addWidget(b_open)
            b_copy = QPushButton("주소 복사")
            b_copy.clicked.connect(self._on_copy)
            btn_row.addWidget(b_copy)
        if show_go_sync:
            b_sync = QPushButton("동기화 탭")
            if not (show_open_browser and self._url):
                b_sync.setDefault(True)
            b_sync.clicked.connect(self._on_go_sync)
            btn_row.addWidget(b_sync)
        btn_row.addStretch(1)
        b_close = QPushButton("닫기")
        b_close.clicked.connect(self._on_close)
        btn_row.addWidget(b_close)
        layout.addLayout(btn_row)

    def result_steps(self) -> SuccessNextSteps:
        return self._result

    def _open_url(self) -> bool:
        if not self._url:
            return False
        QDesktopServices.openUrl(QUrl(self._url))
        self._browser_opened = True
        return True

    def _on_open(self) -> None:
        self._open_url()
        self._result = SuccessNextSteps(
            action=NextStepAction.OPEN_BROWSER, open_browser=True
        )
        self.accept()

    def _on_copy(self) -> None:
        if not self._url:
            return
        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(self._url)
        QMessageBox.information(self, "복사됨", "주소를 복사했습니다.")
        self._result = SuccessNextSteps(
            action=NextStepAction.COPY_URL,
            url_copied=True,
            open_browser=self._browser_opened,
        )

    def _on_go_sync(self) -> None:
        self._result = SuccessNextSteps(
            action=NextStepAction.GO_SYNC,
            go_sync=True,
            open_browser=self._browser_opened,
        )
        self.accept()

    def _on_close(self) -> None:
        opened = False
        if self._open_browser_on_close and not self._browser_opened:
            opened = self._open_url()
        self._result = SuccessNextSteps(
            action=NextStepAction.CLOSE,
            open_browser=opened or self._browser_opened,
        )
        self.accept()


def show_publish_success(
    parent: QWidget | None,
    *,
    full_name: str,
    html_url: str,
    folder: str,
    private: bool,
) -> SuccessNextSteps:
    vis = "비공개 저장소" if private else "공개 저장소 (누구나 볼 수 있음)"
    dlg = SuccessNextDialog(
        parent,
        title="업로드 완료",
        headline=f"✓  {full_name or '저장소'}",
        detail_lines=[
            html_url or "",
            vis,
        ],
        next_lines=[
            "파일을 더 고치면 「동기화」탭에서 올리기",
            "다른 PC에서는 「받기」탭에 주소 입력",
        ],
        url=html_url,
        show_open_browser=bool(html_url),
        show_go_sync=bool(folder),
        open_browser_on_close=False,
    )
    dlg.exec()
    return dlg.result_steps()


def show_clone_success(
    parent: QWidget | None,
    *,
    owner_repo: str,
    path: str,
    html_url: str = "",
) -> SuccessNextSteps:
    dlg = SuccessNextDialog(
        parent,
        title="받기 완료",
        headline=f"✓  {owner_repo or '저장소'}",
        detail_lines=[f"저장 위치: {path}" if path else ""],
        next_lines=[
            "수정 후 「동기화」탭에서 올리기 가능",
        ],
        url=html_url,
        show_open_browser=bool(html_url),
        show_go_sync=bool(path),
        open_browser_on_close=False,
    )
    dlg.exec()
    return dlg.result_steps()
