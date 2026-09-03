"""Settings dialog — desin/CloneUp 설정.dc.html (+ Settings Dark.dc.html).

Sidebar tabs: 계정 · 올리기 기본값 · 안전 · 최근 폴더 · 용어 안내 · 정보.
Prefs save immediately (footer: 바꾸면 바로 저장됩니다).
Colors follow active_palette() (OS light/dark).

Safety tab includes master-password token protection (enable / change / disable).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QRectF, QUrl, Qt, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# Soft minimum for master password UX (crypto already rejects empty/whitespace).
_MASTER_PW_MIN_LEN = 8

from app.auth.secret_vault import VaultError
from app.auth.session import refresh_scopes_from_github
from app.auth.token_expiry import (
    format_connected_at_display,
    format_expires_display,
)
from app.auth.token_store import (
    AUTH_KIND_DEVICE,
    AUTH_KIND_PAT,
    SCOPE_UNKNOWN,
    change_master_password,
    disable_master_protection,
    enable_master_protection,
    format_scopes_display,
    is_logged_in,
    is_token_encrypted,
    load_auth_kind,
    load_connected_at_raw,
    load_expires_at_raw,
    load_pat_note,
    load_scope,
    master_protection_enabled,
)
from app.git.runner import require_git
from app.paths import app_root
from app.ui.login_dialog import PAT_LIST_URL
from app.ui.settings_store import (
    USER_GLOSSARY_DETAIL_MAX,
    USER_GLOSSARY_LINE_MAX,
    USER_GLOSSARY_TERM_MAX,
    add_user_glossary_entry,
    clear_recent_folders,
    load_boot_autostart_enabled,
    load_boot_notify_enabled,
    load_hide_real_email,
    load_history_revert_enabled,
    load_last_commit_message,
    load_last_github_login,
    load_last_private,
    load_last_publish_branch,
    load_recent_folders,
    load_secret_pii_scan_enabled,
    load_user_glossary,
    remove_user_glossary_entry,
    save_boot_autostart_enabled,
    save_boot_notify_enabled,
    save_boot_notify_snooze_until,
    save_hide_real_email,
    save_history_revert_enabled,
    save_last_commit_message,
    save_last_private,
    save_last_publish_branch,
    save_secret_pii_scan_enabled,
)
from app.util.error_popup import format_error_popup_body
from app.util.autostart_win import (
    apply_autostart_preference,
    is_autostart_registered,
    set_autostart_registered,
)
from app.ui.git_terms_ko import GLOSSARY_ENTRIES
from app.ui.theme import Palette, active_palette

_NAV = ("계정", "올리기 기본값", "안전", "최근 폴더", "용어 안내", "정보")

# Exact phrase required to disable secret/PII scan (user must type it).
SECRET_SCAN_OFF_PHRASE = "나는 위의 안내, 경고 사항을 모두 읽고 이해했습니다"


def phrase_matches_secret_scan_off(typed: str) -> bool:
    """True when typed text matches the disable confirmation phrase exactly."""
    return (typed or "").strip() == SECRET_SCAN_OFF_PHRASE


def _warn_soft_bg(p: Palette) -> str:
    """Amber panel fill — light mock #fbf6ee, dark Settings mock #2e2a1e."""
    return "#2e2a1e" if p.name == "dark" else "#fbf6ee"


def _danger_label(p: Palette) -> str:
    """Logout outline button text — dark mock #d98d88."""
    return "#d98d88" if p.name == "dark" else "#9a4a45"


def _danger_hover_bg(p: Palette) -> str:
    """Logout outline hover — dark mock #33241f."""
    return "#33241f" if p.name == "dark" else "#f7efee"


class _ToggleSwitch(QWidget):
    """Pill track + round knob (시안 40×23, knob 19, radius 12 / 50%).

    Drawn with QPainter so Windows does not ignore border-radius on QFrame.
    ``locked=True``: always shown on, ignores clicks (policy: always-on safety).
    """

    toggled = Signal(bool)

    # Design tokens from desin/CloneUp 설정.dc.html
    _W = 40
    _H = 23
    _KNOB = 19
    _PAD = 2

    def __init__(
        self,
        checked: bool = True,
        parent: QWidget | None = None,
        *,
        locked: bool = False,
    ) -> None:
        super().__init__(parent)
        self._locked = bool(locked)
        # Locked switches are always on (safety features users cannot disable)
        self._on = True if self._locked else bool(checked)
        self.setFixedSize(self._W, self._H)
        if self._locked:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.setToolTip("CloneUp에서는 항상 켜 둡니다. 끌 수 없습니다.")
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def isChecked(self) -> bool:
        return self._on

    def isLocked(self) -> bool:
        return self._locked

    def setChecked(self, checked: bool, *, emit: bool = True) -> None:
        if self._locked:
            # Policy: cannot turn off
            if not self._on:
                self._on = True
                self.update()
            return
        on = bool(checked)
        if self._on == on:
            self.update()
            return
        self._on = on
        self.update()
        if emit:
            self.toggled.emit(self._on)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._locked:
                event.accept()
                return
            self.setChecked(not self._on)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._locked:
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.setChecked(not self._on)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        pal = active_palette()
        track = QColor(pal.primary if self._on else pal.border_input)
        knob = QColor(pal.bg_window)
        # Locked: same on look (policy always-on), slightly softer so it reads “fixed”
        if self._locked and self._on:
            track.setAlpha(230)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        # Capsule track (height 23 → radius = half height)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 0, self._W, self._H), self._H / 2, self._H / 2)

        # Round knob, inset 2px, left or right
        ky = float(self._PAD)
        kx = float(self._W - self._PAD - self._KNOB) if self._on else float(self._PAD)
        painter.setBrush(knob)
        painter.drawEllipse(QRectF(kx, ky, self._KNOB, self._KNOB))
        painter.end()


def _mono(base: QFont) -> QFont:
    f = QFont(base)
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setFamilies(["Cascadia Mono", "Consolas", "IBM Plex Mono", "monospace"])
    return f


class SettingsDialog(QDialog):
    """Modal settings browser matching the design mock."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        on_login: Callable[[], None] | None = None,
        on_logout: Callable[[], None] | None = None,
        on_prefs_changed: Callable[..., Any] | None = None,
        on_open_onboarding: Callable[[], None] | None = None,
        initial_tab: int = 0,
    ) -> None:
        super().__init__(parent)
        self._on_login = on_login
        self._on_logout = on_logout
        self._on_prefs_changed = on_prefs_changed
        self._on_open_onboarding = on_open_onboarding
        self._nav_btns: list[QPushButton] = []
        self._private = load_last_private()
        self._hide_email = load_hide_real_email()
        self._secret_scan = load_secret_pii_scan_enabled()
        self._history_revert = load_history_revert_enabled()
        self._secret_scan_block = False  # ignore toggle while reverting UI
        p = active_palette()

        self.setWindowTitle("설정")
        self.setModal(True)
        # Wide enough for account card: meta + 「다시 로그인」「로그아웃」「권한 다시 확인」
        # in one horizontal row (do not stack buttons).
        self.setMinimumSize(960, 560)
        self.resize(1020, 660)
        self.setStyleSheet(self._dialog_qss(p))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # title bar
        bar = QFrame()
        bar.setObjectName("setTitleBar")
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(16, 12, 16, 12)
        title = QLabel("설정")
        title.setObjectName("setTitle")
        bar_l.addWidget(title)
        bar_l.addStretch(1)
        root.addWidget(bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # sidebar
        nav = QFrame()
        nav.setObjectName("setNav")
        nav.setFixedWidth(168)
        nav_l = QVBoxLayout(nav)
        nav_l.setContentsMargins(0, 14, 0, 14)
        nav_l.setSpacing(2)
        for i, label in enumerate(_NAV):
            btn = QPushButton(label)
            btn.setObjectName("setNavItem")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, idx=i: self._go_tab(idx))
            self._nav_btns.append(btn)
            nav_l.addWidget(btn)
        nav_l.addStretch(1)
        body.addWidget(nav)

        # pages
        self._stack = QStackedWidget()
        self._stack.setObjectName("setStack")
        self._page_account = self._build_account(p)
        self._page_defaults = self._build_defaults(p)
        self._page_safety = self._build_safety(p)
        self._page_folders = self._build_folders(p)
        self._page_terms = self._build_terms(p)
        self._page_about = self._build_about(p)
        for page in (
            self._page_account,
            self._page_defaults,
            self._page_safety,
            self._page_folders,
            self._page_terms,
            self._page_about,
        ):
            self._stack.addWidget(page)
        body.addWidget(self._stack, 1)
        root.addLayout(body, 1)

        # footer
        foot = QFrame()
        foot.setObjectName("setFooter")
        foot_l = QHBoxLayout(foot)
        foot_l.setContentsMargins(20, 12, 20, 12)
        note = QLabel("바꾸면 바로 저장됩니다.")
        note.setObjectName("setMeta")
        btn_close = QPushButton("닫기")
        btn_close.setObjectName("setSecondary")
        btn_close.clicked.connect(self.accept)
        foot_l.addWidget(note, 1)
        foot_l.addWidget(btn_close)
        root.addWidget(foot)

        tab = max(0, min(int(initial_tab), len(_NAV) - 1))
        self._go_tab(tab)
        self._refresh_account()
        self._refresh_folders()

    # ----- navigation -----
    def _go_tab(self, index: int) -> None:
        p = active_palette()
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            on = i == index
            btn.setChecked(on)
            if on:
                btn.setStyleSheet(
                    f"QPushButton#setNavItem {{"
                    f"background: {p.bg_window}; color: {p.primary}; "
                    f"font-weight: 600; border: none; border-left: 3px solid {p.primary}; "
                    f"text-align: left; padding: 10px 18px; font-size: 13px;}}"
                    f"QPushButton#setNavItem:hover {{background: {p.bg_window};}}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton#setNavItem {{"
                    f"background: transparent; color: {p.text_secondary}; "
                    f"font-weight: 400; border: none; border-left: 3px solid transparent; "
                    f"text-align: left; padding: 10px 18px; font-size: 13px;}}"
                    f"QPushButton#setNavItem:hover {{background: {p.hover_muted};}}"
                )
        # Safety tab index 2 — refresh master-protection status when opened.
        if index == 2 and hasattr(self, "_master_status"):
            self._refresh_master_protection()

    def _notify_prefs(self, what: str = "all") -> None:
        """Tell main window which settings group changed (selective tab sync)."""
        if self._on_prefs_changed is None:
            return
        try:
            self._on_prefs_changed(what)
        except TypeError:
            # Older callback with no args
            self._on_prefs_changed()

    # ----- pages -----
    def _page_shell(self) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(26, 26, 30, 26)
        lay.setSpacing(22)
        return w, lay

    def _heading(self, title: str, sub: str) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(5)
        t = QLabel(title)
        t.setObjectName("setHeading")
        s = QLabel(sub)
        s.setObjectName("setSub")
        s.setWordWrap(True)
        v.addWidget(t)
        v.addWidget(s)
        return box

    def _build_account(self, p: Palette) -> QWidget:
        w, lay = self._page_shell()
        lay.addWidget(
            self._heading("계정", "GitHub 연결 상태입니다.")
        )

        self._acct_card = QFrame()
        self._acct_card.setObjectName("setCard")
        card_l = QHBoxLayout(self._acct_card)
        card_l.setContentsMargins(16, 16, 16, 16)
        card_l.setSpacing(14)

        self._acct_dot = QLabel("●")
        self._acct_dot.setFixedWidth(14)
        self._acct_title = QLabel("")
        self._acct_title.setObjectName("setCardTitle")
        self._acct_meta = QLabel("")
        self._acct_meta.setObjectName("setMeta")
        self._acct_meta.setFont(_mono(self._acct_meta.font()))
        meta_col = QVBoxLayout()
        meta_col.setContentsMargins(0, 0, 0, 0)
        meta_col.setSpacing(3)
        meta_col.addWidget(self._acct_title)
        meta_col.addWidget(self._acct_meta)

        card_l.addWidget(self._acct_dot, 0, Qt.AlignmentFlag.AlignTop)
        card_l.addLayout(meta_col, 1)

        self._btn_relogin = QPushButton("다시 로그인")
        self._btn_relogin.setObjectName("setSecondary")
        self._btn_relogin.clicked.connect(self._do_relogin)
        self._btn_logout = QPushButton("로그아웃")
        self._btn_logout.setObjectName("setDangerOutline")
        self._btn_logout.clicked.connect(self._do_logout)
        self._btn_connect = QPushButton("GitHub 연결")
        self._btn_connect.setObjectName("setSecondary")
        self._btn_connect.clicked.connect(self._do_relogin)
        self._btn_refresh_scopes = QPushButton("권한 다시 확인")
        self._btn_refresh_scopes.setObjectName("setSecondary")
        self._btn_refresh_scopes.setToolTip(
            "지금 이 앱에 연결된 키의 권한만 GitHub에 물어 맞춥니다.\n"
            "classic 키: 웹에서 scope를 바꾼 뒤 이 버튼을 누르세요.\n"
            "발급한 키 전체 목록은 「키 목록」에서 봅니다."
        )
        self._btn_refresh_scopes.clicked.connect(self._do_refresh_scopes)
        self._btn_pat_list = QPushButton("키 목록")
        self._btn_pat_list.setObjectName("setSecondary")
        self._btn_pat_list.setToolTip(
            "브라우저에서 GitHub에 발급한 개인 액세스 토큰 목록을 엽니다.\n"
            "classic / 세분 키를 확인하고 권한을 고칠 수 있습니다.\n"
            "(키 문자열 자체는 보안상 다시 볼 수 없습니다.)"
        )
        self._btn_pat_list.clicked.connect(self._open_github_pat_list)
        # Keep horizontal actions; wider dialog fits labels.
        btn_policy = QSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        for b in (
            self._btn_relogin,
            self._btn_logout,
            self._btn_connect,
            self._btn_refresh_scopes,
            self._btn_pat_list,
        ):
            b.setSizePolicy(btn_policy)
            b.setMinimumWidth(0)
        self._acct_title.setWordWrap(True)
        self._acct_meta.setWordWrap(True)
        # Logged-in: 다시 로그인 · 권한 다시 확인 · 키 목록 · 로그아웃
        # Logged-out: GitHub 연결 · 키 목록
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.setContentsMargins(0, 0, 0, 0)
        btns.addWidget(self._btn_relogin, 0)
        btns.addWidget(self._btn_refresh_scopes, 0)
        btns.addWidget(self._btn_pat_list, 0)
        btns.addWidget(self._btn_logout, 0)
        btns.addWidget(self._btn_connect, 0)
        card_l.addLayout(btns, 0)
        lay.addWidget(self._acct_card)

        hint = QLabel(
            "로그아웃하면 이 컴퓨터에 저장된 토큰이 지워집니다. "
            "GitHub 쪽 승인까지 없애려면 GitHub 설정에서 따로 해제해야 합니다.\n"
            "계정 카드의 「권한」은 지금 연결된 키 하나분입니다. "
            "발급한 키 전체는 「키 목록」에서 봅니다. "
            "웹에서 권한을 바꾼 뒤에는 「권한 다시 확인」을 누르세요."
        )
        hint.setObjectName("setBanner")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        store_t = QLabel("토큰이 저장된 곳")
        store_t.setObjectName("setSection")
        lay.addWidget(store_t)
        store_b = QLabel(
            "Windows 자격 증명 관리자의 "
            '<span style="font-family: Consolas, monospace;">CloneUp</span> 항목. '
            "저장소 폴더나 로그에는 남지 않습니다."
        )
        store_b.setObjectName("setInfoBox")
        store_b.setWordWrap(True)
        store_b.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(store_b)
        lay.addStretch(1)
        return w

    def _build_defaults(self, p: Palette) -> QWidget:
        w, lay = self._page_shell()
        lay.addWidget(
            self._heading(
                "올리기 기본값",
                "새로 올릴 때 미리 채워둘 값입니다. 그때그때 바꿀 수 있습니다.",
            )
        )

        # visibility
        row = QHBoxLayout()
        row.setSpacing(18)
        lab = QLabel("공개 범위")
        lab.setObjectName("setFormLabel")
        lab.setFixedWidth(148)
        lab.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        right = QVBoxLayout()
        right.setSpacing(7)
        cards = QHBoxLayout()
        cards.setSpacing(8)
        self._btn_priv = QPushButton()
        self._btn_pub = QPushButton()
        for btn, title, sub in (
            (self._btn_priv, "비공개", "나만 볼 수 있음"),
            (self._btn_pub, "공개", "누구나 볼 수 있음"),
        ):
            btn.setObjectName("setChoiceCard")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(64)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            # Use rich text via setText doesn't support multi-line well on QPushButton
            # — store titles and paint via style + accessible name
            btn.setProperty("title", title)
            btn.setProperty("subtitle", sub)
            btn.setText(f"{title}\n{sub}")
        self._btn_priv.clicked.connect(lambda: self._set_private(True))
        self._btn_pub.clicked.connect(lambda: self._set_private(False))
        cards.addWidget(self._btn_priv)
        cards.addWidget(self._btn_pub)
        right.addLayout(cards)
        self._vis_note = QLabel("")
        self._vis_note.setObjectName("setMeta")
        self._vis_note.setWordWrap(True)
        right.addWidget(self._vis_note)
        row.addWidget(lab)
        row.addLayout(right, 1)
        lay.addLayout(row)
        self._paint_visibility()

        # commit message
        row2 = QHBoxLayout()
        row2.setSpacing(18)
        lab2 = QLabel("첫 커밋 메시지")
        lab2.setObjectName("setFormLabel")
        lab2.setFixedWidth(148)
        self._edit_msg = QLineEdit(load_last_commit_message())
        self._edit_msg.setObjectName("setInput")
        self._edit_msg.editingFinished.connect(self._save_commit_message)
        row2.addWidget(lab2)
        row2.addWidget(self._edit_msg, 1)
        lay.addLayout(row2)

        # branch
        row3 = QHBoxLayout()
        row3.setSpacing(18)
        lab3 = QLabel("기본 브랜치 이름")
        lab3.setObjectName("setFormLabel")
        lab3.setFixedWidth(148)
        self._edit_branch = QLineEdit(load_last_publish_branch())
        self._edit_branch.setObjectName("setInput")
        self._edit_branch.setFont(_mono(self._edit_branch.font()))
        self._edit_branch.editingFinished.connect(self._save_branch)
        row3.addWidget(lab3)
        row3.addWidget(self._edit_branch, 1)
        lay.addLayout(row3)

        lay.addStretch(1)
        return w

    def _build_safety(self, p: Palette) -> QWidget:
        # Design: column gap 22; secret/PII shown as always-on switch card.
        # Scroll: master-protection card made this page taller than the dialog.
        outer, outer_lay = self._page_shell()
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("setScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(26, 26, 30, 26)
        lay.setSpacing(22)
        lay.addWidget(
            self._heading(
                "안전",
                "실수로 무언가를 공개하지 않도록 돕는 설정입니다.",
            )
        )

        # --- interactive: hide real email ---
        lay.addWidget(
            self._safety_toggle_card(
                switch=self._make_hide_email_switch(),
                title="커밋에 실제 이메일 숨기기",
                body=(
                    "GitHub가 주는 대체 주소를 씁니다. "
                    "컴퓨터에 이미 Git 이메일을 설정해 두었다면 그 값이 우선합니다."
                ),
            )
        )

        # --- secret/PII scan (off only after typed confirmation) ---
        self._sw_secret_scan = _ToggleSwitch(checked=self._secret_scan)
        self._sw_secret_scan.toggled.connect(self._on_secret_scan_toggled)
        lay.addWidget(
            self._safety_toggle_card(
                switch=self._sw_secret_scan,
                title="비밀·개인정보 점검",
                body=(
                    "올리기·동기화 전에 비밀번호·키가 들어 있을 만한 파일 이름과 "
                    "개인정보 후보를 찾아 알려드립니다. "
                    "끄려면 경고 창에서 안내 문구를 그대로 입력해야 합니다."
                ),
            )
        )

        # --- boot notify (시안: CloneUp 시작 알림) ---
        self._boot_notify_on = load_boot_notify_enabled()
        # Pref ↔ HKCU must match: default True used to show ON without Run key.
        self._boot_autostart_on = self._sync_boot_autostart_pref()
        self._sw_boot_notify = _ToggleSwitch(checked=self._boot_notify_on)
        self._sw_boot_notify.toggled.connect(self._on_boot_notify_toggled)
        lay.addWidget(
            self._safety_toggle_card(
                switch=self._sw_boot_notify,
                title="켤 때 안 올린 수정 확인",
                body=(
                    "컴퓨터에 로그인한 뒤, 최근 폴더에 GitHub로 안 보낸 변경이 있으면 "
                    "작은 알림으로 물어봅니다. 알림에서 올려도 비밀 파일 점검은 그대로입니다."
                ),
            )
        )
        self._sw_boot_autostart = _ToggleSwitch(checked=self._boot_autostart_on)
        self._sw_boot_autostart.toggled.connect(self._on_boot_autostart_toggled)
        lay.addWidget(
            self._safety_toggle_card(
                switch=self._sw_boot_autostart,
                title="Windows 시작 시 트레이에서 대기",
                body=(
                    "로그온할 때 클론업을 트레이에만 띄워 위 알림을 확인할 수 있게 합니다. "
                    "끄면 시작 프로그램에서 빼 둡니다."
                ),
            )
        )

        warn = QLabel(
            "파일 이름(과 일부 내용 검사) 범위에는 한계가 있습니다. "
            "파일 안에 적어둔 비밀번호를 모두 찾지는 못하니 마지막 확인은 직접 해주세요. "
            "점검이 켜져 있을 때, 경고를 무시하고 진행하는 것은 "
            "그때그때 올리기·동기화 화면의 「비밀 파일도 진행」에서만 고를 수 있습니다. "
            "키·인증서처럼 명백한 비밀 값은 점검을 꺼도 막을 수 있습니다."
        )
        warn.setObjectName("setWarnBanner")
        warn.setWordWrap(True)
        lay.addWidget(warn)

        # --- 커밋 내역: 읽기 전용 vs 지워지지 않습니다 (되돌리기) ---
        self._sw_history_revert = _ToggleSwitch(checked=self._history_revert)
        self._sw_history_revert.toggled.connect(self._on_history_revert_toggled)
        lay.addWidget(
            self._safety_toggle_card(
                switch=self._sw_history_revert,
                title="커밋 내역에서 되돌리기 허용",
                body=(
                    "꺼져 있으면 커밋 내역은 읽기 전용입니다 (기본값). "
                    "켜면 「이 시점으로 되돌리기」 버튼이 나타납니다 — "
                    "예전 내용을 되살린 새 커밋을 쌓을 뿐, 지금까지의 기록은 "
                    "하나도 지워지지 않습니다. 처음 실행 안내에서도 고를 수 있습니다."
                ),
            )
        )

        # --- master-password token protection ---
        lay.addWidget(self._build_master_protection_card())

        lay.addStretch(1)
        scroll.setWidget(w)
        outer_lay.addWidget(scroll, 1)
        return outer

    def _build_master_protection_card(self) -> QFrame:
        """Settings → 안전: encrypt stored PAT with master password + DPAPI."""
        card = QFrame()
        card.setObjectName("setCard")
        col = QVBoxLayout(card)
        col.setContentsMargins(17, 15, 17, 15)
        col.setSpacing(10)

        tt = QLabel("마스터 비밀번호로 키 보호")
        tt.setObjectName("setCardTitle")
        col.addWidget(tt)

        body = QLabel(
            "이 PC에 저장된 GitHub 키를 추가로 암호화합니다. "
            "일상적으로 올리기·받기를 할 때는 비밀번호를 묻지 않고, "
            "지금 로그인한 Windows 계정으로만 잠금을 풉니다. "
            "설정에서 켜고·바꾸고·끌 때만 마스터 비밀번호를 입력합니다. "
            "마스터 비밀번호 자체는 디스크에 저장되지 않습니다."
        )
        body.setObjectName("setBody")
        body.setWordWrap(True)
        col.addWidget(body)

        self._master_status = QLabel("")
        self._master_status.setObjectName("setMeta")
        self._master_status.setWordWrap(True)
        col.addWidget(self._master_status)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._btn_master_enable = QPushButton("보호 켜기")
        self._btn_master_enable.setObjectName("setSecondary")
        self._btn_master_enable.clicked.connect(self._do_master_enable)
        self._btn_master_change = QPushButton("비밀번호 바꾸기")
        self._btn_master_change.setObjectName("setSecondary")
        self._btn_master_change.clicked.connect(self._do_master_change)
        self._btn_master_disable = QPushButton("보호 끄기")
        self._btn_master_disable.setObjectName("setDangerOutline")
        self._btn_master_disable.clicked.connect(self._do_master_disable)
        for b in (
            self._btn_master_enable,
            self._btn_master_change,
            self._btn_master_disable,
        ):
            b.setSizePolicy(
                QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            )
            row.addWidget(b)
        row.addStretch(1)
        col.addLayout(row)

        self._refresh_master_protection()
        return card

    def _refresh_master_protection(self) -> None:
        on = master_protection_enabled()
        enc = is_token_encrypted()
        if on:
            extra = " · 저장된 키는 암호화됨" if enc else " · 저장된 키 없음(다음에 연결하면 암호화)"
            self._master_status.setText(f"현재: 켜짐{extra}")
        else:
            self._master_status.setText(
                "현재: 꺼짐 (OS 키링에 저장 — 추가 암호화 없음)"
            )
        self._btn_master_enable.setEnabled(not on)
        self._btn_master_change.setEnabled(on)
        self._btn_master_disable.setEnabled(on)

    @Slot()
    def _do_master_enable(self) -> None:
        if master_protection_enabled():
            self._refresh_master_protection()
            return
        pw = prompt_master_password_enable(self)
        if pw is None:
            return
        QGuiApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            enable_master_protection(pw)
        except VaultError as e:
            QMessageBox.warning(
                self,
                "보호 켜기 실패",
                format_error_popup_body(
                    str(e),
                    lead="마스터 보호를 켤 수 없어요.",
                ),
            )
            return
        except Exception as e:  # noqa: BLE001 — surface unexpected crypto/IO
            QMessageBox.warning(
                self,
                "보호 켜기 실패",
                format_error_popup_body(
                    str(e),
                    lead="마스터 보호를 켜는 중 예상치 못한 오류가 났어요.",
                ),
            )
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        QMessageBox.information(
            self,
            "보호 켜짐",
            "마스터 비밀번호 보호가 켜졌습니다.\n"
            "일상 사용 시에는 비밀번호를 다시 묻지 않습니다.\n"
            "비밀번호는 잊어버리지 마세요 — 복구 방법이 없습니다.",
        )
        self._refresh_master_protection()

    @Slot()
    def _do_master_change(self) -> None:
        if not master_protection_enabled():
            self._refresh_master_protection()
            return
        pair = prompt_master_password_change(self)
        if pair is None:
            return
        old_pw, new_pw = pair
        QGuiApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            change_master_password(old_pw, new_pw)
        except VaultError as e:
            QMessageBox.warning(
                self,
                "비밀번호 바꾸기 실패",
                format_error_popup_body(
                    str(e),
                    lead="마스터 비밀번호를 바꾸지 못했어요.",
                ),
            )
            return
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "비밀번호 바꾸기 실패",
                format_error_popup_body(
                    str(e),
                    lead="비밀번호를 바꾸는 중 예상치 못한 오류가 났어요.",
                ),
            )
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        QMessageBox.information(
            self,
            "비밀번호 변경됨",
            "마스터 비밀번호가 바뀌었습니다.",
        )
        self._refresh_master_protection()

    @Slot()
    def _do_master_disable(self) -> None:
        if not master_protection_enabled():
            self._refresh_master_protection()
            return
        pw = prompt_master_password_disable(self)
        if pw is None:
            return
        QGuiApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            disable_master_protection(pw)
        except VaultError as e:
            QMessageBox.warning(
                self,
                "보호 끄기 실패",
                format_error_popup_body(
                    str(e),
                    lead="마스터 보호를 끌 수 없어요.",
                ),
            )
            return
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "보호 끄기 실패",
                format_error_popup_body(
                    str(e),
                    lead="마스터 보호를 끄는 중 예상치 못한 오류가 났어요.",
                ),
            )
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        QMessageBox.information(
            self,
            "보호 꺼짐",
            "마스터 비밀번호 보호가 꺼졌습니다.\n"
            "GitHub 키는 다시 OS 키링에만 보관됩니다.",
        )
        self._refresh_master_protection()

    def _make_hide_email_switch(self) -> _ToggleSwitch:
        self._sw_hide_email = _ToggleSwitch(checked=self._hide_email)
        self._sw_hide_email.toggled.connect(self._on_hide_email_toggled)
        return self._sw_hide_email

    def _safety_toggle_card(
        self,
        *,
        switch: _ToggleSwitch,
        title: str,
        body: str,
    ) -> QFrame:
        """One design toggle row: switch + title/body (시안 안전 카드)."""
        card = QFrame()
        card.setObjectName("setCard")
        tr = QHBoxLayout(card)
        tr.setContentsMargins(17, 15, 17, 15)
        tr.setSpacing(14)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)
        tt = QLabel(title)
        tt.setObjectName("setCardTitle")
        tb = QLabel(body)
        tb.setObjectName("setBody")
        tb.setWordWrap(True)
        text_col.addWidget(tt)
        text_col.addWidget(tb)
        tr.addWidget(switch, 0, Qt.AlignmentFlag.AlignTop)
        tr.addLayout(text_col, 1)
        return card

    def _build_folders(self, p: Palette) -> QWidget:
        w, lay = self._page_shell()
        lay.addWidget(
            self._heading(
                "최근 폴더",
                "폴더 고르는 칸에 나오는 목록입니다. 최대 12개까지 기억합니다.",
            )
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("setScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._folders_host = QWidget()
        self._folders_layout = QVBoxLayout(self._folders_host)
        self._folders_layout.setContentsMargins(0, 0, 0, 0)
        self._folders_layout.setSpacing(6)
        self._folders_layout.addStretch(1)
        scroll.setWidget(self._folders_host)
        lay.addWidget(scroll, 1)

        row = QHBoxLayout()
        row.setSpacing(14)
        self._btn_clear_recent = QPushButton("목록 비우기")
        self._btn_clear_recent.setObjectName("setSecondary")
        self._btn_clear_recent.clicked.connect(self._clear_recent)
        note = QLabel(
            "컴퓨터·외장디스크에 있는 실제 폴더는 삭제되지 않습니다."
        )
        note.setObjectName("setMeta")
        note.setWordWrap(True)
        row.addWidget(self._btn_clear_recent)
        row.addWidget(note, 1)
        lay.addLayout(row)
        return w

    def _build_terms(self, p: Palette) -> QWidget:
        """Built-in glossary + user-added terms (「+」). Product UI words kept."""
        w, lay = self._page_shell()
        lay.setSpacing(14)

        head_row = QHBoxLayout()
        head_row.setSpacing(12)
        head_row.addWidget(
            self._heading(
                "용어 안내",
                "화면에 보이는 말을 짧게 풀어 둡니다. "
                "commit, push, staging 같은 말도 함께 적습니다. "
                "「+」로 나만의 용어를 추가할 수 있습니다.",
            ),
            1,
        )
        self._btn_add_term = QPushButton("+")
        self._btn_add_term.setObjectName("setSecondary")
        self._btn_add_term.setFixedSize(36, 36)
        self._btn_add_term.setToolTip(
            "용어 추가\n이 컴퓨터에만 저장됩니다."
        )
        self._btn_add_term.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_add_term.clicked.connect(self._on_add_glossary_term)
        head_row.addWidget(
            self._btn_add_term, 0, Qt.AlignmentFlag.AlignTop
        )
        lay.addLayout(head_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("setScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._terms_scroll = scroll
        self._terms_host = QWidget()
        self._terms_host_l = QVBoxLayout(self._terms_host)
        self._terms_host_l.setContentsMargins(0, 0, 0, 0)
        self._terms_host_l.setSpacing(10)
        scroll.setWidget(self._terms_host)
        lay.addWidget(scroll, 1)

        self._rebuild_terms_list()
        return w

    def _glossary_card(
        self,
        p: Palette,
        *,
        term: str,
        one_line: str,
        detail: str,
        user_owned: bool,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("setCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(15, 13, 15, 13)
        cl.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        t = QLabel(term)
        t.setObjectName("setCardTitle")
        t.setWordWrap(True)
        title_row.addWidget(t, 1)
        if user_owned:
            badge = QLabel("내 용어")
            badge.setStyleSheet(
                f"font-size: 11px; font-weight: 600; color: {p.primary}; "
                f"background: {p.bg_window}; padding: 2px 8px; border-radius: 4px;"
            )
            title_row.addWidget(badge, 0)
            btn_del = QPushButton("삭제")
            btn_del.setObjectName("setSecondary")
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setToolTip("이 컴퓨터에서 이 용어만 지웁니다.")
            btn_del.clicked.connect(
                lambda _=False, name=term: self._on_remove_glossary_term(name)
            )
            title_row.addWidget(btn_del, 0)
        cl.addLayout(title_row)

        one = QLabel(one_line)
        one.setObjectName("setBody")
        one.setWordWrap(True)
        one.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {p.text};"
        )
        cl.addWidget(one)
        if detail.strip():
            d = QLabel(detail)
            d.setObjectName("setMeta")
            d.setWordWrap(True)
            d.setStyleSheet(f"font-size: 12px; color: {p.text_muted};")
            cl.addWidget(d)
        return card

    def _rebuild_terms_list(self) -> None:
        """Fill scroll host: built-in cards, then user cards, then hint."""
        if not hasattr(self, "_terms_host_l") or self._terms_host_l is None:
            return
        p = active_palette()
        lay = self._terms_host_l
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for term, one_line, detail in GLOSSARY_ENTRIES:
            lay.addWidget(
                self._glossary_card(
                    p,
                    term=term,
                    one_line=one_line,
                    detail=detail,
                    user_owned=False,
                )
            )

        user_rows = load_user_glossary()
        if user_rows:
            sec = QLabel("내가 추가한 용어")
            sec.setObjectName("setSection")
            lay.addWidget(sec)
            for term, one_line, detail in user_rows:
                lay.addWidget(
                    self._glossary_card(
                        p,
                        term=term,
                        one_line=one_line,
                        detail=detail,
                        user_owned=True,
                    )
                )

        n_user = len(user_rows)
        # Count line only when the user has registered at least one term.
        if n_user > 0:
            hint = QLabel(
                f"내 용어 {n_user}개 · 이 컴퓨터에만 저장됩니다."
            )
            hint.setObjectName("setMeta")
            hint.setWordWrap(True)
            lay.addWidget(hint)
        lay.addStretch(1)

        if hasattr(self, "_btn_add_term") and self._btn_add_term is not None:
            self._btn_add_term.setEnabled(True)

    @Slot()
    def _on_add_glossary_term(self) -> None:
        p = active_palette()
        dlg = QDialog(self)
        dlg.setWindowTitle("용어 추가")
        dlg.setModal(True)
        dlg.setMinimumWidth(420)
        root = QVBoxLayout(dlg)
        root.setSpacing(10)
        root.setContentsMargins(18, 16, 18, 14)

        lab = QLabel(
            "내가 헷갈리는 말을 짧게 적어 두세요. "
            "앱에 기본으로 들어 있는 용어는 그대로 두고, 아래에 덧붙입니다."
        )
        lab.setWordWrap(True)
        lab.setStyleSheet(f"color: {p.text_secondary}; font-size: 12.5px;")
        root.addWidget(lab)

        def _field(title: str, placeholder: str, *, multi: bool = False):
            t = QLabel(title)
            t.setObjectName("setFormLabel")
            root.addWidget(t)
            if multi:
                edit = QPlainTextEdit()
                edit.setPlaceholderText(placeholder)
                edit.setFixedHeight(88)
            else:
                edit = QLineEdit()
                edit.setPlaceholderText(placeholder)
                edit.setClearButtonEnabled(True)
            root.addWidget(edit)
            return edit

        edit_term = _field("용어", f"예: staging (최대 {USER_GLOSSARY_TERM_MAX}자)")
        edit_one = _field(
            "한 줄 요약",
            f"예: 다음에 커밋에 넣을 장을 고르는 자리 (최대 {USER_GLOSSARY_LINE_MAX}자)",
        )
        edit_detail = _field(
            "긴 설명 (선택)",
            f"더 자세한 메모 (최대 {USER_GLOSSARY_DETAIL_MAX}자)",
            multi=True,
        )

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("추가")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        root.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        term = edit_term.text().strip()
        one = edit_one.text().strip()
        detail = edit_detail.toPlainText().strip()
        if not term or not one:
            QMessageBox.warning(
                self, "입력 부족", "용어와 한 줄 요약은 꼭 적어 주세요."
            )
            return
        if not add_user_glossary_entry(term, one, detail):
            QMessageBox.warning(
                self,
                "추가하지 못함",
                "이름이 비었거나, 이미 같은 이름이 있습니다.\n"
                "다른 이름으로 다시 적어 주세요.",
            )
            return
        self._rebuild_terms_list()

    @Slot()
    def _on_remove_glossary_term(self, term: str) -> None:
        reply = QMessageBox.question(
            self,
            "용어 삭제",
            f"「{term}」을(를) 이 컴퓨터에서 지울까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if remove_user_glossary_entry(term):
            self._rebuild_terms_list()

    def _build_about(self, p: Palette) -> QWidget:
        w, lay = self._page_shell()
        lay.addWidget(
            self._heading("정보", "이 앱과 연결된 프로그램들입니다.")
        )

        from app import __version__

        git_ver = "(확인 불가)"
        try:
            _path, ver = require_git()
            git_ver = ".".join(str(x) for x in ver)
        except Exception:
            pass

        facts = [
            ("클론업", __version__),
            ("Git", git_ver),
            ("설정 저장 위치", "레지스트리 CloneUp"),
            ("통신 대상", "github.com · api.github.com"),
        ]
        for key, val in facts:
            row = QFrame()
            row.setObjectName("setFactRow")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(15, 11, 15, 11)
            k = QLabel(key)
            k.setObjectName("setMeta")
            v = QLabel(val)
            v.setObjectName("setFactVal")
            v.setFont(_mono(v.font()))
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            hl.addWidget(k)
            hl.addWidget(v, 1)
            lay.addWidget(row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        btn_onb = QPushButton("시작 안내 다시 보기")
        btn_onb.setObjectName("setSecondary")
        btn_onb.clicked.connect(self._open_onboarding)
        btn_terms = QPushButton("이용약관")
        btn_terms.setObjectName("setSecondary")
        btn_terms.clicked.connect(self._open_terms)
        btn_license = QPushButton("라이선스")
        btn_license.setObjectName("setSecondary")
        btn_license.clicked.connect(self._open_license)
        btn_oss = QPushButton("오픈소스 고지")
        btn_oss.setObjectName("setSecondary")
        btn_oss.clicked.connect(self._open_oss_notices)
        actions.addWidget(btn_onb)
        actions.addWidget(btn_terms)
        actions.addWidget(btn_license)
        actions.addWidget(btn_oss)
        actions.addStretch(1)
        lay.addLayout(actions)
        lay.addStretch(1)
        return w

    # ----- account actions -----
    def _refresh_account(self, *, live: bool = True) -> None:
        """
        Paint account card from keyring.

        ``live=True`` (default): ask GitHub once so Settings reflects
        X-OAuth-Scopes after web-side token changes / last API refresh.
        """
        p = active_palette()
        if live and is_logged_in():
            # Best-effort; failures keep previous keyring values.
            refresh_scopes_from_github()
        logged = is_logged_in()
        login = load_last_github_login() or ""
        if logged:
            self._acct_dot.setStyleSheet(f"color: {p.primary}; font-size: 10px;")
            name = login or "(사용자)"
            self._acct_title.setText(f"{name} 으로 로그인됨")
            scope_raw = (load_scope() or "").strip() or SCOPE_UNKNOWN
            pretty = format_scopes_display(scope_raw)
            if not pretty:
                scope_s = "권한 확인 불가"
            else:
                scope_s = f"권한 {pretty}"
            kind = load_auth_kind()
            if kind == AUTH_KIND_PAT:
                kind_s = "개인 액세스 토큰"
            elif kind == AUTH_KIND_DEVICE:
                kind_s = "장치 코드"
            else:
                kind_s = "연결됨"
            self._acct_meta.setText(f"{scope_s} · {kind_s}")
            self._btn_relogin.show()
            self._btn_logout.show()
            self._btn_connect.hide()
            self._btn_refresh_scopes.show()
            self._btn_pat_list.show()
        else:
            self._acct_dot.setStyleSheet(f"color: {p.text_disabled}; font-size: 10px;")
            self._acct_title.setText("GitHub에 연결되지 않음")
            self._acct_meta.setText("연결하면 올리기·비공개 받기를 쓸 수 있습니다.")
            self._btn_relogin.hide()
            self._btn_logout.hide()
            self._btn_connect.show()
            self._btn_refresh_scopes.hide()
            # Key list is on GitHub account — useful even before CloneUp login.
            self._btn_pat_list.show()

    @Slot()
    def _open_github_pat_list(self) -> None:
        """Open GitHub's PAT list page (full key inventory lives only there)."""
        QDesktopServices.openUrl(QUrl(PAT_LIST_URL))

    @Slot()
    def _do_relogin(self) -> None:
        # Close settings so the login wizard is on top of the main window
        self.accept()
        if self._on_login is not None:
            self._on_login()

    @Slot()
    def _do_logout(self) -> None:
        if self._on_logout is not None:
            self._on_logout()
        self._refresh_account(live=False)

    @Slot()
    def _do_refresh_scopes(self) -> None:
        if not is_logged_in():
            self._refresh_account(live=False)
            return
        self._acct_meta.setText("GitHub에서 권한 확인 중…")
        before_raw = (load_scope() or "").strip()
        before = format_scopes_display(before_raw) or before_raw or "(없음)"
        scope, user = refresh_scopes_from_github()
        self._refresh_account(live=False)
        if not is_logged_in():
            QMessageBox.warning(
                self,
                "연결 끊김",
                "저장된 키가 만료·취소된 것 같습니다.\n"
                "「GitHub 연결」로 새 키를 붙여 넣으세요.",
            )
            return
        after_raw = (scope or load_scope() or "").strip()
        after = format_scopes_display(after_raw) or after_raw or "(없음)"
        if user and user.get("login"):
            from app.ui.settings_store import save_last_github_login

            save_last_github_login(str(user["login"]))
            self._acct_title.setText(f"{user['login']} 으로 로그인됨")

        issued = format_connected_at_display(load_connected_at_raw())
        expires = format_expires_display(load_expires_at_raw())
        pat_note = (load_pat_note() or "").strip() or "기록 없음"

        lines: list[str] = []
        if (
            after_raw == SCOPE_UNKNOWN
            or after_raw == "unknown"
            or not format_scopes_display(after_raw)
        ):
            lines.append(
                "부여된 권한: 확인 불가 "
                "(세분 키이거나 GitHub이 classic 목록을 주지 않음)"
            )
        elif before != after:
            lines.append(f"부여된 권한: {after}")
            lines.append(f"(이전: {before} → 지금 맞춤)")
        else:
            lines.append(f"부여된 권한: {after}")
        lines.append(f"발급일시: {issued}")
        lines.append(f"유효기간(추정): {expires}")
        lines.append(f"Note 이름: {pat_note}")
        QMessageBox.information(self, "권한 다시 확인", "\n".join(lines))

    # ----- defaults -----
    def _set_private(self, private: bool) -> None:
        self._private = bool(private)
        save_last_private(self._private)
        self._paint_visibility()
        self._notify_prefs("private")

    def _paint_visibility(self) -> None:
        p = active_palette()
        priv = self._private
        if priv:
            self._btn_priv.setStyleSheet(
                f"QPushButton#setChoiceCard {{"
                f"text-align: left; padding: 11px 13px; border-radius: 6px; "
                f"border: 1px solid {p.primary}; background: {p.bg_muted}; "
                f"font-size: 13px; color: {p.text};}}"
            )
            self._btn_pub.setStyleSheet(
                f"QPushButton#setChoiceCard {{"
                f"text-align: left; padding: 11px 13px; border-radius: 6px; "
                f"border: 1px solid {p.border_input}; background: {p.bg_window}; "
                f"font-size: 13px; color: {p.text};}}"
            )
            self._vis_note.setText("권장. 나중에 공개로 바꿀 수 있습니다.")
            self._vis_note.setStyleSheet(f"color: {p.text_muted}; font-size: 11.5px;")
        else:
            self._btn_priv.setStyleSheet(
                f"QPushButton#setChoiceCard {{"
                f"text-align: left; padding: 11px 13px; border-radius: 6px; "
                f"border: 1px solid {p.border_input}; background: {p.bg_window}; "
                f"font-size: 13px; color: {p.text};}}"
            )
            # Dark Settings mock: public selected bg #2e2a1e + warn border
            self._btn_pub.setStyleSheet(
                f"QPushButton#setChoiceCard {{"
                f"text-align: left; padding: 11px 13px; border-radius: 6px; "
                f"border: 1px solid {p.warn_border}; background: {_warn_soft_bg(p)}; "
                f"font-size: 13px; color: {p.text};}}"
            )
            self._vis_note.setText(
                "올리는 순간 인터넷에 공개되고, 지워도 완전히 거두기 어렵습니다."
            )
            self._vis_note.setStyleSheet(
                f"color: {p.warn_text}; font-size: 11.5px;"
            )

    @Slot()
    def _save_commit_message(self) -> None:
        text = (self._edit_msg.text() or "").strip()
        if text:
            save_last_commit_message(text)
            self._notify_prefs("message")

    @Slot()
    def _save_branch(self) -> None:
        text = (self._edit_branch.text() or "").strip()
        if text:
            save_last_publish_branch(text)
            self._notify_prefs("branch")

    # ----- safety -----
    @Slot(bool)
    def _on_hide_email_toggled(self, checked: bool) -> None:
        self._hide_email = bool(checked)
        save_hide_real_email(self._hide_email)
        self._notify_prefs("hide_email")

    @Slot(bool)
    def _on_secret_scan_toggled(self, checked: bool) -> None:
        if self._secret_scan_block:
            return
        want_on = bool(checked)
        if want_on:
            self._secret_scan = True
            save_secret_pii_scan_enabled(True)
            self._notify_prefs("secret_scan")
            return
        # Turning OFF requires typed acknowledgment
        if not confirm_disable_secret_pii_scan(self):
            self._secret_scan_block = True
            try:
                self._sw_secret_scan.setChecked(True, emit=False)
            finally:
                self._secret_scan_block = False
            return
        self._secret_scan = False
        save_secret_pii_scan_enabled(False)
        self._notify_prefs("secret_scan")

    @Slot(bool)
    def _on_history_revert_toggled(self, checked: bool) -> None:
        self._history_revert = bool(checked)
        save_history_revert_enabled(self._history_revert)
        self._notify_prefs("history_revert")

    @Slot(bool)
    def _on_boot_notify_toggled(self, checked: bool) -> None:
        self._boot_notify_on = bool(checked)
        save_boot_notify_enabled(self._boot_notify_on)
        if self._boot_notify_on:
            # Clearing snooze when user turns notify back on.
            save_boot_notify_snooze_until(None)
        self._notify_prefs("boot_notify")

    def _sync_boot_autostart_pref(self) -> bool:
        """Apply preference to HKCU; if register fails, store False so UI is honest."""
        import sys

        want = load_boot_autostart_enabled()
        ok = apply_autostart_preference(want)
        if sys.platform == "win32" and want and not ok:
            save_boot_autostart_enabled(False)
            return False
        if sys.platform == "win32" and want and not is_autostart_registered():
            save_boot_autostart_enabled(False)
            return False
        return bool(want)

    @Slot(bool)
    def _on_boot_autostart_toggled(self, checked: bool) -> None:
        self._boot_autostart_on = bool(checked)
        save_boot_autostart_enabled(self._boot_autostart_on)
        ok = set_autostart_registered(self._boot_autostart_on)
        if not ok and self._boot_autostart_on:
            self._boot_autostart_on = False
            save_boot_autostart_enabled(False)
            self._sw_boot_autostart.setChecked(False, emit=False)
            QMessageBox.warning(
                self,
                "시작 프로그램",
                format_error_popup_body(
                    "Windows 시작 항목을 등록하지 못했습니다.",
                    lead="시작 프로그램 등록에 실패했어요.",
                ),
            )
        self._notify_prefs("boot_autostart")

    # ----- folders -----
    def _refresh_folders(self) -> None:
        while self._folders_layout.count():
            item = self._folders_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        paths = load_recent_folders()
        if not paths:
            empty = QLabel("최근 폴더가 없습니다.")
            empty.setObjectName("setMeta")
            self._folders_layout.addWidget(empty)
        else:
            for path in paths:
                row = QFrame()
                row.setObjectName("setRecentRow")
                hl = QHBoxLayout(row)
                hl.setContentsMargins(14, 10, 14, 10)
                lab = QLabel(path)
                lab.setObjectName("setRecentPath")
                lab.setFont(_mono(lab.font()))
                lab.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                lab.setToolTip(path)
                # full path, no mid-elide (product rule)
                lab.setWordWrap(False)
                hl.addWidget(lab, 1)
                self._folders_layout.addWidget(row)
        self._folders_layout.addStretch(1)
        self._btn_clear_recent.setEnabled(bool(paths))

    @Slot()
    def _clear_recent(self) -> None:
        n = len(load_recent_folders())
        if n == 0:
            return
        r = QMessageBox.question(
            self,
            "목록 비우기",
            f"최근 폴더 {n}개를 이 목록에서만 지울까요?\n\n"
            "CloneUp이 기억한 경로만 사라집니다.\n"
            "컴퓨터에 있는 실제 폴더·파일은 삭제되지 않습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        clear_recent_folders()
        self._refresh_folders()
        self._notify_prefs("recent")

    # ----- about -----
    @Slot()
    def _open_onboarding(self) -> None:
        self.accept()
        if self._on_open_onboarding is not None:
            self._on_open_onboarding()

    def _resolve_legal_path(self, *candidates: Path) -> Path | None:
        """First existing file among candidates (dev tree / frozen / install)."""
        for path in candidates:
            if path.is_file():
                return path
        return None

    def _show_text_document(self, title: str, text: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(560, 480)
        dlg.resize(640, 560)
        vl = QVBoxLayout(dlg)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        view.setFont(_mono(view.font()))
        vl.addWidget(view, 1)
        close = QPushButton("닫기")
        close.clicked.connect(dlg.accept)
        vl.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _open_legal_file(
        self,
        title: str,
        candidates: list[Path],
        missing_message: str,
    ) -> None:
        path = self._resolve_legal_path(*candidates)
        if path is None:
            QMessageBox.information(self, title, missing_message)
            return
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as e:
            QMessageBox.warning(
                self,
                title,
                format_error_popup_body(
                    str(e),
                    lead="문서를 열지 못했어요.",
                ),
            )
            return
        self._show_text_document(title, text)

    @Slot()
    def _open_terms(self) -> None:
        root = app_root()
        self._open_legal_file(
            "이용약관",
            [
                root / "legal" / "CloneUp_Terms_ko.txt",
                # frozen installer may place under same tree
                root / "installer" / "license" / "CloneUp_Terms_ko.txt",
                # onedir: LICENSE next to exe, legal sometimes under parent
                root.parent / "legal" / "CloneUp_Terms_ko.txt",
            ],
            "이용약관 파일을 찾지 못했습니다.\n설치 시 약관에 동의하셨습니다.",
        )

    @Slot()
    def _open_license(self) -> None:
        """Apache License 2.0 (repo root LICENSE; also shipped next to install)."""
        root = app_root()
        self._open_legal_file(
            "라이선스 (Apache 2.0)",
            [
                root / "LICENSE",
                root.parent / "LICENSE",  # install: exe folder if MEIPASS=_internal
                root / "legal" / "LICENSE",
            ],
            "라이선스 파일을 찾지 못했습니다.\n"
            "저장소 LICENSE 또는 설치 폴더의 LICENSE를 확인해 주세요.",
        )

    @Slot()
    def _open_oss_notices(self) -> None:
        """Third-party OSS notices promised in terms §16."""
        root = app_root()
        self._open_legal_file(
            "오픈소스 고지",
            [
                root / "legal" / "CloneUp_OpenSourceNotices_ko.txt",
                root.parent / "legal" / "CloneUp_OpenSourceNotices_ko.txt",
            ],
            "오픈소스 고지 파일을 찾지 못했습니다.\n"
            "legal/CloneUp_OpenSourceNotices_ko.txt 를 확인해 주세요.",
        )

    # ----- style -----
    @staticmethod
    def _dialog_qss(p: Palette) -> str:
        """QSS from light 설정 + dark Settings Dark mocks (palette-driven)."""
        warn_bg = _warn_soft_bg(p)
        danger_fg = _danger_label(p)
        danger_hover = _danger_hover_bg(p)
        # Title bar label: dark mock #eae5d9 (near text)
        title_fg = "#eae5d9" if p.name == "dark" else p.text
        return f"""
        QDialog {{
            background: {p.bg_window};
            color: {p.text};
        }}
        QFrame#setTitleBar, QFrame#setFooter {{
            background: {p.bg_bar};
            border: none;
        }}
        QFrame#setTitleBar {{
            border-bottom: 1px solid {p.border_soft};
        }}
        QFrame#setFooter {{
            border-top: 1px solid {p.border_divider};
        }}
        QLabel#setTitle {{
            font-size: 13px;
            font-weight: 600;
            color: {title_fg};
        }}
        QFrame#setNav {{
            background: {p.bg_bar};
            border-right: 1px solid {p.border_soft};
        }}
        QLabel#setHeading {{
            font-size: 16px;
            font-weight: 600;
            color: {p.text};
        }}
        QLabel#setSub {{
            font-size: 12.5px;
            color: {p.text_muted};
        }}
        QLabel#setSection {{
            font-size: 13px;
            font-weight: 600;
            color: {p.text_secondary};
        }}
        QLabel#setFormLabel {{
            font-size: 13px;
            color: {p.text_secondary};
        }}
        QLabel#setMeta {{
            font-size: 11.5px;
            color: {p.text_muted};
        }}
        QLabel#setBody {{
            font-size: 12.5px;
            color: {p.text_secondary};
        }}
        QLabel#setCardTitle {{
            font-size: 13.5px;
            font-weight: 600;
            color: {p.text};
        }}
        QFrame#setCard {{
            background: {p.bg_muted};
            border: 1px solid {p.border_soft};
            border-radius: 8px;
        }}
        QLabel#setBanner {{
            background: {p.bg_hint};
            border-left: 3px solid {p.primary};
            border-radius: 0 6px 6px 0;
            padding: 13px 15px;
            font-size: 12.5px;
            color: {p.text_secondary};
        }}
        QLabel#setWarnBanner {{
            background: {warn_bg};
            border-left: 3px solid {p.warn_border};
            border-radius: 0 6px 6px 0;
            padding: 13px 15px;
            font-size: 12.5px;
            color: {p.text_secondary};
        }}
        QLabel#setInfoBox {{
            background: {p.bg_input};
            border: 1px solid {p.border_divider};
            border-radius: 6px;
            padding: 13px 15px;
            font-size: 12.5px;
            color: {p.text_secondary};
        }}
        QLineEdit#setInput {{
            background: {p.bg_input};
            border: 1px solid {p.border_input};
            border-radius: 5px;
            padding: 6px 12px;
            font-size: 13px;
            color: {p.text};
            min-height: 20px;
            selection-background-color: {p.primary};
        }}
        QFrame#setFactRow {{
            background: {p.bg_muted};
            border-radius: 6px;
        }}
        QLabel#setFactVal {{
            font-size: 12.5px;
            color: {p.text};
        }}
        QFrame#setRecentRow {{
            background: {p.bg_input};
            border: 1px solid {p.border_divider};
            border-radius: 6px;
        }}
        QLabel#setRecentPath {{
            font-size: 12.5px;
            color: {p.text};
        }}
        QScrollArea#setScroll {{
            background: transparent;
            border: none;
        }}
        QPushButton#setSecondary {{
            background: {p.bg_window};
            color: {title_fg};
            border: 1px solid {p.border_outline};
            border-radius: 5px;
            padding: 6px 14px;
            font-size: 12.5px;
            min-height: 20px;
        }}
        QPushButton#setSecondary:hover {{
            background: {p.bg_hint};
        }}
        QPushButton#setDangerOutline {{
            background: {p.bg_window};
            color: {danger_fg};
            border: 1px solid {p.border_outline};
            border-radius: 5px;
            padding: 6px 14px;
            font-size: 12.5px;
            min-height: 20px;
        }}
        QPushButton#setDangerOutline:hover {{
            background: {danger_hover};
        }}
        """


def _pw_field(placeholder: str = "") -> QLineEdit:
    edit = QLineEdit()
    edit.setObjectName("setInput")
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    edit.setClearButtonEnabled(True)
    if placeholder:
        edit.setPlaceholderText(placeholder)
    return edit


def _master_pw_ok(password: str) -> bool:
    return len((password or "").strip()) >= _MASTER_PW_MIN_LEN


def prompt_master_password_enable(parent: QWidget | None = None) -> str | None:
    """Ask for a new master password (+ confirm). Returns password or None."""
    p = active_palette()
    dlg = QDialog(parent)
    dlg.setWindowTitle("마스터 비밀번호 설정")
    dlg.setModal(True)
    dlg.setMinimumWidth(440)
    root = QVBoxLayout(dlg)
    root.setSpacing(12)

    title = QLabel("보호에 쓸 마스터 비밀번호")
    title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {p.text};")
    root.addWidget(title)

    info = QLabel(
        "이 비밀번호는 디스크에 저장되지 않습니다. "
        f"최소 {_MASTER_PW_MIN_LEN}자, 잊어버리면 보호를 끄거나 "
        "키를 다시 연결해야 할 수 있습니다."
    )
    info.setWordWrap(True)
    info.setStyleSheet(f"color: {p.text_secondary}; font-size: 12.5px;")
    root.addWidget(info)

    form = QFormLayout()
    form.setSpacing(8)
    pw1 = _pw_field("새 비밀번호")
    pw2 = _pw_field("새 비밀번호 확인")
    form.addRow("비밀번호", pw1)
    form.addRow("확인", pw2)
    root.addLayout(form)

    err = QLabel("")
    err.setStyleSheet(f"color: {_danger_label(p)}; font-size: 12px;")
    err.setWordWrap(True)
    root.addWidget(err)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
    cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    if ok_btn is not None:
        ok_btn.setText("보호 켜기")
        ok_btn.setEnabled(False)
    if cancel_btn is not None:
        cancel_btn.setText("취소")
    root.addWidget(buttons)

    def _sync() -> None:
        a, b = pw1.text(), pw2.text()
        msg = ""
        ready = False
        if a or b:
            if not _master_pw_ok(a):
                msg = f"비밀번호는 {_MASTER_PW_MIN_LEN}자 이상이어야 합니다."
            elif a != b:
                msg = "확인 비밀번호가 일치하지 않습니다."
            else:
                ready = True
        err.setText(msg)
        if ok_btn is not None:
            ok_btn.setEnabled(ready)

    pw1.textChanged.connect(lambda _t: _sync())
    pw2.textChanged.connect(lambda _t: _sync())
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    if not _master_pw_ok(pw1.text()) or pw1.text() != pw2.text():
        return None
    return pw1.text()


def prompt_master_password_change(
    parent: QWidget | None = None,
) -> tuple[str, str] | None:
    """Ask for current + new master password. Returns (old, new) or None."""
    p = active_palette()
    dlg = QDialog(parent)
    dlg.setWindowTitle("마스터 비밀번호 바꾸기")
    dlg.setModal(True)
    dlg.setMinimumWidth(440)
    root = QVBoxLayout(dlg)
    root.setSpacing(12)

    title = QLabel("마스터 비밀번호 바꾸기")
    title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {p.text};")
    root.addWidget(title)

    form = QFormLayout()
    form.setSpacing(8)
    old = _pw_field("현재 비밀번호")
    new1 = _pw_field("새 비밀번호")
    new2 = _pw_field("새 비밀번호 확인")
    form.addRow("현재", old)
    form.addRow("새 비밀번호", new1)
    form.addRow("확인", new2)
    root.addLayout(form)

    err = QLabel("")
    err.setStyleSheet(f"color: {_danger_label(p)}; font-size: 12px;")
    err.setWordWrap(True)
    root.addWidget(err)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
    cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    if ok_btn is not None:
        ok_btn.setText("바꾸기")
        ok_btn.setEnabled(False)
    if cancel_btn is not None:
        cancel_btn.setText("취소")
    root.addWidget(buttons)

    def _sync() -> None:
        o, a, b = old.text(), new1.text(), new2.text()
        msg = ""
        ready = False
        if o or a or b:
            if not (o or "").strip():
                msg = "현재 비밀번호를 입력하세요."
            elif not _master_pw_ok(a):
                msg = f"새 비밀번호는 {_MASTER_PW_MIN_LEN}자 이상이어야 합니다."
            elif a != b:
                msg = "확인 비밀번호가 일치하지 않습니다."
            else:
                ready = True
        err.setText(msg)
        if ok_btn is not None:
            ok_btn.setEnabled(ready)

    for e in (old, new1, new2):
        e.textChanged.connect(lambda _t: _sync())
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    if not (old.text() or "").strip() or not _master_pw_ok(new1.text()):
        return None
    if new1.text() != new2.text():
        return None
    return old.text(), new1.text()


def prompt_master_password_disable(parent: QWidget | None = None) -> str | None:
    """Confirm disable with current master password. Returns password or None."""
    p = active_palette()
    dlg = QDialog(parent)
    dlg.setWindowTitle("마스터 보호 끄기")
    dlg.setModal(True)
    dlg.setMinimumWidth(440)
    root = QVBoxLayout(dlg)
    root.setSpacing(12)

    title = QLabel("정말 보호를 끌까요?")
    title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {p.text};")
    root.addWidget(title)

    warn = QLabel(
        "끄면 GitHub 키는 다시 OS 키링에만 보관됩니다 "
        "(추가 AES 암호화는 해제됩니다).\n"
        "나중에 설정 → 안전에서 다시 켤 수 있습니다."
    )
    warn.setWordWrap(True)
    warn.setStyleSheet(
        f"background: {_warn_soft_bg(p)}; border-left: 3px solid {p.warn_border}; "
        f"border-radius: 0 6px 6px 0; padding: 12px 14px; "
        f"color: {p.text_secondary}; font-size: 12.5px;"
    )
    root.addWidget(warn)

    form = QFormLayout()
    pw = _pw_field("현재 마스터 비밀번호")
    form.addRow("비밀번호", pw)
    root.addLayout(form)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
    cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    if ok_btn is not None:
        ok_btn.setText("보호 끄기")
        ok_btn.setEnabled(False)
    if cancel_btn is not None:
        cancel_btn.setText("취소")
    root.addWidget(buttons)

    def _sync() -> None:
        if ok_btn is not None:
            ok_btn.setEnabled(bool((pw.text() or "").strip()))

    pw.textChanged.connect(lambda _t: _sync())
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    pw.returnPressed.connect(
        lambda: dlg.accept() if (pw.text() or "").strip() else None
    )

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    text = pw.text()
    return text if (text or "").strip() else None


def confirm_disable_secret_pii_scan(parent: QWidget | None = None) -> bool:
    """
    Warn + require typing SECRET_SCAN_OFF_PHRASE to disable secret/PII scan.

    Returns True only when the user typed the phrase and accepted.
    """
    p = active_palette()
    dlg = QDialog(parent)
    dlg.setWindowTitle("비밀·개인정보 점검 끄기")
    dlg.setModal(True)
    dlg.setMinimumWidth(480)
    dlg.resize(520, 420)
    root = QVBoxLayout(dlg)
    root.setSpacing(12)

    title = QLabel("정말 점검을 끌까요?")
    title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {p.text};")
    root.addWidget(title)

    warn = QLabel(
        "끄면 올리기·동기화 전에 비밀 파일 이름·개인정보 후보를 "
        "자동으로 막거나 자세히 안내하지 않습니다.\n\n"
        "· 실수로 .env, 키 파일, 전화번호 등이 올라갈 위험이 커집니다.\n"
        "· 키·인증서처럼 명백한 비밀 값은 끄더라도 막을 수 있습니다.\n"
        "· 나중에 설정 → 안전에서 다시 켤 수 있습니다."
    )
    warn.setWordWrap(True)
    warn.setStyleSheet(
        f"background: {_warn_soft_bg(p)}; border-left: 3px solid {p.warn_border}; "
        f"border-radius: 0 6px 6px 0; padding: 12px 14px; "
        f"color: {p.text_secondary}; font-size: 12.5px;"
    )
    root.addWidget(warn)

    prompt = QLabel(
        "아래 안내를 읽고, 다음 문장을 <b>그대로</b> 입력하세요."
    )
    prompt.setWordWrap(True)
    prompt.setTextFormat(Qt.TextFormat.RichText)
    prompt.setStyleSheet(f"color: {p.text_secondary}; font-size: 12.5px;")
    root.addWidget(prompt)

    phrase = QLabel(SECRET_SCAN_OFF_PHRASE)
    phrase.setWordWrap(True)
    phrase.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    phrase.setStyleSheet(
        f"background: {p.bg_input}; border: 1px solid {p.border_divider}; "
        f"border-radius: 6px; padding: 10px 12px; font-size: 13px; "
        f"font-weight: 600; color: {p.text};"
    )
    root.addWidget(phrase)

    edit = QLineEdit()
    edit.setPlaceholderText("위 문장을 그대로 입력")
    edit.setClearButtonEnabled(True)
    root.addWidget(edit)

    hint = QLabel("문장이 일치해야 「끄기」를 누를 수 있습니다.")
    hint.setStyleSheet(f"color: {p.text_muted}; font-size: 11.5px;")
    root.addWidget(hint)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
    cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    if ok_btn is not None:
        ok_btn.setText("끄기")
        ok_btn.setEnabled(False)
    if cancel_btn is not None:
        cancel_btn.setText("취소")
    root.addWidget(buttons)

    def _sync_ok() -> None:
        if ok_btn is not None:
            ok_btn.setEnabled(phrase_matches_secret_scan_off(edit.text()))

    edit.textChanged.connect(lambda _t: _sync_ok())
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    edit.returnPressed.connect(
        lambda: dlg.accept() if phrase_matches_secret_scan_off(edit.text()) else None
    )

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    return phrase_matches_secret_scan_off(edit.text())


def show_settings(
    parent: QWidget | None = None,
    *,
    on_login: Callable[[], None] | None = None,
    on_logout: Callable[[], None] | None = None,
    on_prefs_changed: Callable[..., Any] | None = None,
    on_open_onboarding: Callable[[], None] | None = None,
    initial_tab: int = 0,
) -> None:
    """Open the settings dialog (시안 기준)."""
    dlg = SettingsDialog(
        parent,
        on_login=on_login,
        on_logout=on_logout,
        on_prefs_changed=on_prefs_changed,
        on_open_onboarding=on_open_onboarding,
        initial_tab=initial_tab,
    )
    dlg.exec()
