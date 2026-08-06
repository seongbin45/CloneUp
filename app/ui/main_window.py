"""Main window — Publish / Clone / Sync tabs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QFile, QObject, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
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
    QTabWidget,
)

from app.git.publish import preview_commit_email
from app.git.runner import GitError, require_git
from app.git.safety import (
    find_secret_candidates,
    format_pii_list,
    format_secret_list,
    run_safety_checks,
    scan_pii_in_contents,
)
from app.git.url_utils import UrlError, normalize_github_clone_url
from app.auth.token_store import delete_token, load_token
from app.paths import app_root
from app.ui.auth_status import AuthState, AuthStatusButton
from app.ui.device_code_dialog import DeviceCodeOverlay
from app.auth.session import MISSING_REPO_MARKER
from app.ui.login_dialog import (
    ConnectGitHubWizard,
    parse_scopes_from_missing_repo_message,
    show_missing_repo_help,
)
from app.ui.publish_worker import LoginWorker, PatLoginWorker, PublishWorker
from app.ui.success_dialog import show_clone_success, show_publish_success
from app.ui.tip_card import install_tip_card
from app.util.next_action import format_next_step_line
from app.ui.settings_store import (
    load_hide_real_email,
    load_last_commit_message,
    load_last_private,
    load_recent_folders,
    remember_folder,
    save_hide_real_email,
    save_last_commit_message,
    save_last_private,
)
from app.ui.tab_workers import CloneWorker, SyncActionWorker, SyncStatusWorker
from app.ui.theme import active_palette


def _ui_path() -> Path:
    return app_root() / "ui" / "main_window.ui"


def _format_commit_email_g3(
    email: str,
    *,
    private: bool | None,
    hide_real_email: bool,
) -> str:
    """
    G3 copy for commit author email.

    Not “repo public/private chose this email”. hide_real_email uses GitHub
    noreply for this commit only (PC git config unchanged).
    """
    addr = (email or "").strip()
    is_github_noreply = "users.noreply.github.com" in addr.lower()
    is_hide_preview = hide_real_email or "가림 주소" in addr
    is_placeholder = ("로그인 후" in addr) or (
        "noreply" in addr.lower() and not is_github_noreply and "@" not in addr
    )

    # Keep short — beginners skip long G3 blocks
    lines = ["【커밋에 남을 주소】", f"  {addr}"]

    if hide_real_email or is_hide_preview:
        lines.append("이메일 숨기기 켜짐 → 가림 주소 사용 (PC Git 설정은 그대로)")
    elif is_placeholder:
        lines.append("Git에 메일이 없으면 가림 주소를 씁니다.")
    else:
        lines.append("이 PC Git 설정의 메일입니다. 숨기려면 위 옵션을 켜세요.")

    if private is False:
        lines.append("공개 저장소면 누구나 이 주소를 볼 수 있습니다.")
    elif private is True:
        lines.append("비공개여도 권한이 있는 사람은 볼 수 있습니다.")

    return "\n".join(lines)


def load_main_window() -> QMainWindow:
    ui_path = _ui_path()
    if not ui_path.is_file():
        raise FileNotFoundError(f"UI file missing: {ui_path}")

    ui_file = QFile(str(ui_path))
    if not ui_file.open(QFile.OpenModeFlag.ReadOnly):
        raise RuntimeError(f"Cannot open UI: {ui_path}")

    loader = QUiLoader()
    window = loader.load(ui_file)
    ui_file.close()

    if window is None:
        raise RuntimeError(f"QUiLoader failed: {ui_path}")
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
        # After popup Logout, worker cancel should not look like a failed login
        self._expect_logout_ack = False
        self.window.installEventFilter(self)

        # --- shared ---
        self.tabWidget = window.findChild(QTabWidget, "tabWidget")
        self.labelStatusGit = window.findChild(QLabel, "labelStatusGit")
        self.textLog = window.findChild(QPlainTextEdit, "textLog")
        self.btnCancel = window.findChild(QPushButton, "btnCancel")
        btn_auth = window.findChild(QPushButton, "btnAuthStatus")
        if btn_auth is None:
            raise RuntimeError("btnAuthStatus 위젯 없음 — UI에 상태형 로그인 버튼이 필요합니다")
        self.auth_status = AuthStatusButton(btn_auth, parent=self)
        self.btnLogout = window.findChild(QPushButton, "btnLogout")

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
        self.checkHideEmail = window.findChild(QCheckBox, "checkHideEmail")
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
        self.checkSyncHideEmail = window.findChild(QCheckBox, "checkSyncHideEmail")
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
        # DG1 — first-run Git check (plan D): after UI is up
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._ensure_git_bootstrap)
        QTimer.singleShot(0, self._log_token_age_hint)

    def _ensure_git_bootstrap(self) -> None:
        """Plan D / DG1: if Git missing, offer download page or winget install."""
        from app.git.bootstrap import probe_git
        from app.ui.git_setup import ensure_git_or_offer_setup

        if probe_git().ok:
            return
        ensure_git_or_offer_setup(self.window, log=self._log)
        self._refresh_status_bar()

    def _log_token_age_hint(self) -> None:
        """Soft reminder: PAT may expire; we only know connect age on this PC."""
        from app.auth.token_store import load_token, token_age_info

        if not load_token():
            return
        age = token_age_info()
        if age.level in ("soft", "strong", "stale"):
            self._log(
                f"안내: GitHub 키 연결 후 약 {age.days}일 지남. "
                "만료일이 지났으면 올리기/받기가 실패할 수 있습니다."
            )
            if age.level in ("strong", "stale"):
                self._log(
                    "다음: GitHub 키 목록에서 만료일을 확인하거나, "
                    "새 키로 「GitHub: 연결」을 다시 하세요."
                )

    def _install_tab_tip_cards(self) -> None:
        """G1/G2 — collapsible tip cards (folded by default to save space)."""
        tips: list[tuple[str, str, str]] = [
            (
                "labelTabIntroPublish",
                "내 컴퓨터 폴더를 GitHub에 처음 올립니다.",
                "• 먼저 위쪽 「GitHub: 연결」에서 키를 연결하세요.\n"
                "• 「커밋에 내 이메일 숨기기」를 켜 두면 학교·회사 메일이 안 남습니다.\n"
                "• 공개 저장소는 누구나 볼 수 있고, 되돌리기 어렵습니다.\n"
                "• .env 같은 비밀 파일 후보는 기본적으로 올리지 않습니다.",
            ),
            (
                "labelTabIntroClone",
                "GitHub에 있는 폴더를 내 컴퓨터로 복사합니다.",
                "• 저장소 루트 주소만 쓰세요. /tree/main 은 자동으로 정리됩니다.\n"
                "• 같은 이름의 폴더가 이미 있으면 실패합니다. 이름을 바꾸세요.\n"
                "• 비공개 저장소는 「비공개 저장소 받을 때 GitHub 연결 사용」을 켠 뒤 연결하세요.",
            ),
            (
                "labelTabIntroSync",
                "이미 연결된 폴더의 변경사항을 주고받습니다.",
                "• 이 폴더에 .git 이 있어야 합니다. 없으면 「받기」나 「만들고 올리기」를 먼저 하세요.\n"
                "• 올리기 전에 비밀 파일 후보가 있는지 확인하세요.\n"
                "• 권한 오류가 나면 위쪽 「GitHub: 연결」에서 키를 다시 연결하세요.",
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
            self.checkHideEmail,
            self.checkAllowSecrets,
        ):
            if w is not None:
                w.setEnabled(not busy)
        self.auth_status.set_enabled(not busy)
        if self.btnLogout is not None and self.btnLogout.isVisible():
            self.btnLogout.setEnabled(not busy)
        if self.btnPublish is not None:
            self.btnPublish.setText(
                "올리는 중…" if busy else "GitHub에 만들고 올리기"
            )
        if self.btnCancel is not None:
            self.btnCancel.setEnabled(
                busy
                and isinstance(
                    self._worker, (PublishWorker, LoginWorker, PatLoginWorker)
                )
            )

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
            self.checkSyncHideEmail,
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
        overlay.cancelled.connect(self._on_device_overlay_cancelled)
        overlay.show()
        overlay.sync_geometry()
        overlay.raise_()
        self._device_overlay = overlay
        self._log(f"장치 코드 팝업: {user_code}")

    def _perform_logout(self) -> None:
        """Clear keyring token and refresh status (real logout)."""
        delete_token()
        self.auth_status.set_login_name(None)
        self.auth_status.refresh()
        self._update_logout_button()

    def _notify_logout_done(self) -> None:
        """Friendly ack instead of '로그인이 취소되었습니다' failure dialog."""
        self._expect_logout_ack = False
        QMessageBox.information(
            self.window,
            "로그아웃 완료",
            "로그아웃이 완료되었습니다.\n"
            "저장된 GitHub 로그인 정보가 삭제되었습니다.",
        )

    @Slot()
    def _on_device_overlay_cancelled(self) -> None:
        """
        Device popup cancel button.
        Label 「로그아웃」 → delete token + abort login.
        Label 「로그인 취소」 → abort Device Flow only (keep session if any).
        """
        is_logout = self._device_cancel_label == "로그아웃"
        if is_logout:
            self._log("로그아웃 요청 (장치 코드 팝업)…")
            if self._device_overlay is not None:
                self._device_overlay.set_waiting_message("로그아웃 중…")
            self._perform_logout()
            self._expect_logout_ack = True
        else:
            self._expect_logout_ack = False
            self._log("로그인 취소 요청…")
            if self._device_overlay is not None:
                self._device_overlay.set_waiting_message(
                    "취소 중… 잠시만 기다려 주세요."
                )

        w = self._worker
        if w is not None and w.isRunning():
            w.requestInterruption()
        else:
            self._close_device_overlay()
            self._refresh_status_bar()
            if is_logout:
                self._notify_logout_done()

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
        if self.btnLogout is not None:
            self.btnLogout.clicked.connect(self.on_logout)
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
        hide = load_hide_real_email()
        if self.checkHideEmail is not None:
            self.checkHideEmail.setChecked(hide)
        if self.checkSyncHideEmail is not None:
            self.checkSyncHideEmail.setChecked(hide)
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
        self._update_logout_button()

    def _update_logout_button(self) -> None:
        """Show 로그아웃 only when a GitHub session is stored."""
        if self.btnLogout is None:
            return
        logged_in = bool(load_token())
        self.btnLogout.setVisible(logged_in)
        if logged_in:
            self.btnLogout.setEnabled(not self._busy())

    @Slot()
    def on_logout(self) -> None:
        """Top-bar logout — clear keyring session (beginner-visible control)."""
        if self._busy():
            return
        if not load_token():
            self._update_logout_button()
            return
        reply = QMessageBox.question(
            self.window,
            "로그아웃",
            "GitHub 연결을 끊을까요?\n"
            "이 컴퓨터에 저장된 키 정보가 삭제됩니다.\n\n"
            "다시 쓰려면 「GitHub: 연결」에서 키를 넣으면 됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._perform_logout()
        self._update_logout_button()
        self._log("로그아웃 완료 — 이 컴퓨터에 저장된 연결 정보를 지웠습니다.")
        QMessageBox.information(
            self.window,
            "로그아웃 완료",
            "로그아웃이 완료되었습니다.\n"
            "저장된 GitHub 연결 정보가 삭제되었습니다.",
        )

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
        # Re-login (already had a session) → cancel on device popup acts as logout
        had_session = (
            self.auth_status.state
            in (
                AuthState.LOGGED_IN,
                AuthState.SCOPE_INSUFFICIENT,
                AuthState.TOKEN_AGING,
            )
            or bool(load_token())
        )
        if had_session:
            reply = QMessageBox.warning(
                self.window,
                "다시 연결할까요?",
                "이미 GitHub에 연결되어 있습니다.\n\n"
                "새 키로 바꾸면 이전 연결이 교체됩니다.\n\n"
                "「확인」→ 안내 따라 다시 연결\n"
                "「취소」→ 지금 연결 유지",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                self._log("재로그인 취소됨 — 기존 로그인 유지")
                return

        # Beginner 3-step wizard (PAT only). Security: no public Device Flow.
        wiz = ConnectGitHubWizard(self.window, reauth=had_session)
        if wiz.exec() != ConnectGitHubWizard.DialogCode.Accepted:
            self._log("연결 안내 취소")
            return

        if wiz.wants_device_flow():
            from app.config import is_device_flow_allowed

            if not is_device_flow_allowed():
                QMessageBox.warning(
                    self.window,
                    "연결",
                    "이 방식은 사용할 수 없습니다. 안내의 키 연결을 이용해 주세요.",
                )
                return
            self._device_cancel_label = "로그아웃" if had_session else "로그인 취소"
            self._log("--- GitHub 로그인 (Device Flow, 개발용) ---")
            w = LoginWorker(force=True, parent=self)
            w.succeeded.connect(self._on_login_ok)
            w.failed.connect(self._on_fail_msg)
            self._start_worker(w)
            return

        self._start_pat_login(token=wiz.token())

    def _start_pat_login(self, token: str | None = None) -> None:
        """Store user-issued PAT after GET /user (no OAuth App)."""
        raw = (token or "").strip()
        if not raw:
            wiz = ConnectGitHubWizard(self.window, reauth=False)
            if wiz.exec() != ConnectGitHubWizard.DialogCode.Accepted:
                self._log("연결 안내 취소")
                return
            if wiz.wants_device_flow():
                self._log("개발용 Device Flow는 상태줄 로그인에서만 가능")
                return
            raw = wiz.token()
        if not raw.strip():
            self._log("키가 비어 연결 취소")
            return
        self._device_cancel_label = "로그인 취소"
        self._log("--- GitHub 연결 (키) ---")
        w = PatLoginWorker(raw, parent=self)
        w.succeeded.connect(self._on_login_ok)
        w.failed.connect(self._on_fail_msg)
        self._start_worker(w)

    @Slot(dict)
    def _on_login_ok(self, info: dict) -> None:
        self._close_device_overlay()
        login = info.get("login") or ""
        kind = info.get("auth_kind") or ""
        kind_label = {
            "pat": "키(직접 만든 연결)",
            "device": "브라우저(개발용)",
        }.get(str(kind), "GitHub")
        self.auth_status.set_login_name(str(login) if login else None)
        self.auth_status.refresh()
        self._update_logout_button()
        self._log(
            f"연결 완료 ({kind_label}): {login}"
        )
        QMessageBox.information(
            self.window,
            "연결 완료",
            f"{login} 님, 연결되었습니다.\n"
            "만료일이 지나면 「GitHub: 연결」으로 새 키를 넣으세요.",
        )

    @Slot(str)
    def _on_fail_msg(self, message: str) -> None:
        self._close_device_overlay()
        # Logout from device popup interrupts the login worker — treat as success
        if self._expect_logout_ack:
            self._expect_logout_ack = False
            msg = message or ""
            if "취소" in msg or not msg.strip():
                self._log("로그아웃이 완료되었습니다.")
                QMessageBox.information(
                    self.window,
                    "로그아웃 완료",
                    "로그아웃이 완료되었습니다.\n"
                    "저장된 GitHub 로그인 정보가 삭제되었습니다.",
                )
                return
            # Unexpected error after logout click — still show it, token already cleared
            self._log(f"ERROR: {message}")

        self._log(f"ERROR: {message}")
        # G4 — one next-step line under the raw/Korean error
        next_line = format_next_step_line(message)
        if next_line:
            self._log(next_line)
        if message.startswith("취소"):
            QMessageBox.information(self.window, "취소됨", message)
            return

        # Missing repo scope — dedicated step-by-step help (beginners)
        if MISSING_REPO_MARKER in message and not self._busy():
            scopes = parse_scopes_from_missing_repo_message(message)
            if show_missing_repo_help(
                self.window, current_scopes=scopes, offer_reconnect=True
            ):
                self.on_login()
            return

        needs_login = (
            "연결이 필요" in message
            or "키를 붙여" in message
            or "키가 올바르지" in message
            or "만료되었" in message
        )
        body = message
        if next_line:
            body = f"{message}\n\n{next_line}"

        if needs_login and not self._busy():
            reply = QMessageBox.warning(
                self.window,
                "GitHub 연결 필요",
                body + "\n\n지금 키를 붙여 넣을까요?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Ok,
            )
            if reply == QMessageBox.StandardButton.Ok:
                self.on_login()
            return

        QMessageBox.critical(self.window, "실패", body)

    def _confirm_upload_g3(
        self,
        folder: Path,
        *,
        allow_secrets: bool,
        private: bool | None,
        hide_real_email: bool = True,
        title: str = "올리기 전 확인",
    ) -> bool:
        """
        G3 — plain-language preflight before commit/push.
        Secrets list + PII samples + commit email. Cancel = do not start worker.
        """
        parts: list[str] = []
        if private is True:
            vis_short = "비공개 저장소"
            vis_risk = (
                "비공개여도 나중에 공개로 바꾸거나, 권한이 있는 사람·유출 시 "
                "그대로 보일 수 있습니다."
            )
        elif private is False:
            vis_short = "공개 저장소"
            vis_risk = (
                "공개 저장소면 인터넷에 누구나 볼 수 있습니다. "
                "한 번 올라간 내용은 완전 삭제가 어렵습니다."
            )
        else:
            vis_short = "원격 저장소"
            vis_risk = "원격에 올라가면 권한 있는 사람(또는 공개 시 누구나)이 볼 수 있습니다."

        secrets = find_secret_candidates(folder)
        if secrets:
            listing = format_secret_list(secrets)
            if not allow_secrets:
                QMessageBox.warning(
                    self.window,
                    "올릴 수 없음 — 비밀 파일 후보",
                    "이름만 봐도 비밀번호·API 키가 들어 있을 수 있는 파일입니다.\n"
                    f"({vis_short})\n\n"
                    f"{listing}\n\n"
                    "다음 중 하나를 하세요:\n"
                    "  1) 폴더에서 해당 파일을 빼거나 이름 바꾸기\n"
                    "  2) 정말 올려도 되면 「비밀 파일로 보이는 항목이 있어도 진행」을 켠 뒤 "
                    "다시 시도\n\n"
                    "참고: .env.example 처럼 샘플만 있는 파일도 이름 때문에 잡힐 수 있습니다. "
                    "내용이 안전한지 확인한 뒤에만 2)를 쓰세요.",
                )
                self._log(
                    "다음: 비밀 파일 후보를 제거·이름 변경하거나, "
                    "확인 후 「비밀 파일… 진행」 체크"
                )
                return False
            parts.append(
                "【비밀 파일 후보 — 체크를 켠 상태】\n"
                f"{listing}\n\n"
                f"{vis_risk}\n"
                "오탐일 수 있습니다(예: 빈 .env.example). "
                "내용에 실제 비밀번호가 없는지 스스로 확인하세요."
            )

        # Content PII (phone/email) — Command-to-commit-changes-from-Git patterns
        pii_hits = scan_pii_in_contents(folder)
        if pii_hits:
            listing = format_pii_list(pii_hits)
            parts.append(
                "【개인정보로 보이는 값 — 파일 내용】\n"
                f"{listing}\n\n"
                "전화·이메일 형태의 글자를 찾았습니다. "
                f"{vis_risk}\n"
                "오탐일 수 있습니다(예: 문서 속 예시 번호, 버전처럼 보이는 숫자). "
                "실제 개인정보면 올리기 전에 지우거나 가리세요."
            )

        email = preview_commit_email(
            folder, None, hide_real_email=hide_real_email
        )
        parts.append(
            _format_commit_email_g3(
                email, private=private, hide_real_email=hide_real_email
            )
        )

        if not secrets and not pii_hits:
            # Clean path: short confirm
            body = (
                f"{vis_short}로 올립니다.\n"
                f"{vis_risk}\n\n"
                + "\n".join(parts)
                + "\n\n계속할까요?"
            )
        else:
            body = (
                f"{vis_short} — 올리기 전 확인\n\n"
                + "\n\n".join(parts)
                + "\n\n계속할까요?"
            )

        reply = QMessageBox.warning(
            self.window,
            title,
            body,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            self._log("올리기 전 확인 — 사용자가 취소")
            return False
        return True

    @Slot()
    def on_publish(self) -> None:
        if self._busy() or not self.editFolder or not self.editRepoName:
            return
        folder = (self.editFolder.text() or "").strip()
        name = (self.editRepoName.text() or "").strip()
        msg = (
            (self.editCommitMessage.text() if self.editCommitMessage else None)
            or "첫 업로드"
        ).strip()
        allow = bool(self.checkAllowSecrets and self.checkAllowSecrets.isChecked())
        private = bool(self.radioPrivate and self.radioPrivate.isChecked())
        hide_email = bool(
            self.checkHideEmail is None or self.checkHideEmail.isChecked()
        )

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
                    path.resolve(),
                    allow_secrets=False,
                    private=private,
                    hide_real_email=hide_email,
                )
                return
            QMessageBox.warning(self.window, "올릴 수 없음", "\n".join(report.errors))
            return

        if not self._confirm_upload_g3(
            path.resolve(),
            allow_secrets=allow,
            private=private,
            hide_real_email=hide_email,
        ):
            self._log("Publish 취소 — 확인 대화상자")
            return

        remember_folder(str(path.resolve()))
        self._reload_recent_combo()
        save_last_private(private)
        save_last_commit_message(msg)
        save_hide_real_email(hide_email)

        self._log(f"--- Publish: {name} ({'private' if private else 'public'}) ---")
        w = PublishWorker(
            folder=str(path.resolve()),
            repo_name=name,
            commit_message=msg,
            private=private,
            allow_secrets=allow,
            hide_real_email=hide_email,
            parent=self,
        )
        w.succeeded.connect(self._on_publish_ok)
        w.failed.connect(self._on_fail_msg)
        self._start_worker(w)

    def _go_sync_tab(self, folder: str | None = None) -> None:
        """Fill Sync folder field and switch to the Sync tab (V5 next step)."""
        if folder and self.editSyncFolder is not None:
            self.editSyncFolder.setText(str(folder))
        if self.tabWidget is not None:
            # tab order in main_window.ui: 0 publish, 1 clone, 2 sync
            for i in range(self.tabWidget.count()):
                w = self.tabWidget.widget(i)
                if w is not None and w.objectName() == "tabSync":
                    self.tabWidget.setCurrentIndex(i)
                    break
            else:
                if self.tabWidget.count() >= 3:
                    self.tabWidget.setCurrentIndex(2)
        self._log("다음: 동기화 탭 — 이 폴더를 더 고친 뒤 「올리고 보내기」")

    @Slot(dict)
    def _on_publish_ok(self, result: dict) -> None:
        self._close_device_overlay()
        url = result.get("html_url") or ""
        folder = str(result.get("folder") or "")
        full_name = str(result.get("full_name") or "")
        private = bool(result.get("private"))
        self._log(f"Publish 성공: {url or full_name}")
        # Pre-fill Sync so 「동기화 탭으로」 is one click.
        if self.editSyncFolder is not None and folder:
            self.editSyncFolder.setText(folder)

        steps = show_publish_success(
            self.window,
            full_name=full_name,
            html_url=url,
            folder=folder,
            private=private,
        )
        if steps.open_browser:
            self._log(f"브라우저 열기: {url}")
        if steps.url_copied:
            self._log("저장소 주소 복사됨")
        if steps.go_sync and folder:
            self._go_sync_tab(folder)

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
        path = str(result.get("path") or "")
        owner = result.get("owner") or ""
        repo = result.get("repo") or ""
        owner_repo = f"{owner}/{repo}".strip("/")
        clone_url = str(result.get("clone_url") or "")
        # HTTPS clone URL → browse URL when possible
        html_url = ""
        if clone_url.endswith(".git"):
            html_url = clone_url[:-4]
        elif clone_url.startswith("https://github.com/"):
            html_url = clone_url

        self._log(f"Clone 성공: {path}")
        if path:
            remember_folder(path)
            self._reload_recent_combo()
        if self.editSyncFolder is not None and path:
            self.editSyncFolder.setText(path)

        steps = show_clone_success(
            self.window,
            owner_repo=owner_repo or "저장소",
            path=path,
            html_url=html_url,
        )
        if steps.open_browser and html_url:
            self._log(f"브라우저 열기: {html_url}")
        if steps.go_sync and path:
            self._go_sync_tab(path)

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
            (self.editSyncMessage.text() if self.editSyncMessage else None)
            or "변경 사항 반영"
        ).strip()
        allow = bool(
            self.checkSyncAllowSecrets and self.checkSyncAllowSecrets.isChecked()
        )
        hide_email = bool(
            self.checkSyncHideEmail is None or self.checkSyncHideEmail.isChecked()
        )

        if action == "abort":
            ans = QMessageBox.question(
                self.window,
                "충돌 취소",
                "서로 다른 변경이 겹친 상태를 되돌릴까요?\n"
                "(저장소가 충돌 직전 상태로 돌아갑니다.)",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        if action == "pull":
            ans = QMessageBox.question(
                self.window,
                "받아오기",
                "GitHub에 있는 최신 내용을 이 폴더로 가져옵니다.\n"
                "겹치는 변경이 있으면 이 앱에서는 자동으로 합치지 않습니다. 계속할까요?",
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
                    hide_real_email=hide_email,
                    title="올리고 보내기 전 확인",
                ):
                    self._log("Sync push 취소 — 확인 대화상자")
                    return
            save_hide_real_email(hide_email)

        self._log(f"--- Sync {action}: {folder} ---")
        w = SyncActionWorker(
            action=action,
            folder=folder.strip(),
            message=msg,
            allow_secrets=allow,
            hide_real_email=hide_email,
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
