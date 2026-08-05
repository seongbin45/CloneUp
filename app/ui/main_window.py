"""Main window — Publish / Clone / Sync tabs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QFile, QObject, QUrl, Slot
from PySide6.QtGui import QColor, QDesktopServices, QTextCharFormat, QTextCursor
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

from app.git.publish import peek_commit_email
from app.git.runner import GitError, require_git
from app.git.safety import (
    find_secret_candidates,
    format_pii_list,
    format_secret_list,
    run_safety_checks,
    scan_pii_in_contents,
)
from app.git.url_utils import UrlError, normalize_github_clone_url
from app.auth.token_store import load_token
from app.ui.auth_status import AuthState, AuthStatusButton
from app.ui.device_code_dialog import DeviceCodeOverlay
from app.ui.publish_worker import LoginWorker, PublishWorker
from app.ui.tip_card import install_tip_card
from app.util.next_action import format_next_step_line
from app.ui.settings_store import (
    load_last_commit_message,
    load_last_private,
    load_recent_folders,
    remember_folder,
    save_last_commit_message,
    save_last_private,
)
from app.ui.tab_workers import CloneWorker, SyncActionWorker, SyncStatusWorker
from app.ui.theme import active_palette

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

    ctrl = MainController(window)
    window._cloneup_controller = ctrl  # keep strong ref
    return window


class MainController(QObject):
    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.window = window
        self._worker = None  # any QThread worker
        self._device_overlay: DeviceCodeOverlay | None = None
        # Device popup cancel button: "로그아웃" when re-login, else "로그인 취소"
        self._device_cancel_label = "로그인 취소"
        self.window.installEventFilter(self)

        # --- shared ---
        self.labelStatusGit = window.findChild(QLabel, "labelStatusGit")
        self.textLog = window.findChild(QPlainTextEdit, "textLog")
        self.btnCancel = window.findChild(QPushButton, "btnCancel")
        btn_auth = window.findChild(QPushButton, "btnAuthStatus")
        if btn_auth is None:
            raise RuntimeError("btnAuthStatus 위젯 없음 — UI에 상태형 로그인 버튼이 필요합니다")
        self.auth_status = AuthStatusButton(btn_auth, parent=self)

        # D2 — recolor status-row widgets when OS light/dark flips
        # (inline setStyleSheet overrides global QSS and would stay light)
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.styleHints().colorSchemeChanged.connect(
                    self._on_color_scheme_changed
                )
        except Exception:
            pass

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

        self._install_tab_tip_cards()
        self._wire()
        self._load_prefs()
        self._refresh_status_bar()
        self._log("CloneUp — 만들고 올리기 / 받기 / 동기화 탭 사용 가능")

    def _install_tab_tip_cards(self) -> None:
        """G1/G2 — collapsible tip cards (folded by default to save space)."""
        tips: list[tuple[str, str, str]] = [
            (
                "labelTabIntroPublish",
                "내 컴퓨터 폴더를 GitHub에 처음 올립니다.",
                "• 저장소 이름에 쓸 수 없는 문자가 있으면 실패합니다.\n"
                "• 공개로 만들면 누구나 볼 수 있고, 되돌리기 어렵습니다.\n"
                "• .env 같은 비밀 파일 후보는 기본적으로 올리지 않습니다.",
            ),
            (
                "labelTabIntroClone",
                "GitHub에 있는 폴더를 내 컴퓨터로 복사합니다.",
                "• 저장소 루트 주소만 쓰세요. /tree/main 은 자동으로 정리됩니다.\n"
                "• 같은 이름의 폴더가 이미 있으면 실패합니다. 이름을 바꾸세요.\n"
                "• 비공개 저장소는 위 GitHub 로그인이 필요합니다.",
            ),
            (
                "labelTabIntroSync",
                "이미 연결된 폴더의 변경사항을 주고받습니다.",
                "• 이 폴더에 .git 이 있어야 합니다. 없으면 「받기」나 「만들고 올리기」를 먼저 하세요.\n"
                "• 올리기 전에 비밀 파일 후보가 있는지 확인하세요.\n"
                "• push 권한 오류가 나면 GitHub 로그인을 다시 하세요.",
            ),
        ]
        for obj_name, summary, body in tips:
            ph = self.window.findChild(QLabel, obj_name)
            if ph is not None:
                install_tip_card(ph, summary=summary, body=body)

    # ----- helpers -----
    def _log(self, message: str) -> None:
        """Append a log line; color by kind for dark terminal contrast (desin D4)."""
        assert self.textLog is not None
        p = active_palette()
        if p.name == "dark":
            base, dim, ok, err, warn = (
                p.text_log,
                p.text_log_dim,
                p.text_log_ok,
                p.text_log_err,
                p.text_log_warn,
            )
        else:
            base, dim, ok, err, warn = (
                p.text,
                p.text_muted,
                p.success_dot,
                p.danger,
                p.warn_text,
            )

        color = base
        msg = message or ""
        low = msg.lower()
        if msg.startswith("ERROR") or "실패" in msg or "✗" in msg:
            color = err
        elif "성공" in msg or "✓" in msg or msg.startswith("Clone 성공") or msg.startswith("Publish 성공"):
            color = ok
        elif (
            msg.startswith("다음:")
            or "안내" in msg
            or "경고" in msg
            or "비권장" in msg
        ):
            color = warn
        elif msg.startswith("---") or msg.startswith(">") or low.startswith("git "):
            color = dim

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self.textLog.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.textLog.toPlainText():
            cursor.insertText("\n")
        cursor.insertText(msg, fmt)
        self.textLog.setTextCursor(cursor)
        self.textLog.ensureCursorVisible()

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
        # Non-login workers: mid-flow first auth keeps "로그인 취소"
        if not isinstance(worker, LoginWorker):
            self._device_cancel_label = "로그인 취소"
        if hasattr(worker, "log_line"):
            worker.log_line.connect(self._log)
        if hasattr(worker, "user_code_ready"):
            worker.user_code_ready.connect(self._show_device_code_overlay)
        worker.finished.connect(self._on_worker_finished)
        self._set_global_busy(True)
        worker.start()

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if obj is self.window and et == QEvent.Type.Close:
            if not getattr(self, "_closing", False):
                self._closing = True
                self._shutdown_workers()
                self._close_device_overlay()
        elif obj is self.window and et in (
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
        ):
            # Maximize / restore: keep device-code dim covering full client area
            if self._device_overlay is not None:
                self._device_overlay.sync_geometry()
        return False

    def _shutdown_workers(self) -> None:
        w = self._worker
        if w is not None and w.isRunning():
            w.requestInterruption()
            if not w.wait(8000):
                w.terminate()
                w.wait(2000)
        self._worker = None

    def _close_device_overlay(self) -> None:
        if self._device_overlay is not None:
            self._device_overlay.hide()
            self._device_overlay.deleteLater()
            self._device_overlay = None

    @Slot(str, str, int)
    def _show_device_code_overlay(
        self, user_code: str, verification_uri: str, expires_in: int
    ) -> None:
        """UI thread: dim background + code popup until login finishes."""
        self._close_device_overlay()
        overlay = DeviceCodeOverlay(
            self.window,
            user_code=user_code,
            verification_uri=verification_uri,
            expires_in=expires_in,
            cancel_label=self._device_cancel_label,
        )
        overlay.cancelled.connect(self.on_cancel)
        overlay.show()
        overlay.sync_geometry()
        overlay.raise_()
        self._device_overlay = overlay
        self._log(f"장치 코드 팝업: {user_code}")

    @Slot()
    def _on_worker_finished(self) -> None:
        self._close_device_overlay()
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

    def _on_color_scheme_changed(self, *_args) -> None:
        """OS theme changed — main.py already reapplied QSS; refresh inline styles."""
        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        # Design: green status dot + "Git: x.y.z" (desin status row)
        p = active_palette()
        if self.labelStatusGit is not None:
            try:
                _e, ver = require_git()
                self.labelStatusGit.setText(
                    f"●  Git: {ver[0]}.{ver[1]}.{ver[2]}"
                )
                # success_dot for ● (desin green); whole label one color
                self.labelStatusGit.setStyleSheet(
                    f"color: {p.success_dot}; font-size: 12.5px;"
                )
            except GitError:
                self.labelStatusGit.setText("●  Git: 없음")
                self.labelStatusGit.setStyleSheet(
                    f"color: {p.text_faint}; font-size: 12.5px;"
                )
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
        """Cancel login / publish / clone / sync worker and close code popup."""
        self._log("취소 요청…")
        # Close popup immediately so the UI feels responsive.
        if self._device_overlay is not None:
            self._device_overlay.set_waiting_message(
                "취소 중… 잠시만 기다려 주세요."
            )
        w = self._worker
        if w is not None and w.isRunning():
            w.requestInterruption()
        else:
            # No worker — still dismiss overlay if any
            self._close_device_overlay()

    @Slot()
    def on_login(self) -> None:
        if self._busy():
            return
        # Re-login (already had a session) → cancel on popup acts as logout
        had_session = (
            self.auth_status.state
            in (AuthState.LOGGED_IN, AuthState.SCOPE_INSUFFICIENT)
            or bool(load_token())
        )
        if had_session:
            reply = QMessageBox.warning(
                self.window,
                "재로그인 확인",
                "저장된 GitHub 로그인 정보를 삭제하고\n"
                "새 장치 코드 인증을 시작합니다.\n\n"
                "다른 계정으로 로그인할 수 있습니다.\n\n"
                "확인을 누르면 현재 세션이 로그아웃됩니다.\n"
                "취소를 누르면 현재 로그인을 유지합니다.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                self._log("재로그인 취소됨 — 기존 로그인 유지")
                return

        self._device_cancel_label = "로그아웃" if had_session else "로그인 취소"
        self._log("--- GitHub 로그인 ---")
        w = LoginWorker(force=True, parent=self)
        w.succeeded.connect(self._on_login_ok)
        w.failed.connect(self._on_fail_msg)
        self._start_worker(w)

    @Slot(dict)
    def _on_login_ok(self, info: dict) -> None:
        self._close_device_overlay()
        login = info.get("login") or ""
        self.auth_status.set_login_name(str(login) if login else None)
        self.auth_status.refresh()
        self._log(f"로그인 완료: {login} {info.get('token_masked')}")
        QMessageBox.information(
            self.window, "로그인 완료", f"{login}\nscope={info.get('scope')!r}"
        )

    @Slot(str)
    def _on_fail_msg(self, message: str) -> None:
        self._close_device_overlay()
        self._log(f"ERROR: {message}")
        # G4 — one next-step line under the raw/Korean error
        next_line = format_next_step_line(message)
        if next_line:
            self._log(next_line)
        if message.startswith("취소"):
            QMessageBox.information(self.window, "취소됨", message)
        else:
            # Dialog: error + next step when available
            body = message
            if next_line:
                body = f"{message}\n\n{next_line}"
            QMessageBox.critical(self.window, "실패", body)

    def _confirm_upload_g3(
        self,
        folder: Path,
        *,
        allow_secrets: bool,
        private: bool | None,
        title: str = "올리기 전 확인",
    ) -> bool:
        """
        G3 — plain-language preflight before commit/push.
        Secrets list + commit email disclosure. Cancel = do not start worker.
        """
        parts: list[str] = []
        secrets = find_secret_candidates(folder)
        if secrets:
            listing = format_secret_list(secrets)
            if not allow_secrets:
                QMessageBox.warning(
                    self.window,
                    "올릴 수 없음",
                    "비밀 파일로 보이는 항목이 있습니다.\n\n"
                    f"{listing}\n\n"
                    "파일을 제거·이름 변경하거나, "
                    "「비밀 파일로 보이는 항목이 있어도 진행」을 켠 뒤 다시 시도하세요.",
                )
                return False
            vis = (
                "비공개 저장소여도 협업자·유출 시 위험합니다."
                if private
                else "공개 저장소면 인터넷에 그대로 보일 수 있습니다."
            )
            parts.append(
                "다음 파일이 포함될 수 있습니다:\n"
                f"{listing}\n\n"
                f"이대로 올리면 인터넷에 공개될 수 있습니다. ({vis})"
            )

        # Content PII (phone/email) — Command-to-commit-changes-from-Git patterns
        pii_hits = scan_pii_in_contents(folder)
        if pii_hits:
            listing = format_pii_list(pii_hits)
            parts.append(
                "파일 내용에서 개인정보로 보이는 값이 있습니다 "
                "(전화·이메일 패턴):\n"
                f"{listing}\n\n"
                "이대로 올리면 인터넷에 공개될 수 있습니다. "
                "필요하면 올리기 전에 지우거나 가리세요."
            )

        email = peek_commit_email(folder)
        parts.append(
            "이 이메일이 커밋에 기록되어 공개됩니다:\n"
            f"  {email}"
        )

        body = "\n\n".join(parts) + "\n\n계속할까요?"
        reply = QMessageBox.warning(
            self.window,
            title,
            body,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Ok

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
            # Prefer G3-style secret listing when that is the only block
            if report.secret_candidates and not allow:
                self._confirm_upload_g3(
                    path.resolve(), allow_secrets=False, private=private
                )
                return
            QMessageBox.warning(self.window, "올릴 수 없음", "\n".join(report.errors))
            return

        if not self._confirm_upload_g3(
            path.resolve(), allow_secrets=allow, private=private
        ):
            self._log("Publish 취소 — 확인 대화상자")
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
        self._close_device_overlay()
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

        if action == "push":
            path = Path(folder.strip()).expanduser()
            if path.is_dir():
                if not self._confirm_upload_g3(
                    path.resolve(),
                    allow_secrets=allow,
                    private=None,
                    title="올리고 보내기 전 확인",
                ):
                    self._log("Sync push 취소 — 확인 대화상자")
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
