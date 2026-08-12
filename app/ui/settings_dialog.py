"""Settings dialog — desin/CloneUp 설정.dc.html (+ Settings Dark.dc.html).

Sidebar tabs: 계정 · 올리기 기본값 · 안전 · 최근 폴더 · 정보.
Prefs save immediately (footer: 바꾸면 바로 저장됩니다).
Colors follow active_palette() (OS light/dark).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QRectF, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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

from app.auth.token_store import (
    AUTH_KIND_DEVICE,
    AUTH_KIND_PAT,
    SCOPE_UNKNOWN,
    is_logged_in,
    load_auth_kind,
    load_scope,
)
from app.git.runner import require_git
from app.paths import app_root
from app.ui.settings_store import (
    clear_recent_folders,
    load_hide_real_email,
    load_history_revert_enabled,
    load_last_commit_message,
    load_last_github_login,
    load_last_private,
    load_last_publish_branch,
    load_recent_folders,
    load_secret_pii_scan_enabled,
    save_hide_real_email,
    save_history_revert_enabled,
    save_last_commit_message,
    save_last_private,
    save_last_publish_branch,
    save_secret_pii_scan_enabled,
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
        self.setMinimumSize(820, 540)
        self.resize(880, 620)
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
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addWidget(self._btn_relogin)
        btns.addWidget(self._btn_logout)
        btns.addWidget(self._btn_connect)
        card_l.addLayout(btns)
        lay.addWidget(self._acct_card)

        hint = QLabel(
            "로그아웃하면 이 컴퓨터에 저장된 토큰이 지워집니다. "
            "GitHub 쪽 승인까지 없애려면 GitHub 설정에서 따로 해제해야 합니다."
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
        # Design: column gap 22; secret/PII shown as always-on switch card
        w, lay = self._page_shell()
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

        lay.addStretch(1)
        return w

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
        """Read-only beginner glossary — product UI words kept as-is."""
        w, lay = self._page_shell()
        lay.setSpacing(14)
        lay.addWidget(
            self._heading(
                "용어 안내",
                "명령어 사전이 아니라, 왜 쓰는지·언제 쓰는지·뭐가 위험한지를 "
                "화면 말 그대로 풀어 둡니다. 버튼·탭 이름은 바꾸지 않습니다. "
                "시작 안내(도움말)와 같은 감각입니다.",
            )
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("setScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        host_l = QVBoxLayout(host)
        host_l.setContentsMargins(0, 0, 0, 0)
        host_l.setSpacing(10)

        for term, one_line, detail in GLOSSARY_ENTRIES:
            card = QFrame()
            card.setObjectName("setCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(15, 13, 15, 13)
            cl.setSpacing(6)
            t = QLabel(term)
            t.setObjectName("setCardTitle")
            one = QLabel(one_line)
            one.setObjectName("setBody")
            one.setWordWrap(True)
            one.setStyleSheet(
                f"font-size: 13px; font-weight: 500; color: {p.text};"
            )
            d = QLabel(detail)
            d.setObjectName("setMeta")
            d.setWordWrap(True)
            d.setStyleSheet(f"font-size: 12px; color: {p.text_muted};")
            cl.addWidget(t)
            cl.addWidget(one)
            cl.addWidget(d)
            host_l.addWidget(card)

        hint = QLabel(
            "혼자 쓸 때도 어제 나에게 남기는 기록입니다. "
            "협업은 그다음 이야기입니다."
        )
        hint.setObjectName("setMeta")
        hint.setWordWrap(True)
        host_l.addWidget(hint)
        host_l.addStretch(1)
        scroll.setWidget(host)
        lay.addWidget(scroll, 1)
        return w

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
        actions.addWidget(btn_onb)
        actions.addWidget(btn_terms)
        actions.addStretch(1)
        lay.addLayout(actions)
        lay.addStretch(1)
        return w

    # ----- account actions -----
    def _refresh_account(self) -> None:
        p = active_palette()
        logged = is_logged_in()
        login = load_last_github_login() or ""
        if logged:
            self._acct_dot.setStyleSheet(f"color: {p.primary}; font-size: 10px;")
            name = login or "(사용자)"
            self._acct_title.setText(f"{name} 으로 로그인됨")
            scope = (load_scope() or "").strip() or SCOPE_UNKNOWN
            if scope == SCOPE_UNKNOWN:
                scope_s = "권한 확인 불가"
            else:
                scope_s = f"권한 {scope}"
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
        else:
            self._acct_dot.setStyleSheet(f"color: {p.text_disabled}; font-size: 10px;")
            self._acct_title.setText("GitHub에 연결되지 않음")
            self._acct_meta.setText("연결하면 올리기·비공개 받기를 쓸 수 있습니다.")
            self._btn_relogin.hide()
            self._btn_logout.hide()
            self._btn_connect.show()

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
        self._refresh_account()

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

    @Slot()
    def _open_terms(self) -> None:
        path = app_root() / "legal" / "CloneUp_Terms_ko.txt"
        if not path.is_file():
            # frozen installer may place under same tree
            alt = app_root() / "installer" / "license" / "CloneUp_Terms_ko.txt"
            path = alt if alt.is_file() else path
        if not path.is_file():
            QMessageBox.information(
                self,
                "이용약관",
                "이용약관 파일을 찾지 못했습니다.\n"
                "설치 시 약관에 동의하셨습니다.",
            )
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "이용약관", str(e))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("이용약관")
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
