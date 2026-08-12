"""Main window — Publish / Clone / Sync tabs."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QFile,
    QObject,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QKeySequence,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.git.publish import preview_commit_email
from app.git.runner import GitError, require_git, run_git
from app.git.safety import (
    find_secret_candidates,
    format_content_secret_list,
    format_pii_list,
    format_secret_list,
    run_safety_checks,
    scan_pii_in_contents,
    scan_secret_in_contents,
)
from app.git.url_utils import UrlError, normalize_github_clone_url
from app.auth.token_store import delete_token, is_logged_in, load_token
from app.paths import app_root
from app.ui.auth_status import AuthState, AuthStatusButton
from app.ui.device_code_dialog import DeviceCodeOverlay
from app.auth.session import MISSING_REPO_MARKER
from app.ui.login_dialog import (
    ConnectGitHubWizard,
    parse_scopes_from_missing_repo_message,
    show_missing_repo_help,
    show_missing_workflow_scope_help,
)
from app.ui.publish_worker import LoginWorker, PatLoginWorker, PublishWorker
from app.ui.commit_history_dialog import (
    show_commit_history,
    show_remote_commit_history,
)
from app.ui.settings_dialog import show_settings
from app.ui.success_dialog import show_clone_success, show_publish_success
from app.ui.tip_card import install_tip_card
from app.util.next_action import format_next_step_line, is_missing_workflow_scope_error
from app.ui.onboarding_dialog import show_onboarding
from app.ui.settings_store import (
    load_hide_real_email,
    load_last_commit_message,
    load_last_private,
    load_last_publish_branch,
    load_onboarding_done,
    load_recent_folders,
    load_secret_pii_scan_enabled,
    remember_folder,
    save_hide_real_email,
    save_last_commit_message,
    save_last_private,
    save_last_publish_branch,
    save_onboarding_done,
)
from app.ui.tab_workers import CloneWorker, SyncActionWorker, SyncStatusWorker
from app.ui.theme import active_palette


class _CloneRepoListWorker(QThread):
    """Load GitHub /user/repos off the UI thread (module-level for reliable Signals)."""

    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(self, token: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._token = token

    def run(self) -> None:  # noqa: N802
        try:
            from app.github.api_client import list_user_repos

            rows = list_user_repos(self._token)
            self.succeeded.emit(list(rows or []))
        except Exception as e:
            self.failed.emit(str(e))


def _ui_path() -> Path:
    return app_root() / "ui" / "main_window.ui"


# comboPublishBranch's last item — not a real branch name, picking it just
# clears the field so beginners discover they can type a custom branch.
_PUBLISH_BRANCH_CUSTOM_HINT = "사용자 지정…"


def _folder_path(edit: QLineEdit | None) -> str:
    """Full folder path from a path line edit (always the real text, no elide)."""
    if edit is None:
        return ""
    return (edit.text() or "").strip()


def _set_folder_path(edit: QLineEdit | None, path: str) -> None:
    """Show the complete path in the field; tooltip mirrors it for hover copy."""
    if edit is None:
        return
    path = (path or "").strip()
    edit.setText(path)
    if path:
        edit.setToolTip(path)
    # Keep caret at start so drive/root is visible; user can scroll for the rest.
    edit.setCursorPosition(0)


class _RecentFolderPopup(QFrame):
    """Frameless, non-activating recent-folder dropdown.

    Deliberately NOT a native combo/completer popup (those use the
    Qt::Popup window flag and grab the mouse): while one is open, a click on
    another widget just closes it without also reaching that widget, so you
    need a second click to actually act on it. This widget never grabs
    input — MainController's application-wide event filter hides it on an
    outside click instead, so the very same click still reaches whatever is
    underneath.
    """

    picked = Signal(str)

    def __init__(self, owner: QWidget | None = None) -> None:
        # `owner` (the main window) keeps this floating above it via normal
        # Tool-window stacking, without reparenting it into that window.
        super().__init__(
            owner,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list = QListWidget(self)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._list)

    def set_items(self, items: list[str]) -> None:
        self._list.clear()
        self._list.addItems(items)

    def items(self) -> list[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]

    def popup_below(self, edit: QLineEdit) -> None:
        if self._list.count() == 0:
            self.hide()
            return
        from app.ui.theme import active_palette

        p = active_palette()
        self._list.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {p.bg_input};
                color: {p.text};
                border: none;
                outline: 0;
            }}
            QListWidget::item {{
                padding: 6px 10px;
            }}
            QListWidget::item:selected, QListWidget::item:hover {{
                background-color: {p.primary};
                color: {p.text_on_primary};
            }}
            """
        )
        self.setStyleSheet(
            f"_RecentFolderPopup {{ background-color: {p.bg_input};"
            f" border: 1px solid {p.border_input}; }}"
        )
        width = max(edit.width(), 200)
        # +4px: sizeHintForRow() can undercount the QSS item padding above,
        # since a stylesheet's polish pass doesn't always land before this
        # call — a small buffer avoids an unwanted scrollbar for it.
        row_h = (self._list.sizeHintForRow(0) or 28) + 4
        height = min(row_h * self._list.count(), row_h * 8) + 8
        pos = edit.mapToGlobal(edit.rect().bottomLeft())
        self.setGeometry(pos.x(), pos.y() + 2, width, height)
        self.show()
        self.raise_()

    def _on_item_clicked(self, item) -> None:
        text = item.text()
        self.hide()
        self.picked.emit(text)


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
        wrap.resize(760, 700)
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
        # F11: toggle fullscreen from any of the 3 tabs (만들고 올리기/받기/동기화).
        # QShortcut (not a keyPressEvent override) so it fires no matter which
        # child control has focus — see docs/UX_GUIDANCE.md "키보드 단축키".
        QShortcut(
            QKeySequence(Qt.Key.Key_F11), self.window, activated=self._toggle_fullscreen
        )

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
        self.btnSettings = window.findChild(QPushButton, "btnSettings")
        self.btnHelpOnboarding = window.findChild(QPushButton, "btnHelpOnboarding")

        # D2 — recolor status-row widgets when OS light/dark flips
        # (inline setStyleSheet overrides global QSS and would stay light)
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.styleHints().colorSchemeChanged.connect(
                    self._on_color_scheme_changed
                )
                # App-wide: lets us hide the recent-folder popups (below) on
                # any outside click without grabbing/eating that click.
                app.installEventFilter(self)
        except Exception:
            pass

        # --- publish ---
        self.editFolder = window.findChild(QLineEdit, "editFolder")
        self.btnBrowseFolder = window.findChild(QPushButton, "btnBrowseFolder")
        self._last_recent_dropdown_hide_at = 0.0
        self._recentPopupPublish = self._install_recent_dropdown(
            self.editFolder, self._on_recent_picked
        )
        self.editRepoName = window.findChild(QLineEdit, "editRepoName")
        self.radioPublic = window.findChild(QRadioButton, "radioPublic")
        self.radioPrivate = window.findChild(QRadioButton, "radioPrivate")
        self.comboPublishBranch = window.findChild(QComboBox, "comboPublishBranch")
        self.editCommitMessage = window.findChild(QLineEdit, "editCommitMessage")
        self.checkHideEmail = window.findChild(QCheckBox, "checkHideEmail")
        self.checkAllowSecrets = window.findChild(QCheckBox, "checkAllowSecrets")
        self.btnPublish = window.findChild(QPushButton, "btnPublish")
        if self.comboPublishBranch is not None:
            # Allow picking common names or typing a custom branch
            self.comboPublishBranch.setEditable(True)
            self.comboPublishBranch.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        # --- clone ---
        # Editable combo: type/paste URL, or pick from GitHub list when logged in
        self.comboCloneUrl = window.findChild(QComboBox, "comboCloneUrl")
        # Back-compat alias used in older call sites / docs
        self.editCloneUrl = self.comboCloneUrl
        self.btnCloneRepoList = window.findChild(QPushButton, "btnCloneRepoList")
        self.labelCloneHint = window.findChild(QLabel, "labelCloneHint")
        self.comboCloneBranch = window.findChild(QComboBox, "comboCloneBranch")
        self.editCloneParent = window.findChild(QLineEdit, "editCloneParent")
        self.btnCloneBrowseParent = window.findChild(QPushButton, "btnCloneBrowseParent")
        self.editCloneDirName = window.findChild(QLineEdit, "editCloneDirName")
        self.checkCloneUseToken = window.findChild(QCheckBox, "checkCloneUseToken")
        self.btnClone = window.findChild(QPushButton, "btnClone")
        self.btnCloneHistory = window.findChild(QPushButton, "btnCloneHistory")
        self.btnCloneCancel = window.findChild(QPushButton, "btnCloneCancel")
        # List-only selection (no free typing) — real names + (notes)
        if self.comboCloneBranch is not None:
            self.comboCloneBranch.setEditable(False)
            self.comboCloneBranch.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        if self.comboCloneUrl is not None:
            self.comboCloneUrl.setEditable(True)
            self.comboCloneUrl.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            self.comboCloneUrl.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            # Native arrow hidden in theme; list opens via btnCloneRepoList
        self._clone_url_timer = QTimer(self)
        self._clone_url_timer.setSingleShot(True)
        self._clone_url_timer.setInterval(350)
        self._clone_url_timer.timeout.connect(self._normalize_clone_url_field)
        # Track last owner/repo so folder name resets when URL changes to another repo
        self._last_clone_repo_key: str | None = None
        self._clone_repos_worker: QThread | None = None
        self._clone_repos_loaded_for: str | None = None  # token fingerprint / "none"
        self._clone_url_logged_in_mode: bool | None = None
        # Publish: folder path that last auto-filled editRepoName (so re-pick updates name)
        self._publish_folder_for_repo_name: str | None = None

        # --- sync ---
        self.editSyncFolder = window.findChild(QLineEdit, "editSyncFolder")
        self._recentPopupSync = self._install_recent_dropdown(
            self.editSyncFolder, self._on_sync_recent_picked
        )
        self.btnSyncBrowse = window.findChild(QPushButton, "btnSyncBrowse")
        self.btnSyncRefresh = window.findChild(QPushButton, "btnSyncRefresh")
        self.btnSyncHistory = window.findChild(QPushButton, "btnSyncHistory")
        self.labelSyncBranchTitle = window.findChild(QLabel, "labelSyncBranchTitle")
        self.labelSyncBranch = window.findChild(QLabel, "labelSyncBranch")
        if self.labelSyncBranch is not None:
            # Badge width follows text — do not stretch across the row
            self.labelSyncBranch.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
            )
            self.labelSyncBranch.setAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
        self.labelSyncStatus = window.findChild(QLabel, "labelSyncStatus")
        self.labelSyncStatusTitle = window.findChild(QLabel, "labelSyncStatusTitle")
        self.frameSyncStatus = window.findChild(QFrame, "frameSyncStatus")
        self._sync_chips_layout: QHBoxLayout | None = None
        # Chips layout is the direct layout of frameSyncStatus
        if self.frameSyncStatus is not None:
            lay = self.frameSyncStatus.layout()
            if isinstance(lay, QHBoxLayout):
                self._sync_chips_layout = lay
            elif lay is not None and lay.objectName() == "syncStatusChipsLayout":
                self._sync_chips_layout = lay  # type: ignore[assignment]
        self.editSyncMessage = window.findChild(QLineEdit, "editSyncMessage")
        self.checkSyncHideEmail = window.findChild(QCheckBox, "checkSyncHideEmail")
        self.checkSyncAllowSecrets = window.findChild(QCheckBox, "checkSyncAllowSecrets")
        self.btnSyncPull = window.findChild(QPushButton, "btnSyncPull")
        self.btnSyncPush = window.findChild(QPushButton, "btnSyncPush")
        self.btnSyncAbort = window.findChild(QPushButton, "btnSyncAbort")
        self.btnSyncCancel = window.findChild(QPushButton, "btnSyncCancel")
        # Debounce path paste/type → auto status refresh (2)
        self._sync_folder_timer = QTimer(self)
        self._sync_folder_timer.setSingleShot(True)
        self._sync_folder_timer.setInterval(400)
        self._sync_folder_timer.timeout.connect(self._sync_folder_maybe_refresh)

        if self.textLog is None or self.btnPublish is None:
            raise RuntimeError("필수 UI 위젯 누락")

        self._install_tab_tip_cards()
        self._wire()
        self._load_prefs()
        self._refresh_status_bar()
        self._log("CloneUp — 만들고 올리기 / 받기 / 동기화 탭 사용 가능")
        # Apply 받기 URL mode (list vs plain input) after paint
        QTimer.singleShot(0, self._sync_clone_url_login_mode)
        # First-run onboarding → then DG1 Git check / token age (after paint)
        QTimer.singleShot(0, self._startup_after_show)

    def _startup_after_show(self) -> None:
        """Onboarding (once) then Git bootstrap and soft token age hint."""
        if not load_onboarding_done():
            self._log("첫 실행 안내 표시")
            if show_onboarding(self.window):
                save_onboarding_done(True)
                self._log("첫 실행 안내 완료")
            else:
                # Esc / close without 시작하기 — still mark done so we don't trap
                save_onboarding_done(True)
                self._log("첫 실행 안내 닫음")
        self._ensure_git_bootstrap()
        self._log_token_age_hint()

    def _ensure_git_bootstrap(self) -> None:
        """Plan D / DG1: if Git missing, full-window simple install chooser."""
        from app.git.bootstrap import force_git_setup_ui, probe_git
        from app.ui.git_setup import ensure_git_or_offer_setup

        # Git installed → skip, unless CLONEUP_FORCE_NO_GIT=1 (UI test)
        if probe_git().ok and not force_git_setup_ui():
            return
        ensure_git_or_offer_setup(self.window, log=self._log)
        self._refresh_status_bar()

    @Slot()
    def on_help_onboarding(self) -> None:
        """Re-open first-run guide (시안: 도움말)."""
        if self._busy():
            return
        self._log("도움말 — 시작 안내")
        show_onboarding(self.window)

    @Slot()
    def on_settings_menu(self) -> None:
        """Open 설정 dialog (시안: desin/CloneUp 설정.dc.html)."""
        if self._busy():
            return
        self._log("설정 열기")
        show_settings(
            self.window,
            on_login=self.on_login,
            on_logout=self.on_logout,
            on_prefs_changed=self._on_settings_prefs_changed,
            on_open_onboarding=self.on_help_onboarding,
        )
        # Settings may live-refresh scopes or clear a 401 token; status row
        # only reads keyring — re-paint after the dialog closes.
        self._refresh_status_bar()

    def _on_settings_prefs_changed(self, what: str = "all") -> None:
        """
        Push settings-store values into main tabs after 설정 auto-save.

        *what* limits which widgets update so toggling 안전 does not wipe
        an in-progress commit message on 만들고 올리기.
        """
        self._apply_settings_store_to_tabs(what)

    def _apply_settings_store_to_tabs(self, what: str = "all") -> None:
        """Selective settings → tab sync. Startup uses ``_load_prefs`` (full)."""
        w = (what or "all").strip().lower() or "all"

        if w in ("all", "defaults", "private", "visibility"):
            if load_last_private() and self.radioPrivate is not None:
                self.radioPrivate.setChecked(True)
            elif self.radioPublic is not None:
                self.radioPublic.setChecked(True)

        if w in ("all", "defaults", "message", "commit_message"):
            if self.editCommitMessage is not None:
                self.editCommitMessage.setText(load_last_commit_message())

        if w in ("all", "defaults", "branch", "publish_branch"):
            if self.comboPublishBranch is not None:
                br = load_last_publish_branch()
                idx = self.comboPublishBranch.findText(br)
                if idx >= 0:
                    self.comboPublishBranch.setCurrentIndex(idx)
                else:
                    self.comboPublishBranch.setEditText(br)

        if w in ("all", "safety", "hide_email", "email"):
            hide = load_hide_real_email()
            if self.checkHideEmail is not None:
                self.checkHideEmail.setChecked(hide)
            if self.checkSyncHideEmail is not None:
                self.checkSyncHideEmail.setChecked(hide)

        if w in ("all", "folders", "recent"):
            self._reload_recent_combo()

        # secret_scan: no tab widget; read live via load_secret_pii_scan_enabled()
        # history_revert: no tab widget either — CommitHistoryDialog reads
        # load_history_revert_enabled() itself, fresh, every time it opens
        # (동기화/받기 tabs both go through it), so there's nothing to push here.

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
                "• 왜: 작업 폴더 내용을 커밋(로컬 기록)한 뒤 GitHub(원격)로 보냅니다. "
                "커밋 전 파일은 밖에 안 갑니다.\n"
                "• 먼저 위쪽 「GitHub: 연결」에서 키를 연결하세요.\n"
                "• branch 는 보통 main 입니다. 필요하면 목록에서 고르거나 직접 입력하세요.\n"
                "• 「커밋에 내 이메일 숨기기」를 켜 두면 학교·회사 메일이 안 남습니다.\n"
                "• 공개 저장소는 누구나 볼 수 있고, 한 번 올라간 내용은 거두기 어렵습니다.\n"
                "• .env 같은 비밀 파일 후보는 기본적으로 올리지 않습니다.",
            ),
            (
                "labelTabIntroClone",
                "GitHub에 있는 폴더를 내 컴퓨터로 복사합니다.",
                "• 왜: GitHub(원격) 기록을 이 PC 작업 폴더로 가져와, 고치고 다시 맞출 준비를 합니다.\n"
                "• 주소를 붙여 넣거나, GitHub 연결 후 「목록 ▼」에서 내 저장소를 고를 수 있습니다.\n"
                "• 같은 이름의 폴더가 이미 있으면 실패합니다. 이름을 바꾸세요.\n"
                "• 비공개 저장소는 「비공개 저장소 받을 때 GitHub 연결 사용」을 켠 뒤 연결하세요.\n"
                "• 「커밋 내역」으로 주소의 GitHub 커밋을 볼 수 있습니다. "
                "공개 저장소는 로그인 없이도 됩니다.",
            ),
            (
                "labelTabIntroSync",
                "이미 연결된 폴더의 변경사항을 주고받습니다.",
                "• 왜: 로컬 커밋과 GitHub를 맞춥니다(자동 드라이브 동기화 아님). "
                "상태의 보낼/받을 커밋을 보세요.\n"
                "• 이 폴더에 .git 이 있어야 합니다. 없으면 「받기」나 「만들고 올리기」를 먼저 하세요.\n"
                "• 「커밋 내역」은 지난 시점 보기·(설정 시) 되돌리기입니다. "
                "「충돌 취소」는 합치기 중 겹침을 포기하는 비상 버튼입니다.\n"
                "• 왼쪽 branch / 상태에 이 폴더 정보가 나란히 보입니다.\n"
                "• 폴더를 고르거나 경로를 붙이면 상태가 자동으로 다시 읽힙니다.\n"
                "• 올리기 전에 비밀 파일 후보가 있는지 확인하세요.",
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
            self.editFolder,
            self.editRepoName,
            self.comboPublishBranch,
            self.editCommitMessage,
            self.radioPublic,
            self.radioPrivate,
            self.checkHideEmail,
            self.checkAllowSecrets,
        ):  # path fields stay enabled via same list
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
            self.btnCloneHistory,
            self.btnCloneBrowseParent,
            self.btnCloneRepoList,
            self.comboCloneUrl,
            self.comboCloneBranch,
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
            self.btnSyncHistory,
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
        try:
            return self._event_filter_impl(obj, event)
        except Exception:
            # Installed app-wide (for the recent-folder popups' outside-click
            # detection), so this can be reached for objects torn down by
            # someone else entirely — e.g. in tests that create/close their
            # own window while this filter is still registered. A dead C++
            # object here is a teardown race, not a real error to surface.
            return False

    def _event_filter_impl(self, obj, event) -> bool:
        et = event.type()
        if obj is self.window and et == QEvent.Type.Close:
            if not getattr(self, "_closing", False):
                self._closing = True
                self._shutdown_workers()
                self._close_device_overlay()
                self._detach_app_event_filter()
        elif obj is self.window and et in (
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
        ):
            # Maximize / restore: keep device-code dim covering full client area
            if self._device_overlay is not None:
                self._device_overlay.sync_geometry()
        elif obj in (self.editFolder, self.editSyncFolder) and et in (
            QEvent.Type.FocusIn,
            QEvent.Type.MouseButtonPress,
        ):
            self._show_recent_dropdown(obj)
        elif et == QEvent.Type.MouseButtonPress:
            # App-wide: close recent-folder popups on an outside click.
            # These popups don't grab the mouse, so this never blocks the
            # click from also reaching whatever widget is underneath it.
            self._maybe_hide_recent_dropdowns(event)
        return False

    def _detach_app_event_filter(self) -> None:
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
        except Exception:
            pass

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
        # 받기 탭: 로그아웃 → URL 입력 전용 모드
        self._clone_repos_loaded_for = None
        self._sync_clone_url_login_mode(force=True)

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
        if self.btnSettings is not None:
            self.btnSettings.clicked.connect(self.on_settings_menu)
        if self.btnHelpOnboarding is not None:
            self.btnHelpOnboarding.clicked.connect(self.on_help_onboarding)
        if self.editFolder:
            self.editFolder.editingFinished.connect(self._maybe_fill_repo_name)
        if self.comboPublishBranch is not None:
            self.comboPublishBranch.activated.connect(
                self._on_publish_branch_activated
            )

        if self.btnCloneBrowseParent:
            self.btnCloneBrowseParent.clicked.connect(self.on_clone_browse_parent)
        if self.btnClone:
            self.btnClone.clicked.connect(self.on_clone)
        if self.btnCloneHistory is not None:
            self.btnCloneHistory.clicked.connect(self.on_clone_history)
        if self.btnCloneCancel:
            self.btnCloneCancel.clicked.connect(self.on_cancel)
        if self.comboCloneUrl is not None:
            le = self.comboCloneUrl.lineEdit()
            if le is not None:
                le.editingFinished.connect(self._normalize_clone_url_field)
                le.textChanged.connect(self._on_clone_url_text_changed)
            self.comboCloneUrl.activated.connect(self._on_clone_url_activated)
        if self.btnCloneRepoList is not None:
            self.btnCloneRepoList.clicked.connect(self._on_clone_repo_list_clicked)
        if self.tabWidget is not None:
            self.tabWidget.currentChanged.connect(self._on_tab_changed)

        if self.btnSyncBrowse:
            self.btnSyncBrowse.clicked.connect(self.on_sync_browse)
        if self.btnSyncRefresh:
            self.btnSyncRefresh.clicked.connect(self.on_sync_refresh)
        if self.btnSyncHistory is not None:
            self.btnSyncHistory.clicked.connect(self.on_sync_history)
        if self.editSyncFolder is not None:
            self.editSyncFolder.editingFinished.connect(
                self._on_sync_folder_editing_finished
            )
            self.editSyncFolder.textChanged.connect(self._on_sync_folder_text_changed)
        if self.btnSyncPull:
            self.btnSyncPull.clicked.connect(lambda: self.on_sync_action("pull"))
        if self.btnSyncPush:
            self.btnSyncPush.clicked.connect(lambda: self.on_sync_action("push"))
        if self.btnSyncAbort:
            self.btnSyncAbort.clicked.connect(lambda: self.on_sync_action("abort"))
        if self.btnSyncCancel:
            self.btnSyncCancel.clicked.connect(self.on_cancel)

    def _load_prefs(self) -> None:
        """Startup (and full) load: settings store → all related tab fields."""
        self._apply_settings_store_to_tabs("all")
        # First-run convenience only (not on every settings live-save)
        recent = load_recent_folders()
        if recent and self.editFolder is not None and not _folder_path(self.editFolder):
            for p in recent:
                if Path(p).is_dir():
                    _set_folder_path(self.editFolder, p)
                    self._maybe_fill_repo_name()
                    break
        if self.editCloneParent is not None and not self.editCloneParent.text():
            self.editCloneParent.setText(str(Path.home() / "Desktop"))

    def _publish_branch_name(self) -> str:
        """Current branch field value for first publish (default main)."""
        if self.comboPublishBranch is None:
            return "main"
        text = (self.comboPublishBranch.currentText() or "").strip()
        if not text or text == _PUBLISH_BRANCH_CUSTOM_HINT:
            return "main"
        return text

    @Slot(int)
    def _on_publish_branch_activated(self, index: int) -> None:
        """Picking the "사용자 지정…" hint clears the field for free typing."""
        if self.comboPublishBranch is None:
            return
        if self.comboPublishBranch.itemText(index) != _PUBLISH_BRANCH_CUSTOM_HINT:
            return
        self.comboPublishBranch.setEditText("")
        le = self.comboPublishBranch.lineEdit()
        if le is not None:
            le.setFocus()

    def _reload_recent_combo(self) -> None:
        """Refresh both folder fields' recent-folder dropdown popups."""
        items = load_recent_folders()
        if self._recentPopupPublish is not None:
            self._recentPopupPublish.set_items(items)
        if self._recentPopupSync is not None:
            self._recentPopupSync.set_items(items)

    @Slot()
    def _toggle_fullscreen(self) -> None:
        """F11: plain top-level QMainWindow, so showNormal() restores the
        exact pre-fullscreen geometry itself — no Frameless-flag dance
        needed here (that workaround is only for the Dialog-flagged popups
        in commit_history_dialog.py / onboarding_dialog.py)."""
        if self.window.isFullScreen():
            self.window.showNormal()
        else:
            self.window.showFullScreen()

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
        self._sync_clone_url_login_mode()

    def _update_logout_button(self) -> None:
        """Show 로그아웃 only when a GitHub session is stored."""
        if self.btnLogout is None:
            return
        logged_in = is_logged_in()
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
        """
        Sync repo name with the local folder basename.

        - Empty repo name → fill from folder.
        - Repo name still equals the *previous* auto folder basename → update
          (user picked another folder; do not leave the old name stuck).
        - User typed a custom repo name → leave it alone.
        """
        if not self.editFolder or not self.editRepoName:
            return
        folder = _folder_path(self.editFolder)
        if not folder:
            return
        try:
            new_base = Path(folder).expanduser().resolve().name
        except OSError:
            new_base = Path(folder).name
        if not new_base:
            return

        cur = (self.editRepoName.text() or "").strip()
        prev = self._publish_folder_for_repo_name
        prev_base = Path(prev).name if prev else None

        if not cur or (prev_base is not None and cur == prev_base):
            self.editRepoName.setText(new_base)
            self._publish_folder_for_repo_name = folder

    def _install_recent_dropdown(
        self, edit: QLineEdit | None, on_pick
    ) -> _RecentFolderPopup | None:
        """Attach a recent-folder dropdown to `edit` that shows the full list
        on focus/click, regardless of current text."""
        if edit is None:
            return None
        popup = _RecentFolderPopup(self.window)
        popup.picked.connect(on_pick)
        edit.installEventFilter(self)
        return popup

    def _recent_popup_for(self, edit: QLineEdit) -> _RecentFolderPopup | None:
        if edit is self.editFolder:
            return self._recentPopupPublish
        if edit is self.editSyncFolder:
            return self._recentPopupSync
        return None

    def _show_recent_dropdown(self, edit: QLineEdit) -> None:
        # Hiding one of these popups (a Tool window) makes Windows queue a
        # spurious FocusIn back onto `edit` shortly after — without this
        # debounce that immediately reopens the very popup we just closed
        # (e.g. right after picking an item, or on an outside click).
        if time.monotonic() - self._last_recent_dropdown_hide_at < 0.3:
            return
        popup = self._recent_popup_for(edit)
        if popup is not None:
            popup.popup_below(edit)

    def _note_recent_dropdown_hidden(self) -> None:
        self._last_recent_dropdown_hide_at = time.monotonic()

    def _maybe_hide_recent_dropdowns(self, event) -> None:
        try:
            pos = event.globalPosition().toPoint()
        except AttributeError:
            pos = event.globalPos()
        for popup, edit in (
            (self._recentPopupPublish, self.editFolder),
            (self._recentPopupSync, self.editSyncFolder),
        ):
            if popup is None or not popup.isVisible():
                continue
            if popup.geometry().contains(pos):
                continue  # click on a row — its own itemClicked handles it
            if edit is not None and edit.rect().contains(edit.mapFromGlobal(pos)):
                continue  # click on the originating field itself
            popup.hide()
            self._note_recent_dropdown_hidden()

    @Slot(str)
    def _on_recent_picked(self, path: str) -> None:
        self._note_recent_dropdown_hidden()
        if not path or not self.editFolder:
            return
        _set_folder_path(self.editFolder, path)
        self._log(f"최근 폴더: {path}")
        self._maybe_fill_repo_name()

    @Slot(str)
    def _on_sync_recent_picked(self, path: str) -> None:
        self._note_recent_dropdown_hidden()
        if not path or self.editSyncFolder is None:
            return
        _set_folder_path(self.editSyncFolder, path)
        remember_folder(path)
        self._reload_recent_combo()
        self._log(f"최근 폴더(동기화): {path}")
        self.on_sync_refresh(quiet=True)

    @Slot()
    def on_browse_folder(self) -> None:
        if not self.editFolder:
            return
        start = _folder_path(self.editFolder) or str(Path.home())
        path = QFileDialog.getExistingDirectory(self.window, "올릴 폴더 선택", start)
        if path:
            _set_folder_path(self.editFolder, path)
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
        # 받기 탭: 로그인 → 내 저장소 목록 모드
        self._clone_repos_loaded_for = None
        self._sync_clone_url_login_mode(force=True)
        QMessageBox.information(
            self.window,
            "연결 완료",
            f"{login} 님, 연결되었습니다.\n"
            "만료일이 지나면 「GitHub: 연결」으로 새 키를 넣으세요.\n"
            "「받기」탭에서 내 저장소 목록을 고를 수 있습니다.",
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

        # Push rejected: repo has .github/workflows/* but the PAT lacks
        # `workflow`. Reactive-only dedicated help (see next_action.py) —
        # this repo has just proven it needs the scope, unlike the default
        # connect flow which stays `repo`-only.
        if is_missing_workflow_scope_error(message) and not self._busy():
            if show_missing_workflow_scope_help(self.window, offer_reconnect=True):
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

    def _safety_scan_enabled(self) -> bool:
        """Settings → 안전 → 비밀·개인정보 점검 (default on)."""
        return load_secret_pii_scan_enabled()

    def _effective_allow_secrets(self, ui_allow: bool) -> bool:
        """
        Soft filename/content checks bypassed when global scan is off,
        or when the per-action 「비밀 파일도 진행」 box is checked.
        Hard content secrets still always block in G3 / run_safety_checks.
        """
        if not self._safety_scan_enabled():
            return True
        return bool(ui_allow)

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
        scan_on = self._safety_scan_enabled()
        # When global scan is off, treat soft checks as allowed
        allow_secrets = bool(allow_secrets) or (not scan_on)
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

        secrets: list = []
        content_secrets: list = []
        soft_content: list = []
        pii_hits: list = []
        if scan_on:
            secrets = find_secret_candidates(folder)
            content_secrets = scan_secret_in_contents(folder)
        else:
            # Still scan high-confidence content secrets (never fully bypassable)
            content_secrets = scan_secret_in_contents(folder)

        # High-confidence content keys are never bypassable (H1 review).
        hard_kinds = {
            "github_token",
            "aws_access_key",
            "private_key",
            "stripe_key",
            "slack_token",
        }
        hard_content = [h for h in content_secrets if h.kind in hard_kinds]
        soft_content = (
            [h for h in content_secrets if h.kind not in hard_kinds] if scan_on else []
        )
        if hard_content:
            listing = format_content_secret_list(hard_content)
            QMessageBox.warning(
                self.window,
                "올릴 수 없음",
                "파일 내용에 비밀 키처럼 보이는 값이 있어 막을 수 없습니다.\n"
                "(설정에서 점검을 꺼도, 「비밀 파일도 진행」으로도 우회할 수 없습니다.)\n\n"
                f"{listing}\n\n"
                "키·인증서를 파일에서 지운 뒤 다시 시도하세요.",
            )
            self._log("다음: 파일 안의 키/인증서를 지운 뒤 다시 올리기")
            return False
        if secrets or soft_content:
            listing_parts: list[str] = []
            if secrets:
                listing_parts.append(format_secret_list(secrets))
            if soft_content:
                listing_parts.append(format_content_secret_list(soft_content))
            listing = "\n".join(p for p in listing_parts if p)
            if not allow_secrets:
                QMessageBox.warning(
                    self.window,
                    "올릴 수 없음",
                    "비밀처럼 보이는 파일이 있어 막았습니다.\n\n"
                    f"{listing}\n\n"
                    "1) 파일을 빼거나 이름 바꾸기\n"
                    "2) 정말 필요하면 「비밀 파일도 진행 (고급)」을 켠 뒤 다시\n"
                    "3) 또는 설정 → 안전에서 점검을 끈 뒤 (경고 문구 입력)\n\n"
                    "참고: .env.example 같은 샘플 이름도 걸릴 수 있습니다.",
                )
                self._log(
                    "다음: 비밀 파일을 빼거나, 「비밀 파일도 진행 (고급)」을 켠 뒤 다시"
                )
                return False
            parts.append(
                "【비밀 파일 — 고급 허용】\n"
                f"{listing}\n"
                "내용에 실제 비밀번호가 없는지 확인하세요."
            )

        # Content PII (phone/email) — only when scan is enabled
        if scan_on:
            pii_hits = scan_pii_in_contents(folder)
            if pii_hits:
                listing = format_pii_list(pii_hits)
                parts.append(
                    "【개인정보 후보】\n"
                    f"{listing}\n"
                    "실제 전화·이메일이면 지운 뒤 올리세요. (예시 값은 오탐일 수 있음)"
                )
        if not scan_on:
            parts.append(
                "【안내】 설정에서 비밀·개인정보 점검이 꺼져 있습니다. "
                "파일 이름·개인정보 자동 차단을 건너뜁니다. "
                "(키·인증서 형태는 여전히 막습니다.)"
            )

        email = preview_commit_email(
            folder, None, hide_real_email=hide_real_email
        )
        parts.append(
            _format_commit_email_g3(
                email, private=private, hide_real_email=hide_real_email
            )
        )

        if not secrets and not content_secrets and not pii_hits:
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
        folder = _folder_path(self.editFolder)
        name = (self.editRepoName.text() or "").strip()
        msg = (
            (self.editCommitMessage.text() if self.editCommitMessage else None)
            or "첫 업로드"
        ).strip()
        allow_ui = bool(
            self.checkAllowSecrets and self.checkAllowSecrets.isChecked()
        )
        allow = self._effective_allow_secrets(allow_ui)
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

        # H1: create .git (+ default .gitignore) before safety so gitignore applies
        from app.git.publish import (
            PublishError,
            ensure_repo_for_safety,
            resolve_publish_branch,
        )

        root = path.resolve()
        try:
            branch = resolve_publish_branch(self._publish_branch_name())
        except PublishError as e:
            QMessageBox.warning(self.window, "branch", str(e))
            return

        need_git_prep = not (root / ".git").exists()
        if need_git_prep:
            # Surprise prevention (P3): prep happens before G3 confirm
            prep = QMessageBox.question(
                self.window,
                "폴더 준비",
                "올리기 전에 이 폴더를 Git 저장소로 준비합니다.\n\n"
                "· .git 폴더가 생깁니다\n"
                "· .gitignore 가 없으면 기본 목록을 만듭니다\n"
                f"· 첫 branch: {branch}\n\n"
                "확인 창에서 취소해도 위 준비는 이미 남습니다.\n"
                "계속할까요?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Ok,
            )
            if prep != QMessageBox.StandardButton.Ok:
                self._log("Publish 취소 — Git 준비 안내")
                return

        try:
            ensure_repo_for_safety(root, write_gitignore=True, branch=branch)
        except PublishError as e:
            QMessageBox.warning(self.window, "CloneUp", str(e))
            return
        except Exception as e:
            QMessageBox.warning(
                self.window, "CloneUp", f"폴더 Git 준비에 실패했습니다.\n{e}"
            )
            return
        if need_git_prep:
            self._log(f"안내: 이 폴더에 .git 준비를 마쳤습니다 (branch {branch}).")

        report = run_safety_checks(
            root,
            allow_secrets=allow,
            write_gitignore=False,
            scan_pii=self._safety_scan_enabled(),
        )
        if not report.ok:
            # Prefer G3-style secret listing when that is the only block
            if report.secret_candidates and not allow:
                self._confirm_upload_g3(
                    root,
                    allow_secrets=False,
                    private=private,
                    hide_real_email=hide_email,
                )
                return
            QMessageBox.warning(self.window, "올릴 수 없음", "\n".join(report.errors))
            return

        if not self._confirm_upload_g3(
            root,
            allow_secrets=allow,
            private=private,
            hide_real_email=hide_email,
        ):
            self._log("Publish 취소 — 확인 대화상자")
            return

        remember_folder(str(root))
        self._reload_recent_combo()
        save_last_private(private)
        save_last_commit_message(msg)
        save_last_publish_branch(branch)
        save_hide_real_email(hide_email)

        self._log(
            f"--- Publish: {name} ({'private' if private else 'public'}, "
            f"branch {branch}) ---"
        )
        w = PublishWorker(
            folder=str(root),
            repo_name=name,
            commit_message=msg,
            private=private,
            allow_secrets=allow,
            hide_real_email=hide_email,
            default_branch=branch,
            parent=self,
        )
        w.succeeded.connect(self._on_publish_ok)
        w.failed.connect(self._on_fail_msg)
        self._start_worker(w)

    def _go_sync_tab(self, folder: str | None = None) -> None:
        """Fill Sync folder field and switch to the Sync tab (V5 next step)."""
        if folder and self.editSyncFolder is not None:
            _set_folder_path(self.editSyncFolder, str(folder))
            remember_folder(str(folder))
            self._reload_recent_combo()
            # Auto-refresh so current work-line (branch) is visible immediately
            QTimer.singleShot(0, self.on_sync_refresh)
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
            _set_folder_path(self.editSyncFolder, folder)
            remember_folder(folder)
            self._reload_recent_combo()

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
    # Real branch names stay intact; notes only in parentheses for beginners.
    _NOTE_DEFAULT = "default branch"
    _NOTE_FROM_URL = "from URL"

    @staticmethod
    def _format_branch_label(name: str, note: str | None = None) -> str:
        name = (name or "").strip()
        if not name:
            return ""
        if note:
            return f"{name} ({note})"
        return name

    @classmethod
    def _parse_branch_label(cls, display: str) -> str | None:
        """Extract real branch name; ignore UI-only notes in (...)."""
        text = (display or "").strip()
        if not text or text in ("default branch", "기본 브랜치"):
            return None
        if text.endswith(")") and " (" in text:
            base, _, note = text.rpartition(" (")
            note = note[:-1].strip()
            if note in (cls._NOTE_DEFAULT, cls._NOTE_FROM_URL, "default"):
                base = base.strip()
                return base or None
        return text

    def _clone_url_text(self) -> str:
        """Prefer itemData URL when the field still shows a list label."""
        if self.comboCloneUrl is None:
            return ""
        text = (self.comboCloneUrl.currentText() or "").strip()
        # If the visible text is a dropdown label, use stored https URL
        idx = self.comboCloneUrl.currentIndex()
        if idx >= 0:
            data = self.comboCloneUrl.itemData(idx)
            if isinstance(data, str) and data.startswith("https://github.com/"):
                label = (self.comboCloneUrl.itemText(idx) or "").strip()
                # Same selection: label or already-normalized URL
                if text == label or text == data or text.rstrip("/") == data.rstrip("/"):
                    return data.strip()
                # Text still looks like "owner/repo" / list label for this item
                base = label.split("  ·  ")[0].split(" · ")[0].strip()
                if text == base or text.startswith(base + " "):
                    return data.strip()
        return text

    def _set_clone_url_text(self, text: str, *, block: bool = True) -> None:
        if self.comboCloneUrl is None:
            return
        if block:
            self.comboCloneUrl.blockSignals(True)
            le = self.comboCloneUrl.lineEdit()
            if le is not None:
                le.blockSignals(True)
        try:
            self.comboCloneUrl.setEditText(text)
        finally:
            if block:
                le = self.comboCloneUrl.lineEdit()
                if le is not None:
                    le.blockSignals(False)
                self.comboCloneUrl.blockSignals(False)

    def _sync_clone_url_login_mode(self, *, force: bool = False) -> None:
        """
        Logged in  → dropdown list of my repos (+ still editable URL).
        Logged out → plain URL field (no list / no chevron), same as before.

        Uses ``is_logged_in()``. Always re-ensures the repo list when logged in
        and the combo is still empty (so a failed first fetch can recover).
        """
        if self.comboCloneUrl is None:
            return
        logged_in = is_logged_in()
        mode_changed = self._clone_url_logged_in_mode != logged_in
        if (
            not force
            and not mode_changed
            and self._clone_url_logged_in_mode is not None
            and logged_in
            and self.comboCloneUrl.count() > 0
        ):
            # Already in list mode with items
            return
        if (
            not force
            and not mode_changed
            and self._clone_url_logged_in_mode is not None
            and not logged_in
        ):
            return

        self._clone_url_logged_in_mode = logged_in
        le = self.comboCloneUrl.lineEdit()
        # Native combo arrow is always hidden (theme); use explicit 「목록 ▼」 button.
        if self.btnCloneRepoList is not None:
            self.btnCloneRepoList.setVisible(logged_in)
            self.btnCloneRepoList.setEnabled(logged_in and not self._busy())
        # labelCloneHint stays on its short static .ui text (root-only +
        # branch-below) regardless of login state — the list-picker mention
        # already lives in the placeholder below, the button's own tooltip,
        # and the top tip card, so repeating it here just ate vertical space.
        if logged_in:
            if le is not None:
                le.setPlaceholderText(
                    "「목록 ▼」에서 고르거나 https://github.com/owner/repo"
                )
            self._maybe_load_clone_repo_list(
                force=force or mode_changed or self.comboCloneUrl.count() == 0
            )
        else:
            cur = self._clone_url_text()
            self.comboCloneUrl.blockSignals(True)
            self.comboCloneUrl.clear()
            if cur:
                self.comboCloneUrl.setEditText(cur)
            self.comboCloneUrl.blockSignals(False)
            self._clone_repos_loaded_for = "none"
            if le is not None:
                le.setPlaceholderText("https://github.com/owner/repo")

    @Slot()
    def _on_clone_repo_list_clicked(self) -> None:
        """Open the repo list popup (visible button — native ▼ is hidden)."""
        if self.comboCloneUrl is None:
            return
        if not is_logged_in():
            QMessageBox.information(
                self.window,
                "목록",
                "GitHub에 연결한 뒤에 내 저장소 목록을 볼 수 있습니다.\n"
                "위쪽 「GitHub: 연결」을 눌러 주세요.",
            )
            return
        if self.comboCloneUrl.count() == 0:
            self._maybe_load_clone_repo_list(force=True)
            self._log("받기: 목록을 불러온 뒤 다시 「목록 ▼」을 눌러 주세요.")
            return
        # Drop-down under the field
        self.comboCloneUrl.setFocus(Qt.FocusReason.MouseFocusReason)
        self.comboCloneUrl.showPopup()

    @Slot()
    def _on_clone_url_text_changed(self, _text: str = "") -> None:
        """Debounce paste so long /tree/… URLs collapse to owner/repo."""
        self._clone_url_timer.start()

    @Slot(int)
    def _on_clone_url_activated(self, index: int) -> None:
        """User picked a listed repo — put the real GitHub URL in the field."""
        if not is_logged_in() or self.comboCloneUrl is None or index < 0:
            return
        url = self.comboCloneUrl.itemData(index)
        if isinstance(url, str) and url.strip():
            self._set_clone_url_text(url.strip())
            self._normalize_clone_url_field()

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        if self.tabWidget is None:
            return
        w = self.tabWidget.widget(index)
        if w is not None and w.objectName() == "tabClone":
            self._sync_clone_url_login_mode()

    def _maybe_load_clone_repo_list(self, *, force: bool = False) -> None:
        """Fill combo dropdown only when is_logged_in()."""
        if self.comboCloneUrl is None:
            return
        if not is_logged_in():
            self._clone_repos_loaded_for = "none"
            return
        token = load_token()
        if not token:
            return
        key = token[:12]
        if not force and self._clone_repos_loaded_for == key:
            return
        if self._clone_repos_worker is not None and self._clone_repos_worker.isRunning():
            return

        # Placeholder so the drop-down is obviously “alive” while loading
        if self.comboCloneUrl.count() == 0:
            self.comboCloneUrl.blockSignals(True)
            self.comboCloneUrl.addItem("저장소 목록 불러오는 중…", "")
            self.comboCloneUrl.blockSignals(False)

        w = _CloneRepoListWorker(token, parent=self)
        self._clone_repos_worker = w
        w.succeeded.connect(
            self._on_clone_repo_list_ok, Qt.ConnectionType.QueuedConnection
        )
        w.failed.connect(
            self._on_clone_repo_list_fail, Qt.ConnectionType.QueuedConnection
        )
        w.start()
        self._log("받기: GitHub에서 내 저장소 목록 불러오는 중…")

    @Slot(list)
    def _on_clone_repo_list_ok(self, rows: list) -> None:
        if self.comboCloneUrl is None or not is_logged_in():
            return
        token = load_token()
        self._clone_repos_loaded_for = (token or "")[:12] if token else "none"
        cur = self._clone_url_text()
        # Drop loading placeholder / stale rows
        if cur.startswith("저장소 목록"):
            cur = ""
        self.comboCloneUrl.blockSignals(True)
        self.comboCloneUrl.clear()
        n = 0
        for item in rows or []:
            if not isinstance(item, dict):
                continue
            full = str(item.get("full_name") or "").strip()
            html = str(item.get("html_url") or "").strip()
            if not full or not html:
                continue
            private = bool(item.get("private"))
            label = f"{full}  ·  비공개" if private else full
            self.comboCloneUrl.addItem(label, html)
            n += 1
        if cur and not cur.startswith("저장소 목록"):
            self.comboCloneUrl.setEditText(cur)
        else:
            self.comboCloneUrl.setEditText("")
        self.comboCloneUrl.blockSignals(False)
        if n:
            self._log(
                f"받기: 내 저장소 {n}개 준비됨 — 「목록 ▼」 버튼으로 고르세요"
            )
            if self.btnCloneRepoList is not None:
                self.btnCloneRepoList.setText(f"목록 ▼ ({n})")
        else:
            self._log("받기: 목록이 비어 있습니다. 주소를 직접 붙여 넣으세요.")
            if self.btnCloneRepoList is not None:
                self.btnCloneRepoList.setText("목록 ▼")

    @Slot(str)
    def _on_clone_repo_list_fail(self, msg: str) -> None:
        self._clone_repos_loaded_for = None  # allow retry
        if self.comboCloneUrl is not None:
            cur = self._clone_url_text()
            self.comboCloneUrl.blockSignals(True)
            self.comboCloneUrl.clear()
            if cur and not cur.startswith("저장소 목록"):
                self.comboCloneUrl.setEditText(cur)
            self.comboCloneUrl.blockSignals(False)
        self._log(f"받기: 저장소 목록을 못 읽음 ({msg[:160]})")

    @Slot()
    def _normalize_clone_url_field(self) -> None:
        """
        Strip everything after github.com/user/repo and refresh branch list.

        When owner/repo changes (different repository), reset folder name and
        branch to match the new repo — old name would collide or look wrong.
        """
        if self.comboCloneUrl is None:
            return
        raw = self._clone_url_text()
        if not raw:
            # Cleared field → clear dependent fields
            self._last_clone_repo_key = None
            if self.editCloneDirName is not None:
                self.editCloneDirName.clear()
            if self.comboCloneBranch is not None:
                self.comboCloneBranch.blockSignals(True)
                self.comboCloneBranch.clear()
                self.comboCloneBranch.blockSignals(False)
            return
        try:
            n = normalize_github_clone_url(raw)
        except UrlError:
            return

        # Rewrite field to clean root (no .git, no subpaths)
        if self._clone_url_text() != n.display_url:
            self._set_clone_url_text(n.display_url)
            for w in n.warnings:
                self._log(f"URL 안내: {w}")

        repo_key = f"{n.owner}/{n.repo}".lower()
        repo_changed = self._last_clone_repo_key != repo_key
        self._last_clone_repo_key = repo_key

        if self.editCloneDirName is not None:
            cur_name = (self.editCloneDirName.text() or "").strip()
            # New/empty → fill; different repo → always reset to new repo name
            if repo_changed or not cur_name:
                self.editCloneDirName.setText(n.repo)
                if repo_changed and cur_name and cur_name != n.repo:
                    self._log(f"폴더 이름 → {n.repo} (저장소가 바뀜)")

        self._refresh_clone_branches(
            n.owner,
            n.repo,
            suggested=n.suggested_branch,
            repo_changed=repo_changed,
        )

    def _refresh_clone_branches(
        self,
        owner: str,
        repo: str,
        *,
        suggested: str | None = None,
        repo_changed: bool = False,
    ) -> None:
        """
        Fill branch combo with real names; notes only as ``name (note)``.

        Never replace a branch name with a vague label alone.
        """
        if self.comboCloneBranch is None:
            return
        prev_value = self._parse_branch_label(
            self.comboCloneBranch.currentText() or ""
        )
        names: list[str] = []
        default_branch: str | None = None
        token = load_token()
        try:
            from app.github.api_client import (
                get_repo_default_branch,
                list_repo_branches,
            )

            default_branch = get_repo_default_branch(
                owner, repo, access_token=token
            )
            names = list_repo_branches(owner, repo, access_token=token)
        except Exception as e:
            self._log(f"branch list: failed ({e.__class__.__name__})")

        if default_branch and default_branch not in names:
            names = [default_branch] + names

        # Build display items: real name + optional (note)
        items: list[str] = []
        seen: set[str] = set()

        def _add(name: str, note: str | None = None) -> str:
            label = self._format_branch_label(name, note)
            key = name.lower()
            if key in seen:
                return label
            seen.add(key)
            items.append(label)
            return label

        default_label: str | None = None
        if default_branch:
            default_label = _add(default_branch, self._NOTE_DEFAULT)
        for name in names:
            if default_branch and name == default_branch:
                continue
            _add(name)
        suggested_label: str | None = None
        if suggested:
            if default_branch and suggested == default_branch:
                suggested_label = default_label
            elif suggested.lower() in seen:
                # already listed as plain name — find that label
                for it in items:
                    if self._parse_branch_label(it) == suggested:
                        suggested_label = it
                        break
            else:
                suggested_label = _add(suggested, self._NOTE_FROM_URL)

        if not items and suggested:
            suggested_label = _add(suggested, self._NOTE_FROM_URL)

        self.comboCloneBranch.blockSignals(True)
        self.comboCloneBranch.clear()
        for it in items:
            self.comboCloneBranch.addItem(it)

        # Selection: new repo → URL hint or default; same repo → keep value
        pick: str | None = None
        if repo_changed:
            pick = suggested_label or default_label
        else:
            if prev_value:
                for it in items:
                    if self._parse_branch_label(it) == prev_value:
                        pick = it
                        break
            if pick is None:
                pick = suggested_label or default_label

        if pick and self.comboCloneBranch.findText(pick) >= 0:
            self.comboCloneBranch.setCurrentIndex(
                self.comboCloneBranch.findText(pick)
            )
        elif self.comboCloneBranch.count() > 0:
            self.comboCloneBranch.setCurrentIndex(0)
        self.comboCloneBranch.blockSignals(False)

        if names or default_branch:
            self._log(
                f"branch list: {len(items)}"
                + (f" · default={default_branch}" if default_branch else "")
            )
        if suggested:
            self._log(f"branch from URL: {suggested}")

    def _selected_clone_branch(self) -> str | None:
        if self.comboCloneBranch is None:
            return None
        return self._parse_branch_label(self.comboCloneBranch.currentText() or "")

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
        url = self._clone_url_text()
        parent = (self.editCloneParent.text() if self.editCloneParent else "") or ""
        name = (self.editCloneDirName.text() if self.editCloneDirName else "") or ""
        use_token = bool(
            self.checkCloneUseToken is None or self.checkCloneUseToken.isChecked()
        )

        # A4 — 체크 ON + 미연결: 비공개/공개를 갈라 안내 (기본 체크는 유지)
        if use_token and not load_token():
            box = QMessageBox(self.window)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("GitHub 연결")
            box.setText(
                "「비공개 저장소 받을 때 GitHub 연결 사용」이 켜져 있는데,\n"
                "아직 GitHub와 연결되지 않았습니다."
            )
            box.setInformativeText(
                "· 비공개 저장소 → 연결하기\n"
                "· 공개 저장소 → 연결 없이 받기"
            )
            btn_connect = box.addButton(
                "연결하기", QMessageBox.ButtonRole.AcceptRole
            )
            btn_public = box.addButton(
                "연결 없이 받기", QMessageBox.ButtonRole.ActionRole
            )
            box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is btn_connect:
                self.on_login()
                return
            if clicked is btn_public:
                use_token = False
                if self.checkCloneUseToken is not None:
                    self.checkCloneUseToken.setChecked(False)
                self._log("공개 저장소로 보고, 연결 없이 받기를 진행합니다.")
            else:
                self._log("받기 취소")
                return

        if not url.strip():
            QMessageBox.warning(self.window, "CloneUp", "GitHub 주소를 입력하세요.")
            return
        if not parent.strip() or not Path(parent).expanduser().is_dir():
            QMessageBox.warning(self.window, "CloneUp", "저장 위치 폴더를 선택하세요.")
            return
        try:
            norm = normalize_github_clone_url(url)
            # Ensure field shows cleaned root before work starts
            self._set_clone_url_text(norm.display_url)
            for w in norm.warnings:
                self._log(f"URL 안내: {w}")
        except UrlError as e:
            QMessageBox.warning(self.window, "주소 오류", str(e))
            return

        branch = self._selected_clone_branch()
        branch_note = branch or "(repo default)"
        self._log(f"--- clone: {norm.display_url} · branch {branch_note} ---")
        w = CloneWorker(
            url=norm.display_url,
            parent_dir=str(Path(parent).expanduser().resolve()),
            dir_name=name.strip(),
            use_token=use_token,
            branch=branch,
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
            _set_folder_path(self.editSyncFolder, path)

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
    def _clear_sync_chips(self) -> None:
        """Remove dynamic status chips; keep the placeholder label if present."""
        lay = self._sync_chips_layout
        if lay is None:
            return
        # Remove everything except labelSyncStatus (placeholder) and spacer
        for i in reversed(range(lay.count())):
            item = lay.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w is None:
                continue
            name = w.objectName() or ""
            if name == "labelSyncStatus":
                w.show()
                w.setText("폴더를 고르면 표시됩니다")
                continue
            if name.startswith("syncChip_"):
                lay.removeWidget(w)
                w.deleteLater()

    def _add_sync_chip(self, text: str, kind: str) -> None:
        """
        Add a colored pill. kind: ok | warn | bad | info | muted
        """
        lay = self._sync_chips_layout
        if lay is None:
            return
        # Hide plain-text placeholder once we show chips
        if self.labelSyncStatus is not None:
            self.labelSyncStatus.hide()
        chip = QLabel(text)
        chip.setObjectName(f"syncChip_{kind}")
        chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Re-apply stylesheet on the chip via parent polish
        chip.setProperty("class", f"syncChip_{kind}")
        # Insert before trailing spacer (last item)
        idx = max(0, lay.count() - 1)
        lay.insertWidget(idx, chip)
        # Ensure theme QSS applies to dynamically created widgets
        host = self.window
        if host is not None:
            chip.style().unpolish(chip)
            chip.style().polish(chip)

    def _render_sync_status_chips(self, st: dict) -> None:
        """Visual chips for GitHub / local / push-pull (beginner scannable)."""
        self._clear_sync_chips()
        conflict = bool(st.get("conflict"))
        has_origin = bool(st.get("has_origin"))
        dirty = bool(st.get("dirty"))
        ahead = st.get("ahead")
        behind = st.get("behind")

        if conflict:
            self._add_sync_chip("●  변경이 겹침", "bad")
        if has_origin:
            self._add_sync_chip("●  GitHub에 연결됨", "ok")
        else:
            self._add_sync_chip("○  GitHub에 연결 안 됨", "muted")

        # Local working tree (uncommitted)
        if conflict:
            pass
        elif dirty:
            self._add_sync_chip("●  올릴 변경 있음", "warn")
        else:
            self._add_sync_chip("●  새 변경 없음", "ok")

        # Commit vs origin — skip "같음" when local dirty so chips don't contradict
        # (dirty + ahead/behind 0 = uncommitted files, remote tip still matches)
        if has_origin and ahead is not None and behind is not None:
            try:
                a, b = int(ahead), int(behind)
            except (TypeError, ValueError):
                a, b = 0, 0
            if a == 0 and b == 0:
                if not dirty and not conflict:
                    self._add_sync_chip("●  GitHub와 같음", "ok")
                # if dirty: "올릴 변경 있음" already explains the situation
            else:
                if a > 0:
                    self._add_sync_chip(f"↑  보낼 내용 {a}개", "info")
                if b > 0:
                    self._add_sync_chip(f"↓  받을 내용 {b}개", "info")
        elif has_origin:
            self._add_sync_chip("·  비교할 수 없음", "muted")

    def _clear_sync_status_labels(self) -> None:
        if self.labelSyncBranch is not None:
            self.labelSyncBranch.setText("(폴더를 고르면 표시됩니다)")
        self._clear_sync_chips()
        if self.labelSyncStatus is not None:
            self.labelSyncStatus.show()
            self.labelSyncStatus.setText("폴더를 고르면 표시됩니다")

    def _set_sync_branch_label(self, branch: str | None) -> None:
        """Value only — title「branch」is the left form label; badge hugs text."""
        if self.labelSyncBranch is None:
            return
        b = (branch or "").strip()
        if not b:
            text = "(알 수 없음)"
        elif b.startswith("("):
            text = f"{b}  ·  특정 커밋만 보는 중"
        else:
            text = b
        self.labelSyncBranch.setText(text)
        # Content-sized badge: lift any stretch from the HBox row
        self.labelSyncBranch.setMinimumWidth(0)
        self.labelSyncBranch.setMaximumWidth(16777215)
        self.labelSyncBranch.adjustSize()
        hint_w = self.labelSyncBranch.sizeHint().width()
        # padding safety for font metrics / QSS
        self.labelSyncBranch.setFixedWidth(max(hint_w + 4, 48))

    @Slot()
    def _on_sync_folder_text_changed(self, _text: str = "") -> None:
        """Debounce while pasting/typing a path (improvement 2)."""
        self._sync_folder_timer.start()

    @Slot()
    def _on_sync_folder_editing_finished(self) -> None:
        self._sync_folder_timer.stop()
        # Keep tooltip in sync with whatever the user typed (full path always).
        ed = self.editSyncFolder
        if ed is not None:
            t = (ed.text() or "").strip()
            if t:
                ed.setToolTip(t)
        self._sync_folder_maybe_refresh()

    @Slot()
    def _sync_folder_maybe_refresh(self) -> None:
        """Auto status refresh when folder field settles (browse / paste / type)."""
        if self._busy():
            return
        folder = _folder_path(self.editSyncFolder)
        if not folder:
            self._clear_sync_status_labels()
            return
        try:
            p = Path(folder).expanduser()
            if not p.is_dir():
                return  # incomplete path while typing
            if not (p / ".git").is_dir():
                if self.labelSyncBranch is not None:
                    self.labelSyncBranch.setText(
                        "(.git 없음 — 「받기」/「만들고 올리기」먼저)"
                    )
                self._clear_sync_chips()
                self._add_sync_chip("○  Git 폴더 아님", "muted")
                if self.labelSyncStatus is not None:
                    self.labelSyncStatus.hide()
                return
        except OSError:
            return
        self.on_sync_refresh(quiet=True)

    @Slot()
    def on_sync_browse(self) -> None:
        if not self.editSyncFolder:
            return
        start = _folder_path(self.editSyncFolder) or str(Path.home())
        path = QFileDialog.getExistingDirectory(self.window, "로컬 폴더", start)
        if path:
            _set_folder_path(self.editSyncFolder, path)
            remember_folder(path)
            self._reload_recent_combo()
            self.on_sync_refresh(quiet=True)

    def _open_commit_history(self, folder: str) -> None:
        """Validate local git folder and open read-only commit history dialog."""
        folder = (folder or "").strip()
        if not folder:
            QMessageBox.warning(
                self.window,
                "커밋 내역",
                "로컬 폴더를 선택하세요.",
            )
            return
        try:
            p = Path(folder).expanduser().resolve()
            if not p.is_dir():
                QMessageBox.warning(
                    self.window, "커밋 내역", "폴더를 찾을 수 없습니다."
                )
                return
            if not (p / ".git").exists():
                QMessageBox.warning(
                    self.window,
                    "커밋 내역",
                    "이 폴더는 Git 저장소가 아닙니다.\n"
                    "「받기」로 받은 뒤이거나, .git 이 있는 폴더를 고르세요.",
                )
                return
        except OSError as e:
            QMessageBox.warning(self.window, "커밋 내역", str(e))
            return
        self._log(f"커밋 내역 열기: {p}")
        show_commit_history(self.window, str(p))

    @Slot()
    def on_sync_history(self) -> None:
        """Open read-only commit history for the sync-tab folder."""
        if self._busy():
            return
        self._open_commit_history(_folder_path(self.editSyncFolder))

    @staticmethod
    def _local_clone_for_url(target: Path, owner: str, repo: str) -> str | None:
        """
        If *target* is already a local clone of owner/repo, return its path
        (so 커밋 내역 opens in local/되돌리기-capable mode instead of the
        read-only-only GitHub API view) — else None.
        """
        try:
            if not target.is_dir() or not (target / ".git").is_dir():
                return None
            r = run_git(["remote", "get-url", "origin"], cwd=str(target), check=False)
            if r.returncode != 0:
                return None
            origin = (r.stdout or "").strip()
            if not origin:
                return None
            n2 = normalize_github_clone_url(origin)
        except (GitError, UrlError, OSError):
            return None
        if n2.owner.lower() == owner.lower() and n2.repo.lower() == repo.lower():
            return str(target)
        return None

    def _find_local_clone_for_url(self, owner: str, repo: str) -> str | None:
        """
        Look for an existing local clone of owner/repo.

        editCloneParent/editCloneDirName are plain text fields — not saved
        anywhere, so they reset to their defaults on every app restart and
        after navigating away. Checking only those means "이미 받았음" is
        detected in the same session right after cloning, then quietly stops
        working the next time the app opens. 최근 폴더 (settings-backed,
        survives restarts) is the fallback so a previously cloned repo is
        still found regardless of what's currently typed in the 받기 탭.
        """
        parent = (self.editCloneParent.text() if self.editCloneParent else "") or ""
        if parent.strip():
            dirname = (
                self.editCloneDirName.text() if self.editCloneDirName else ""
            ) or ""
            target = Path(parent).expanduser() / (dirname.strip() or repo)
            found = self._local_clone_for_url(target, owner, repo)
            if found:
                return found
        for candidate in load_recent_folders():
            found = self._local_clone_for_url(Path(candidate), owner, repo)
            if found:
                return found
        return None

    @Slot()
    def on_clone_history(self) -> None:
        """Open commit history for the GitHub URL on the 받기 tab.

        Already cloned somewhere on this computer (checked against 최근
        폴더, not just whatever the 받기 탭 fields currently show)? Open
        that local folder instead — same 읽기 전용/되돌리기 popup as 동기화
        탭, gated by the same Settings > 안전 switch. Never cloned? Fall
        back to the read-only GitHub API view; public repos work without
        login, private needs a stored token.
        """
        if self._busy():
            return
        raw = self._clone_url_text()
        if not raw:
            QMessageBox.warning(
                self.window,
                "커밋 내역",
                "GitHub 저장소 주소를 입력하세요.\n"
                "예: https://github.com/사용자/저장소\n\n"
                "공개 저장소는 로그인 없이 볼 수 있습니다.",
            )
            return
        try:
            n = normalize_github_clone_url(raw)
        except UrlError as e:
            QMessageBox.warning(self.window, "커밋 내역", str(e))
            return

        local = self._find_local_clone_for_url(n.owner, n.repo)
        if local:
            self._log(f"커밋 내역 열기(이미 받은 로컬 폴더): {local}")
            show_commit_history(self.window, local)
            return

        # Optional token: public OK without; private needs connect
        token = load_token()
        self._log(f"커밋 내역 열기(GitHub): {n.display_url}")
        show_remote_commit_history(
            self.window,
            n.owner,
            n.repo,
            access_token=token,
            display_url=n.display_url,
        )

    @Slot()
    def on_sync_refresh(self, quiet: bool = False) -> None:
        if self._busy():
            return
        folder = _folder_path(self.editSyncFolder)
        if not folder:
            if not quiet:
                QMessageBox.warning(
                    self.window, "CloneUp", "동기화할 폴더를 선택하세요."
                )
            else:
                self._clear_sync_status_labels()
            return
        self._log(f"--- 상태: {folder} ---")
        w = SyncStatusWorker(folder=folder, parent=self)
        w.succeeded.connect(self._on_sync_status)
        w.failed.connect(
            lambda msg, q=quiet: self._on_sync_status_failed(msg, quiet=q)
        )
        if hasattr(w, "log_line"):
            w.log_line.connect(self._log)
        self._start_worker(w)

    @Slot(str)
    def _on_sync_status_failed(self, message: str, *, quiet: bool = False) -> None:
        if self.labelSyncBranch is not None:
            self.labelSyncBranch.setText("(확인 실패)")
        self._clear_sync_chips()
        self._add_sync_chip("●  상태를 읽지 못함", "bad")
        if self.labelSyncStatus is not None:
            self.labelSyncStatus.hide()
        if quiet:
            self._log(message)
        else:
            self._on_fail_msg(message)

    @Slot(dict)
    def _on_sync_status(self, st: dict) -> None:
        branch = str(st.get("branch") or "").strip()
        summary = st.get("summary") or ""
        self._set_sync_branch_label(branch)
        self._render_sync_status_chips(st)
        if branch:
            self._log(f"branch: {branch}")
        if summary:
            self._log(summary)
        if st.get("conflict"):
            QMessageBox.warning(
                self.window,
                "변경이 겹침",
                "이 폴더와 GitHub 내용이 서로 달라 자동으로 합치지 못했습니다.\n"
                "「충돌 취소」로 되돌리거나, 다른 프로그램에서 파일을 고친 뒤 다시 하세요.",
            )

    @Slot()
    def on_sync_action(self, action: str) -> None:
        if self._busy():
            return
        folder = _folder_path(self.editSyncFolder)
        if not folder:
            QMessageBox.warning(self.window, "CloneUp", "동기화할 폴더를 선택하세요.")
            return
        msg = (
            (self.editSyncMessage.text() if self.editSyncMessage else None)
            or "변경 사항 반영"
        ).strip()
        allow_ui = bool(
            self.checkSyncAllowSecrets and self.checkSyncAllowSecrets.isChecked()
        )
        allow = self._effective_allow_secrets(allow_ui)
        hide_email = bool(
            self.checkSyncHideEmail is None or self.checkSyncHideEmail.isChecked()
        )

        if action == "abort":
            ans = QMessageBox.question(
                self.window,
                "충돌 취소",
                "서로 다른 변경이 겹친 상태를 되돌릴까요?\n\n"
                "· 같은 부분을 컴퓨터와 GitHub 양쪽에서 고쳐서 "
                "자동으로 합치지 못한 상태입니다.\n"
                "· 「충돌 취소」는 합치기 시도를 포기하고, "
                "그 시도 직전으로 돌아갑니다.\n"
                "· 「커밋 내역」의 되돌리기(지난 시점으로 새 커밋)와는 다릅니다.\n\n"
                "계속할까요?",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        if action == "pull":
            ans = QMessageBox.question(
                self.window,
                "받아오기",
                "GitHub에 있는 최신 기록을 이 폴더로 가져옵니다.\n"
                "(원격에만 있는 커밋을 가져와, 내 PC 기록을 맞춥니다.)\n\n"
                "같은 줄을 양쪽에서 고친 경우에는 자동으로 합치지 않고 멈출 수 있습니다. "
                "그때는 「충돌 취소」를 쓰세요. 계속할까요?",
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
        if _folder_path(self.editSyncFolder):
            # chain a status refresh without blocking — schedule after busy clears
            QTimer.singleShot(100, self.on_sync_refresh)
