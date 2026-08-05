"""Main window — Publish tab wired to background publish worker."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, QObject, QUrl, Slot
from PySide6.QtGui import QDesktopServices
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
)

from app.auth.token_store import has_scope, load_scope, load_token
from app.git.runner import GitError, require_git
from app.git.safety import run_safety_checks
from app.ui.publish_worker import PublishWorker
from app.util.log_mask import mask_token

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
        wrap = QMainWindow()
        wrap.setCentralWidget(window)
        wrap.setWindowTitle("클론업 (CloneUp)")
        wrap.resize(720, 560)
        window = wrap

    PublishController(window)
    return window


class PublishController(QObject):
    """Wires main_window.ui and runs publish off the UI thread."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.window = window
        self._worker: PublishWorker | None = None

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
            "editRepoName": self.editRepoName,
        }
        missing = [k for k, v in required.items() if v is None]
        if missing:
            raise RuntimeError(f"UI widgets missing: {missing}")

        assert self.btnBrowseFolder is not None
        assert self.btnPublish is not None
        self.btnBrowseFolder.clicked.connect(self.on_browse_folder)
        self.btnPublish.clicked.connect(self.on_publish)
        if self.editFolder is not None:
            self.editFolder.editingFinished.connect(self._maybe_fill_repo_name)

        self._refresh_status_bar()
        self._log(
            "CloneUp 준비됨. 폴더를 고르고 「GitHub에 만들고 올리기」를 누르세요."
        )
        self._log("실패 케이스 표: docs/FAILURE_CASES.md")

    def _log(self, message: str) -> None:
        assert self.textLog is not None
        self.textLog.appendPlainText(message)

    def _set_busy(self, busy: bool) -> None:
        assert self.btnPublish is not None
        assert self.btnBrowseFolder is not None
        self.btnPublish.setEnabled(not busy)
        self.btnBrowseFolder.setEnabled(not busy)
        for w in (
            self.editFolder,
            self.editRepoName,
            self.editCommitMessage,
            self.radioPublic,
            self.radioPrivate,
            self.checkAllowSecrets,
        ):
            if w is not None:
                w.setEnabled(not busy)
        self.btnPublish.setText(
            "올리는 중…" if busy else "GitHub에 만들고 올리기"
        )

    def _refresh_status_bar(self) -> None:
        assert self.labelStatusGit is not None
        try:
            _exe, ver = require_git()
            self.labelStatusGit.setText(f"Git: {ver[0]}.{ver[1]}.{ver[2]}")
        except GitError as e:
            self.labelStatusGit.setText("Git: 없음")
            self._log(f"Git 확인 실패: {e}")

        if self.labelStatusAuth is not None:
            token = load_token()
            if not token:
                self.labelStatusAuth.setText("GitHub: 미로그인")
            elif has_scope("repo"):
                self.labelStatusAuth.setText(
                    f"GitHub: 로그인됨 (scope={load_scope()!r})"
                )
            else:
                self.labelStatusAuth.setText(
                    f"GitHub: 권한 부족 (scope={load_scope()!r} → 재로그인 필요)"
                )
            if token:
                self._log(f"keyring 토큰: {mask_token(token)}")

    @Slot()
    def _maybe_fill_repo_name(self) -> None:
        assert self.editFolder is not None
        assert self.editRepoName is not None
        if (self.editRepoName.text() or "").strip():
            return
        folder = (self.editFolder.text() or "").strip()
        if not folder:
            return
        self.editRepoName.setText(Path(folder).name)

    @Slot()
    def on_browse_folder(self) -> None:
        assert self.editFolder is not None
        path = QFileDialog.getExistingDirectory(self.window, "올릴 폴더 선택")
        if path:
            self.editFolder.setText(path)
            self._log(f"폴더 선택: {path}")
            self._maybe_fill_repo_name()

    @Slot()
    def on_publish(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        assert self.editFolder is not None
        assert self.editRepoName is not None
        assert self.editCommitMessage is not None
        assert self.checkAllowSecrets is not None

        folder = (self.editFolder.text() or "").strip()
        name = (self.editRepoName.text() or "").strip()
        msg = (self.editCommitMessage.text() or "Initial commit").strip()
        allow = self.checkAllowSecrets.isChecked()
        private = bool(self.radioPrivate and self.radioPrivate.isChecked())

        if not folder:
            QMessageBox.warning(self.window, "CloneUp", "로컬 폴더를 선택하세요.")
            return
        path = Path(folder).expanduser()
        if not path.is_dir():
            QMessageBox.warning(self.window, "CloneUp", f"폴더가 없습니다:\n{folder}")
            return
        if not name:
            name = path.name
            self.editRepoName.setText(name)

        # Preflight on UI thread (fast) — S1 / S3
        report = run_safety_checks(
            path.resolve(),
            allow_secrets=allow,
            write_gitignore=False,  # worker/publish will write if needed
        )
        if not report.ok:
            detail = "\n".join(report.errors)
            self._log(f"사전 검사 실패: {detail}")
            QMessageBox.warning(
                self.window,
                "올릴 수 없음",
                detail
                + (
                    "\n\n비밀 파일을 꼭 올려야 하면 "
                    "「비밀 파일… 진행」을 켠 뒤 다시 시도하세요."
                    if report.secret_candidates
                    else ""
                ),
            )
            return

        if report.secret_candidates and allow:
            ans = QMessageBox.question(
                self.window,
                "비밀 파일 경고",
                "다음 파일이 포함될 수 있습니다:\n"
                + "\n".join(report.secret_candidates)
                + "\n\n계속할까요?",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        self._log("--- Publish 시작 ---")
        self._log(f"  folder={path}")
        self._log(f"  name={name}")
        self._log(f"  visibility={'private' if private else 'public'}")
        self._log(f"  message={msg}")

        self._set_busy(True)
        worker = PublishWorker(
            folder=str(path.resolve()),
            repo_name=name,
            commit_message=msg,
            private=private,
            allow_secrets=allow,
            parent=self,
        )
        worker.log_line.connect(self._log)
        worker.succeeded.connect(self._on_publish_ok)
        worker.failed.connect(self._on_publish_err)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    @Slot(dict)
    def _on_publish_ok(self, result: dict) -> None:
        self._log("=== 성공 ===")
        self._log(f"  {result.get('html_url')}")
        self._refresh_status_bar()
        url = result.get("html_url") or ""
        QMessageBox.information(
            self.window,
            "업로드 완료",
            f"저장소: {result.get('full_name')}\n"
            f"{url}\n\n"
            f".git/config 토큰 없음: {result.get('config_clean')}",
        )
        if url:
            QDesktopServices.openUrl(QUrl(url))

    @Slot(str)
    def _on_publish_err(self, message: str) -> None:
        self._log(f"ERROR: {message}")
        QMessageBox.critical(self.window, "업로드 실패", message)

    @Slot()
    def _on_worker_finished(self) -> None:
        self._set_busy(False)
        self._worker = None
