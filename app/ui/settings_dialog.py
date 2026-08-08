"""Settings dialog — desin/CloneUp 설정.dc.html.

Sidebar tabs: 계정 · 올리기 기본값 · 안전 · 최근 폴더 · 정보.
Prefs save immediately (footer: 바꾸면 바로 저장됩니다).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
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
    load_last_commit_message,
    load_last_github_login,
    load_last_private,
    load_last_publish_branch,
    load_recent_folders,
    save_hide_real_email,
    save_last_commit_message,
    save_last_private,
    save_last_publish_branch,
)
from app.ui.theme import Palette, active_palette

_NAV = ("계정", "올리기 기본값", "안전", "최근 폴더", "정보")


class _ToggleSwitch(QFrame):
    """Track + knob toggle matching desin 설정 (40×23, knob 19)."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on = bool(checked)
        self.setObjectName("setSwitchTrack")
        self.setFixedSize(40, 23)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(2, 2, 2, 2)
        self._lay.setSpacing(0)
        self._knob = QFrame()
        self._knob.setObjectName("setSwitchKnob")
        self._knob.setFixedSize(19, 19)
        self._knob.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._paint()

    def isChecked(self) -> bool:
        return self._on

    def setChecked(self, checked: bool, *, emit: bool = True) -> None:
        on = bool(checked)
        if self._on == on:
            self._paint()
            return
        self._on = on
        self._paint()
        if emit:
            self.toggled.emit(self._on)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._on)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.setChecked(not self._on)
            event.accept()
            return
        super().keyPressEvent(event)

    def _paint(self) -> None:
        p = active_palette()
        track = p.primary if self._on else p.border_input
        # Design: track #1f6f5c / #cdc8bf, knob #fbfaf8, justify flex-end/start
        self.setStyleSheet(
            f"QFrame#setSwitchTrack {{"
            f"background: {track}; border: none; border-radius: 12px;}}"
            f"QFrame#setSwitchKnob {{"
            f"background: {p.bg_window}; border: none; border-radius: 9px;}}"
        )
        while self._lay.count():
            item = self._lay.takeAt(0)
            # keep knob; discard stretch spacers
            if item is not None and item.widget() is self._knob:
                pass
        if self._on:
            self._lay.addStretch(1)
            self._lay.addWidget(self._knob, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            self._lay.addWidget(self._knob, 0, Qt.AlignmentFlag.AlignVCenter)
            self._lay.addStretch(1)


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
        on_prefs_changed: Callable[[], None] | None = None,
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
        self._page_about = self._build_about(p)
        for page in (
            self._page_account,
            self._page_defaults,
            self._page_safety,
            self._page_folders,
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

    def _notify_prefs(self) -> None:
        if self._on_prefs_changed is not None:
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
        # Design: column gap 22 between heading / toggle card / secret block
        w, lay = self._page_shell()
        lay.addWidget(
            self._heading(
                "안전",
                "실수로 무언가를 공개하지 않도록 돕는 설정입니다.",
            )
        )

        toggle_row = QFrame()
        toggle_row.setObjectName("setCard")
        tr = QHBoxLayout(toggle_row)
        # design padding: 15px 17px
        tr.setContentsMargins(17, 15, 17, 15)
        tr.setSpacing(14)

        self._sw_hide_email = _ToggleSwitch(checked=self._hide_email)
        self._sw_hide_email.toggled.connect(self._on_hide_email_toggled)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)
        tt = QLabel("커밋에 실제 이메일 숨기기")
        tt.setObjectName("setCardTitle")
        tb = QLabel(
            "GitHub가 주는 대체 주소를 씁니다. "
            "컴퓨터에 이미 Git 이메일을 설정해 두었다면 그 값이 우선합니다."
        )
        tb.setObjectName("setBody")
        tb.setWordWrap(True)
        text_col.addWidget(tt)
        text_col.addWidget(tb)
        tr.addWidget(self._sw_hide_email, 0, Qt.AlignmentFlag.AlignTop)
        tr.addLayout(text_col, 1)
        lay.addWidget(toggle_row)

        # design: column gap 9 for 비밀 파일 점검 block
        secret = QVBoxLayout()
        secret.setContentsMargins(0, 0, 0, 0)
        secret.setSpacing(9)
        sec = QLabel("비밀 파일 점검")
        sec.setObjectName("setSection")
        secret.addWidget(sec)
        always = QLabel(
            "항상 켜져 있습니다. 올리기 전에 비밀번호가 들어 있을 만한 "
            "파일 이름을 찾아 알려드립니다."
        )
        always.setObjectName("setInfoBox")
        always.setWordWrap(True)
        secret.addWidget(always)
        warn = QLabel(
            "파일 이름만 봅니다. 파일 안에 적어둔 비밀번호는 찾지 못하니 "
            "마지막 확인은 직접 해주세요. 경고를 무시하고 진행하는 것은 "
            "그때그때 올리기 화면에서만 고를 수 있습니다."
        )
        warn.setObjectName("setWarnBanner")
        warn.setWordWrap(True)
        secret.addWidget(warn)
        lay.addLayout(secret)
        lay.addStretch(1)
        return w

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
        self._notify_prefs()

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
            self._btn_pub.setStyleSheet(
                f"QPushButton#setChoiceCard {{"
                f"text-align: left; padding: 11px 13px; border-radius: 6px; "
                f"border: 1px solid {p.warn_border}; background: {p.bg_hint}; "
                f"font-size: 13px; color: {p.text};}}"
            )
            self._vis_note.setText(
                "올리는 순간 인터넷에 공개되고, 지워도 완전히 거두기 어렵습니다."
            )
            self._vis_note.setStyleSheet(f"color: {p.warn_text}; font-size: 11.5px;")

    @Slot()
    def _save_commit_message(self) -> None:
        text = (self._edit_msg.text() or "").strip()
        if text:
            save_last_commit_message(text)
            self._notify_prefs()

    @Slot()
    def _save_branch(self) -> None:
        text = (self._edit_branch.text() or "").strip()
        if text:
            save_last_publish_branch(text)
            self._notify_prefs()

    # ----- safety -----
    @Slot(bool)
    def _on_hide_email_toggled(self, checked: bool) -> None:
        self._hide_email = bool(checked)
        save_hide_real_email(self._hide_email)
        self._notify_prefs()

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
        self._notify_prefs()

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
            color: {p.text};
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
            background: #fbf6ee;
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
            color: {p.text};
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
            color: #9a4a45;
            border: 1px solid {p.border_outline};
            border-radius: 5px;
            padding: 6px 14px;
            font-size: 12.5px;
            min-height: 20px;
        }}
        QPushButton#setDangerOutline:hover {{
            background: #f7efee;
        }}
        """


def show_settings(
    parent: QWidget | None = None,
    *,
    on_login: Callable[[], None] | None = None,
    on_logout: Callable[[], None] | None = None,
    on_prefs_changed: Callable[[], None] | None = None,
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
