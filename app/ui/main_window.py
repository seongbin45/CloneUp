"""Main window — Publish / Clone / Sync tabs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, QObject, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
)

from app.git.runner import GitError, require_git
from app.git.safety import run_safety_checks
from app.git.url_utils import UrlError, normalize_github_clone_url
from app.ui.auth_status import AuthStatusButton
from app.ui.publish_worker import LoginWorker, PublishWorker
from app.ui.settings_store import (
    load_last_commit_message,
    load_last_private,
    load_recent_folders,
    remember_folder,
    save_last_commit_message,
    save_last_private,
)
from app.ui.tab_workers import CloneWorker, SyncActionWorker, SyncStatusWorker

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
        wrap.resize(760, 620)
        window = wrap

    MainController(window)
    return window


class MainController(QObject):
    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.window = window
        self._worker = None  # any QThread worker

        # --- shared ---
        self.labelStatusGit = window.findChild(QLabel, "labelStatusGit")
        self.textLog = window.findChild(QPlainTextEdit, "textLog")
        self.btnCancel = window.findChild(QPushButton, "btnCancel")
        btn_auth = window.findChild(QPushButton, "btnAuthStatus")
        if btn_auth is None:
            raise RuntimeError("btnAuthStatus 위젯 없음 — UI에 상태형 로그인 버튼이 필요합니다")
        self.auth_status = AuthStatusButton(btn_auth, parent=self)

        # --- publish ---
        self.editFolder = window.findChild(QLineEdit, "editFolder")
        self.btnBrowseFolder = window.findChild(QPushButton, "btnBrowseFolder")
        self.comboRecent = window.findChild(QComboBox, "comboRecent")
        self.editRepoName = window.findChild(QLineEdit, "editRepoName")
        self.radioPublic = window.findChild(QRadioButton, "radioPublic")
        self.radioPrivate = window.findChild(QRadioButton, "radioPrivate")
        self.editCommitMessage = window.findChild(QLineEdit, "editCommitMessage")
        self.checkAllowSecrets = window.findChild(QCheckBox, "checkAllowSecrets")
        self.btnPublish = window.findChild(QPushButton, "btnPublish")

        # --- clone ---
        self.editCloneUrl = window.findChild(QLineEdit, "editCloneUrl")
        self.editCloneParent = window.findChild(QLineEdit, "editCloneParent")
        self.btnCloneBrowseParent = window.findChild(QPushButton, "btnCloneBrowseParent")
        self.editCloneDirName = window.findChild(QLineEdit, "editCloneDirName")
        self.checkCloneUseToken = window.findChild(QCheckBox, "checkCloneUseToken")
        self.btnClone = window.findChild(QPushButton, "btnClone")
        self.btnCloneCancel = window.findChild(QPushButton, "btnCloneCancel")

        # --- sync ---
        self.editSyncFolder = window.findChild(QLineEdit, "editSyncFolder")
        self.btnSyncBrowse = window.findChild(QPushButton, "btnSyncBrowse")
        self.btnSyncRefresh = window.findChild(QPushButton, "btnSyncRefresh")
        self.labelSyncStatus = window.findChild(QLabel, "labelSyncStatus")
        self.editSyncMessage = window.findChild(QLineEdit, "editSyncMessage")
        self.checkSyncAllowSecrets = window.findChild(QCheckBox, "checkSyncAllowSecrets")
        self.btnSyncPull = window.findChild(QPushButton, "btnSyncPull")
        self.btnSyncPush = window.findChild(QPushButton, "btnSyncPush")
        self.btnSyncAbort = window.findChild(QPushButton, "btnSyncAbort")
        self.btnSyncCancel = window.findChild(QPushButton, "btnSyncCancel")

        if self.textLog is None or self.btnPublish is None:
            raise RuntimeError("필수 UI 위젯 누락")

        self._wire()
        self._load_prefs()
        self._refresh_status_bar()
        self._log("CloneUp — 만들고 올리기 / 받기 / 동기화 탭 사용 가능")

    # ----- helpers -----
    def _log(self, message: str) -> None:
        assert self.textLog is not None
        self.textLog.appendPlainText(message)

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _set_global_busy(self, busy: bool) -> None:
        # publish
        for w in (
            self.btnPublish,
            self.btnBrowseFolder,
            self.comboRecent,
            self.editFolder,
            self.editRepoName,
            self.editCommitMessage,
            self.radioPublic,
            self.radioPrivate,
            self.checkAllowSecrets,
        ):
            if w is not None:
                w.setEnabled(not busy)
        self.auth_status.set_enabled(not busy)
        if self.btnPublish is not None:
            self.btnPublish.setText(
                "올리는 중…" if busy else "GitHub에 만들고 올리기"
            )
        if self.btnCancel is not None:
            self.btnCancel.setEnabled(busy and isinstance(self._worker, (PublishWorker, LoginWorker)))

        # clone
        for w in (
            self.btnClone,
            self.btnCloneBrowseParent,
            self.editCloneUrl,
            self.editCloneParent,
            self.editCloneDirName,
            self.checkCloneUseToken,
        ):
            if w is not None:
                w.setEnabled(not busy)
        if self.btnCloneCancel is not None:
            self.btnCloneCancel.setEnabled(busy and isinstance(self._worker, CloneWorker))
        if self.btnClone is not None:
            self.btnClone.setText("받는 중…" if busy and isinstance(self._worker, CloneWorker) else "저장소 받기")

        # sync
        for w in (
            self.btnSyncBrowse,
            self.btnSyncRefresh,
            self.btnSyncPull,
            self.btnSyncPush,
            self.btnSyncAbort,
            self.editSyncFolder,
            self.editSyncMessage,
            self.checkSyncAllowSecrets,
        ):
            if w is not None:
                w.setEnabled(not busy)
        if self.btnSyncCancel is not None:
            self.btnSyncCancel.setEnabled(
                busy and isinstance(self._worker, SyncActionWorker)
            )

    def _start_worker(self, worker) -> None:
        self._worker = worker
        worker.log_line.connect(self._log)
        worker.finished.connect(self._on_worker_finished)
        self._set_global_busy(True)
        worker.start()

    @Slot()
    def _on_worker_finished(self) -> None:
        self._set_global_busy(False)
        self._worker = None
        self._refresh_status_bar()

    def _wire(self) -> None:
        if self.btnBrowseFolder:
            self.btnBrowseFolder.clicked.connect(self.on_browse_folder)
        if self.btnPublish:
            self.btnPublish.clicked.connect(self.on_publish)
        if self.btnCancel:
            self.btnCancel.clicked.connect(self.on_cancel)
        self.auth_status.login_requested.connect(self.on_login)
        if self.editFolder:
            self.editFolder.editingFinished.connect(self._maybe_fill_repo_name)
        if self.comboRecent:
            self.comboRecent.activated.connect(self._on_recent_activated)

        if self.btnCloneBrowseParent:
            self.btnCloneBrowseParent.clicked.connect(self.on_clone_browse_parent)
        if self.btnClone:
            self.btnClone.clicked.connect(self.on_clone)
        if self.btnCloneCancel:
            self.btnCloneCancel.clicked.connect(self.on_cancel)
        if self.editCloneUrl:
            self.editCloneUrl.editingFinished.connect(self._maybe_fill_clone_dirname)

        if self.btnSyncBrowse:
            self.btnSyncBrowse.clicked.connect(self.on_sync_browse)
        if self.btnSyncRefresh:
            self.btnSyncRefresh.clicked.connect(self.on_sync_refresh)
        if self.btnSyncPull:
            self.btnSyncPull.clicked.connect(lambda: self.on_sync_action("pull"))
        if self.btnSyncPush:
            self.btnSyncPush.clicked.connect(lambda: self.on_sync_action("push"))
        if self.btnSyncAbort:
            self.btnSyncAbort.clicked.connect(lambda: self.on_sync_action("abort"))
        if self.btnSyncCancel:
            self.btnSyncCancel.clicked.connect(self.on_cancel)

    def _load_prefs(self) -> None:
        if self.editCommitMessage is not None:
            self.editCommitMessage.setText(load_last_commit_message())
        if load_last_private() and self.radioPrivate is not None:
            self.radioPrivate.setChecked(True)
        elif self.radioPublic is not None:
            self.radioPublic.setChecked(True)
        self._reload_recent_combo()
        recent = load_recent_folders()
        if recent and self.editFolder is not None and not self.editFolder.text():
            for p in recent:
                if Path(p).is_dir():
                    self.editFolder.setText(p)
                    self._maybe_fill_repo_name()
                    break
        if self.editCloneParent is not None and not self.editCloneParent.text():
            self.editCloneParent.setText(str(Path.home() / "Desktop"))

    def _reload_recent_combo(self) -> None:
        if self.comboRecent is None:
            return
        self.comboRecent.blockSignals(True)
        self.comboRecent.clear()
        self.comboRecent.addItem("(최근 폴더 선택)")
        for p in load_recent_folders():
            self.comboRecent.addItem(p)
        self.comboRecent.setCurrentIndex(0)
        self.comboRecent.blockSignals(False)

    def _refresh_status_bar(self) -> None:
        if self.labelStatusGit is not None:
            try:
                _e, ver = require_git()
                self.labelStatusGit.setText(f"Git: {ver[0]}.{ver[1]}.{ver[2]}")
            except GitError:
                self.labelStatusGit.setText("Git: 없음")
        self.auth_status.refresh()

    # ----- publish -----
    @Slot()
    def _maybe_fill_repo_name(self) -> None:
        if not self.editFolder or not self.editRepoName:
            return
        if (self.editRepoName.text() or "").strip():
            return
        folder = (self.editFolder.text() or "").strip()
        if folder:
            self.editRepoName.setText(Path(folder).name)

    @Slot(int)
    def _on_recent_activated(self, index: int) -> None:
        if not self.comboRecent or index <= 0:
            return
        path = self.comboRecent.itemText(index)
        if self.editFolder:
            self.editFolder.setText(path)
            self._log(f"최근 폴더: {path}")
            self._maybe_fill_repo_name()

    @Slot()
    def on_browse_folder(self) -> None:
        if not self.editFolder:
            return
        start = (self.editFolder.text() or "").strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self.window, "올릴 폴더 선택", start)
        if path:
            self.editFolder.setText(path)
            remember_folder(path)
            self._reload_recent_combo()
            self._log(f"폴더 선택: {path}")
            self._maybe_fill_repo_name()

    @Slot()
    def on_cancel(self) -> None:
        if not self._busy():
            return
        self._log("취소 요청…")
        self._worker.requestInterruption()

    @Slot()
    def on_login(self) -> None:
        if self._busy():
            return
        self._log("--- GitHub 로그인 ---")
        w = LoginWorker(force=True, parent=self)
        w.succeeded.connect(self._on_login_ok)
        w.failed.connect(self._on_fail_msg)
        self._start_worker(w)

    @Slot(dict)
    def _on_login_ok(self, info: dict) -> None:
        login = info.get("login") or ""
        self.auth_status.set_login_name(str(login) if login else None)
        self.auth_status.refresh()
        self._log(f"로그인 완료: {login} {info.get('token_masked')}")
        QMessageBox.information(
            self.window, "로그인 완료", f"{login}\nscope={info.get('scope')!r}"
        )

    @Slot(str)
    def _on_fail_msg(self, message: str) -> None:
        self._log(f"ERROR: {message}")
        if message.startswith("취소"):
            QMessageBox.information(self.window, "취소됨", message)
        else:
            QMessageBox.critical(self.window, "실패", message)

    @Slot()
    def on_publish(self) -> None:
        if self._busy() or not self.editFolder or not self.editRepoName:
            return
        folder = (self.editFolder.text() or "").strip()
        name = (self.editRepoName.text() or "").strip()
        msg = (
            (self.editCommitMessage.text() if self.editCommitMessage else None)
            or "Initial commit"
        ).strip()
        allow = bool(self.checkAllowSecrets and self.checkAllowSecrets.isChecked())
        private = bool(self.radioPrivate and self.radioPrivate.isChecked())

        if not folder:
            QMessageBox.warning(self.window, "CloneUp", "로컬 폴더를 선택하세요.")
            return
        path = Path(folder).expanduser()
        if not path.is_dir():
            QMessageBox.warning(self.window, "CloneUp", f"폴더 없음:\n{folder}")
            return
        if not name:
            name = path.name
            self.editRepoName.setText(name)

        report = run_safety_checks(
            path.resolve(), allow_secrets=allow, write_gitignore=False
        )
        if not report.ok:
            QMessageBox.warning(self.window, "올릴 수 없음", "\n".join(report.errors))
            return

        remember_folder(str(path.resolve()))
        self._reload_recent_combo()
        save_last_private(private)
        save_last_commit_message(msg)

        self._log(f"--- Publish: {name} ({'private' if private else 'public'}) ---")
        w = PublishWorker(
            folder=str(path.resolve()),
            repo_name=name,
            commit_message=msg,
            private=private,
            allow_secrets=allow,
            parent=self,
        )
        w.succeeded.connect(self._on_publish_ok)
        w.failed.connect(self._on_fail_msg)
        self._start_worker(w)

    @Slot(dict)
    def _on_publish_ok(self, result: dict) -> None:
        self._log(f"Publish 성공: {result.get('html_url')}")
        url = result.get("html_url") or ""
        QMessageBox.information(
            self.window,
            "업로드 완료",
            f"{result.get('full_name')}\n{url}",
        )
        if url:
            QDesktopServices.openUrl(QUrl(url))
        # offer to open in Sync tab
        if self.editSyncFolder is not None and result.get("folder"):
            self.editSyncFolder.setText(str(result["folder"]))

    # ----- clone -----
    @Slot()
    def _maybe_fill_clone_dirname(self) -> None:
        if not self.editCloneUrl or not self.editCloneDirName:
            return
        if (self.editCloneDirName.text() or "").strip():
            return
        raw = (self.editCloneUrl.text() or "").strip()
        if not raw:
            return
        try:
            n = normalize_github_clone_url(raw)
            self.editCloneDirName.setText(n.repo)
            for w in n.warnings:
                self._log(f"URL 안내: {w}")
        except UrlError:
            pass

    @Slot()
    def on_clone_browse_parent(self) -> None:
        if not self.editCloneParent:
            return
        start = (self.editCloneParent.text() or "").strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self.window, "저장 위치", start)
        if path:
            self.editCloneParent.setText(path)

    @Slot()
    def on_clone(self) -> None:
        if self._busy():
            return
        url = (self.editCloneUrl.text() if self.editCloneUrl else "") or ""
        parent = (self.editCloneParent.text() if self.editCloneParent else "") or ""
        name = (self.editCloneDirName.text() if self.editCloneDirName else "") or ""
        use_token = bool(
            self.checkCloneUseToken is None or self.checkCloneUseToken.isChecked()
        )

        if not url.strip():
            QMessageBox.warning(self.window, "CloneUp", "GitHub 주소를 입력하세요.")
            return
        if not parent.strip() or not Path(parent).expanduser().is_dir():
            QMessageBox.warning(self.window, "CloneUp", "저장 위치 폴더를 선택하세요.")
            return
        try:
            norm = normalize_github_clone_url(url)
            for w in norm.warnings:
                self._log(f"URL 안내: {w}")
        except UrlError as e:
            QMessageBox.warning(self.window, "주소 오류", str(e))
            return

        self._log(f"--- Clone: {norm.clone_url} ---")
        w = CloneWorker(
            url=url.strip(),
            parent_dir=str(Path(parent).expanduser().resolve()),
            dir_name=name.strip(),
            use_token=use_token,
            parent=self,
        )
        w.succeeded.connect(self._on_clone_ok)
        w.failed.connect(self._on_fail_msg)
        self._start_worker(w)

    @Slot(dict)
    def _on_clone_ok(self, result: dict) -> None:
        path = result.get("path") or ""
        self._log(f"Clone 성공: {path}")
        remember_folder(path)
        self._reload_recent_combo()
        if self.editSyncFolder is not None:
            self.editSyncFolder.setText(path)
        QMessageBox.information(
            self.window,
            "받기 완료",
            f"{result.get('owner')}/{result.get('repo')}\n{path}",
        )

    # ----- sync -----
    @Slot()
    def on_sync_browse(self) -> None:
        if not self.editSyncFolder:
            return
        start = (self.editSyncFolder.text() or "").strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self.window, "로컬 저장소", start)
        if path:
            self.editSyncFolder.setText(path)
            self.on_sync_refresh()

    @Slot()
    def on_sync_refresh(self) -> None:
        if self._busy():
            return
        folder = (self.editSyncFolder.text() if self.editSyncFolder else "") or ""
        if not folder.strip():
            QMessageBox.warning(self.window, "CloneUp", "동기화할 폴더를 선택하세요.")
            return
        self._log(f"--- 상태: {folder} ---")
        w = SyncStatusWorker(folder=folder.strip(), parent=self)
        w.succeeded.connect(self._on_sync_status)
        w.failed.connect(self._on_fail_msg)
        # status has no log_line always — connect if present
        if hasattr(w, "log_line"):
            w.log_line.connect(self._log)
        self._start_worker(w)

    @Slot(dict)
    def _on_sync_status(self, st: dict) -> None:
        summary = st.get("summary") or ""
        if self.labelSyncStatus is not None:
            self.labelSyncStatus.setText(f"상태: {summary}")
        self._log(summary)
        if st.get("conflict"):
            QMessageBox.warning(
                self.window,
                "충돌 상태",
                "병합 충돌 중입니다.\n"
                "「충돌 취소」로 되돌리거나, 에디터에서 수동 해결하세요.",
            )

    @Slot()
    def on_sync_action(self, action: str) -> None:
        if self._busy():
            return
        folder = (self.editSyncFolder.text() if self.editSyncFolder else "") or ""
        if not folder.strip():
            QMessageBox.warning(self.window, "CloneUp", "동기화할 폴더를 선택하세요.")
            return
        msg = (
            (self.editSyncMessage.text() if self.editSyncMessage else None) or "Update"
        ).strip()
        allow = bool(
            self.checkSyncAllowSecrets and self.checkSyncAllowSecrets.isChecked()
        )

        if action == "abort":
            ans = QMessageBox.question(
                self.window,
                "충돌 취소",
                "진행 중인 merge/rebase 를 취소할까요?\n"
                "(git merge --abort / rebase --abort)",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        if action == "pull":
            ans = QMessageBox.question(
                self.window,
                "받아오기",
                "원격 변경을 pull 합니다.\n"
                "충돌이 나면 이 앱으로 해결하지 않고 안내만 합니다. 계속할까요?",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        self._log(f"--- Sync {action}: {folder} ---")
        w = SyncActionWorker(
            action=action,
            folder=folder.strip(),
            message=msg,
            allow_secrets=allow,
            parent=self,
        )
        w.succeeded.connect(self._on_sync_action_ok)
        w.failed.connect(self._on_fail_msg)
        self._start_worker(w)

    @Slot(str)
    def _on_sync_action_ok(self, message: str) -> None:
        self._log(message)
        QMessageBox.information(self.window, "동기화", message[:1500] or "완료")
        # refresh status after action
        if self.editSyncFolder and (self.editSyncFolder.text() or "").strip():
            # chain a status refresh without blocking — schedule after busy clears
            # call after finished: use QTimer single shot
            from PySide6.QtCore import QTimer

            QTimer.singleShot(100, self.on_sync_refresh)
