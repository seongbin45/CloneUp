"""Main window — Publish tab skeleton (no full publish wiring yet)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, QObject, Slot
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QWidget,
)

from app.git.runner import GitError, require_git

_UI_PATH = Path(__file__).resolve().parents[2] / "ui" / "main_window.ui"


def load_main_window() -> QMainWindow:
    if not _UI_PATH.is_file():
        raise FileNotFoundError(f"UI file missing: {_UI_PATH}")

    ui_file = QFile(str(_UI_PATH))
    if not ui_file.open(QFile.OpenModeFlag.ReadOnly):
        raise RuntimeError(f"Cannot open UI: {_UI_PATH}")

    loader = QUiLoader()
    window = loader.load(ui_file)
    ui_file.close()

    if window is None:
        raise RuntimeError(f"QUiLoader failed: {_UI_PATH}")
    if not isinstance(window, QMainWindow):
        # Wrap if designer root is not QMainWindow
        wrap = QMainWindow()
        wrap.setCentralWidget(window)
        wrap.setWindowTitle("클론업 (CloneUp)")
        wrap.resize(720, 560)
        window = wrap

    PublishSkeletonController(window)
    return window


class PublishSkeletonController(QObject):
    """Attaches slots to widgets defined in main_window.ui."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.window = window

        self.labelStatusGit = window.findChild(QLabel, "labelStatusGit")
        self.labelStatusAuth = window.findChild(QLabel, "labelStatusAuth")
        self.editFolder = window.findChild(QLineEdit, "editFolder")
        self.btnBrowseFolder = window.findChild(QPushButton, "btnBrowseFolder")
        self.editRepoName = window.findChild(QLineEdit, "editRepoName")
        self.radioPublic = window.findChild(QRadioButton, "radioPublic")
        self.radioPrivate = window.findChild(QRadioButton, "radioPrivate")
        self.editCommitMessage = window.findChild(QLineEdit, "editCommitMessage")
        self.checkAllowSecrets = window.findChild(QCheckBox, "checkAllowSecrets")
        self.btnPublish = window.findChild(QPushButton, "btnPublish")
        self.textLog = window.findChild(QPlainTextEdit, "textLog")

        required = {
            "labelStatusGit": self.labelStatusGit,
            "editFolder": self.editFolder,
            "btnBrowseFolder": self.btnBrowseFolder,
            "btnPublish": self.btnPublish,
            "textLog": self.textLog,
        }
        missing = [k for k, v in required.items() if v is None]
        if missing:
            raise RuntimeError(f"UI widgets missing: {missing}")

        assert self.btnBrowseFolder is not None
        assert self.btnPublish is not None
        self.btnBrowseFolder.clicked.connect(self.on_browse_folder)
        self.btnPublish.clicked.connect(self.on_publish_stub)

        self._refresh_status_bar()
        self._log(
            "CloneUp UI 골격 로드됨. "
            "Publish 버튼은 stub — 실패 케이스: docs/FAILURE_CASES.md"
        )

    def _log(self, message: str) -> None:
        assert self.textLog is not None
        self.textLog.appendPlainText(message)

    def _refresh_status_bar(self) -> None:
        assert self.labelStatusGit is not None
        if self.labelStatusAuth is not None:
            self.labelStatusAuth.setText(
                "GitHub: (UI 연동 전 · keyring은 스파이크 사용)"
            )
        try:
            _exe, ver = require_git()
            self.labelStatusGit.setText(f"Git: {ver[0]}.{ver[1]}.{ver[2]}")
        except GitError as e:
            self.labelStatusGit.setText("Git: 없음")
            self._log(f"Git 확인 실패: {e}")

    @Slot()
    def on_browse_folder(self) -> None:
        assert self.editFolder is not None
        path = QFileDialog.getExistingDirectory(self.window, "올릴 폴더 선택")
        if path:
            self.editFolder.setText(path)
            self._log(f"폴더 선택: {path}")

    @Slot()
    def on_publish_stub(self) -> None:
        assert self.editFolder is not None
        assert self.editRepoName is not None
        assert self.editCommitMessage is not None
        assert self.checkAllowSecrets is not None

        folder = (self.editFolder.text() or "").strip()
        name = (self.editRepoName.text() or "").strip()
        msg = (self.editCommitMessage.text() or "").strip()
        allow = self.checkAllowSecrets.isChecked()
        private = bool(self.radioPrivate and self.radioPrivate.isChecked())

        self._log("--- Publish 클릭 (stub) ---")
        self._log(f"  folder={folder or '(비어 있음)'}")
        self._log(f"  name={name or '(비어 있음)'}")
        self._log(f"  visibility={'private' if private else 'public'}")
        self._log(f"  message={msg}")
        self._log(f"  allow_secrets={allow}")
        self._log(
            "다음: QThread + publish 연결, FAILURE_CASES "
            "S1(빈 폴더)/S3(비밀 파일)/G2(origin) 선검사."
        )
        QMessageBox.information(
            self.window,
            "CloneUp",
            "UI 골격 단계입니다.\n"
            "실제 업로드는 아직 연결되지 않았습니다.\n\n"
            "스파이크: spike_publish.py\n"
            "실패 표: docs/FAILURE_CASES.md",
        )
