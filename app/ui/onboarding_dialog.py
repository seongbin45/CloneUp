"""First-run onboarding — desin/CloneUp 첫 실행 안내.dc.html.

Short steps for beginners (folders · commits · why-Git loop · history mode ·
cost · undo · safety). Shown once after install; reopen via 도움말.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QGuiApplication, QKeyEvent, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.settings_store import load_history_revert_enabled, save_history_revert_enabled
from app.ui.theme import Palette, active_palette


class _SelectableCard(QFrame):
    """Plain QFrame with a click signal — used for the 읽기전용/되돌리기 picker."""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


@dataclass(frozen=True)
class _Step:
    key: str
    title: str
    lead: str


_STEPS: tuple[_Step, ...] = (
    _Step(
        "folders",
        "폴더가 두 곳에 있습니다",
        "클론업이 하는 일은 이 둘을 맞추는 것뿐입니다. 이것만 알면 나머지는 다 따라옵니다.",
    ),
    _Step(
        "commits",
        "커밋은 내 서고에 남기는 기록입니다",
        "책상 위 원고를 봉인해 꽂습니다(commit). 아직 출판사(GitHub)로 push한 것은 아닙니다.",
    ),
    _Step(
        "loop",
        "왜 여러 단계인가요 — 한 바퀴 루프",
        "자리가 넷입니다. 성공한 뒤 이 그림을 보면 됩니다. 자동 클라우드가 아닙니다.",
    ),
    _Step(
        "history_mode",
        "커밋 내역은 어떻게 쓸까요?",
        "목록을 보기만 할지, 예전 시점으로 되돌릴 수 있게 할지를 고릅니다. "
        "기본은 확인만 하는 쪽입니다.",
    ),
    _Step(
        "cost",
        "무엇이 대가를 치르는지 먼저 보세요",
        "대부분의 동작은 잃는 것이 없습니다. 조심할 것은 하나뿐입니다.",
    ),
    _Step(
        "undo",
        "되돌리기를 누르면 무슨 일이 생기나요",
        "예전 내용을 되살린 새 커밋이 하나 더 쌓일 뿐입니다.",
    ),
    _Step(
        "safety",
        "실수해도 됩니다",
        "위험한 동작은 앱이 먼저 막아섭니다.",
    ),
)

_COST_ROWS: tuple[tuple[str, str, str, bool], ...] = (
    ("커밋하기", "돌아올 지점이 하나 생깁니다", "없습니다", False),
    ("비공개로 올리기", "다른 곳에서도 받아 쓸 수 있습니다", "없습니다", False),
    (
        "공개로 올리기",
        "누구나 받아 볼 수 있습니다",
        "인터넷에 공개되고, 지워도 완전히 거두기 어렵습니다",
        True,
    ),
    (
        "되돌리기",
        "예전 내용이 돌아옵니다",
        "기록이 한 줄 길어집니다",
        False,
    ),
)

_SAFETY_ROWS: tuple[tuple[str, str], ...] = (
    (
        "되돌리기 전에 백업 브랜치를 만듭니다",
        "잘못 눌러도 돌아올 자리가 남습니다. 따로 하실 일은 없습니다.",
    ),
    (
        "비밀번호가 든 파일로 보이면 멈춥니다",
        "올리기 전에 파일 이름을 검사해 알려드립니다. "
        "다만 파일 안쪽까지는 보지 못하니 마지막 확인은 직접 해주세요.",
    ),
    (
        "위험한 동작은 실행 직전에 다시 묻습니다",
        "무엇이 바뀌는지 파일 목록으로 보여드린 뒤에 진행합니다.",
    ),
)


class OnboardingDialog(QDialog):
    """Modal multi-step first-run guide (opens F11-style true fullscreen)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        # Own top-level window so showFullScreen covers the whole monitor
        # (including taskbar), not just the parent client area.
        super().__init__(parent)
        self._i = 0
        self._fullscreen_applied = False
        self._history_revert = load_history_revert_enabled()
        p = active_palette()
        self.setWindowTitle("클론업 시작하기")
        self.setModal(True)
        # Top-level window (not a child tool dialog) so fullscreen covers the monitor
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setStyleSheet(self._qss(p))
        # F11 works even if focus is on a child control
        QShortcut(QKeySequence(Qt.Key.Key_F11), self, activated=self._toggle_fullscreen)

        # Outer shell fills the screen (design bg around the card)
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        outer = QWidget()
        outer.setObjectName("obShell")
        outer_l = QVBoxLayout(outer)
        outer_l.setContentsMargins(40, 32, 40, 32)
        outer_l.setSpacing(0)

        # Centered content card (readable width on ultrawide)
        row = QHBoxLayout()
        row.addStretch(1)
        card = QFrame()
        card.setObjectName("obCardShell")
        card.setMaximumWidth(1040)
        card.setMinimumWidth(720)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root = QVBoxLayout(card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # title bar
        bar = QFrame()
        bar.setObjectName("obTitleBar")
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(16, 12, 16, 12)
        bar_l.setSpacing(12)
        title = QLabel("클론업 시작하기")
        title.setObjectName("obTitle")
        self._step_lbl = QLabel(f"1 / {len(_STEPS)}")
        self._step_lbl.setObjectName("obStepMeta")
        self._fs_hint = QLabel("전체 화면 · Esc 닫기 · F11 창 모드")
        self._fs_hint.setObjectName("obStepMeta")
        bar_l.addWidget(title)
        bar_l.addStretch(1)
        bar_l.addWidget(self._fs_hint)
        bar_l.addWidget(self._step_lbl)
        root.addWidget(bar)

        # body stack
        body_wrap = QWidget()
        body_wrap.setObjectName("obBody")
        body_l = QVBoxLayout(body_wrap)
        body_l.setContentsMargins(48, 40, 48, 34)
        body_l.setSpacing(26)

        self._title = QLabel()
        self._title.setObjectName("obHeadline")
        self._title.setWordWrap(True)
        self._lead = QLabel()
        self._lead.setObjectName("obLead")
        self._lead.setWordWrap(True)
        body_l.addWidget(self._title)
        body_l.addWidget(self._lead)

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._stack.addWidget(self._page_folders(p))
        self._stack.addWidget(self._page_commits(p))
        self._stack.addWidget(self._page_loop(p))
        self._stack.addWidget(self._page_history_mode(p))
        self._stack.addWidget(self._page_cost(p))
        self._stack.addWidget(self._page_undo(p))
        self._stack.addWidget(self._page_safety(p))
        body_l.addWidget(self._stack, 1)
        root.addWidget(body_wrap, 1)

        # footer
        foot = QFrame()
        foot.setObjectName("obFooter")
        foot_l = QHBoxLayout(foot)
        foot_l.setContentsMargins(20, 14, 20, 14)
        foot_l.setSpacing(16)

        self._dots: list[QPushButton] = []
        dots_row = QHBoxLayout()
        dots_row.setSpacing(7)
        for n in range(len(_STEPS)):
            d = QPushButton()
            d.setObjectName("obDot")
            d.setFixedSize(8, 8)
            d.setCursor(Qt.CursorShape.PointingHandCursor)
            d.setFlat(True)
            d.clicked.connect(lambda _=False, idx=n: self._go(idx))
            self._dots.append(d)
            dots_row.addWidget(d)
        foot_l.addLayout(dots_row)
        foot_l.addStretch(1)

        self._btn_skip = QPushButton("건너뛰기")
        self._btn_skip.setObjectName("obSkip")
        self._btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_skip.setFlat(True)
        self._btn_skip.clicked.connect(self._on_skip)
        self._btn_prev = QPushButton("이전")
        self._btn_prev.setObjectName("obSecondary")
        self._btn_prev.clicked.connect(self._on_prev)
        self._btn_next = QPushButton("다음")
        self._btn_next.setObjectName("obPrimary")
        self._btn_next.clicked.connect(self._on_next)
        foot_l.addWidget(self._btn_skip)
        foot_l.addWidget(self._btn_prev)
        foot_l.addWidget(self._btn_next)
        root.addWidget(foot)

        row.addWidget(card, 1)
        row.addStretch(1)
        outer_l.addLayout(row, 1)
        shell.addWidget(outer, 1)

        self._sync_ui()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        # F11-style: cover entire screen, taskbar hidden (Windows)
        if not self._fullscreen_applied:
            self._fullscreen_applied = True
            self._enter_fullscreen()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        # F11 handled by QShortcut (_toggle_fullscreen)
        super().keyPressEvent(event)

    @Slot()
    def _toggle_fullscreen(self) -> None:
        """F11: leave true-fullscreen (taskbar back) ↔ windowed card."""
        if self.isFullScreen():
            self._leave_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self) -> None:
        """True fullscreen like browser F11 (covers taskbar)."""
        # Frameless only while fullscreen — avoid broken chrome on showNormal
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.show()  # required after changing window flags
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        if hasattr(self, "_fs_hint") and self._fs_hint is not None:
            self._fs_hint.setText("전체 화면 · Esc 닫기 · F11 창 모드")

    def _leave_fullscreen(self) -> None:
        """
        Exit fullscreen into a normal, movable window on the usable desktop
        (taskbar visible again). showNormal() alone with Frameless often
        leaves a zero-size or off-screen window on Windows.
        """
        # 1) Clear fullscreen state first
        self.setWindowState(Qt.WindowState.WindowNoState)
        # 2) Restore title bar so the window can be moved/closed normally
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.show()  # re-apply flags
        # 3) Explicit geometry on availableGeometry (excludes taskbar)
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            ag = screen.availableGeometry()
            w = min(960, max(720, ag.width() - 80))
            h = min(720, max(520, ag.height() - 80))
            x = ag.x() + max(0, (ag.width() - w) // 2)
            y = ag.y() + max(0, (ag.height() - h) // 2)
            self.setGeometry(x, y, w, h)
        else:
            self.resize(960, 700)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if hasattr(self, "_fs_hint") and self._fs_hint is not None:
            self._fs_hint.setText("창 모드 · Esc 닫기 · F11 전체 화면")

    # --- pages ---
    def _page_folders(self, p: Palette) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)

        row = QHBoxLayout()
        row.setSpacing(20)
        row.addWidget(
            self._card(
                p,
                lines=[
                    ("내 컴퓨터", "obMuted"),
                    ("my-project", "obMono"),
                    ("직접 파일을 고치는 곳", "obBody"),
                ],
            ),
            1,
        )
        mid = QVBoxLayout()
        mid.setSpacing(14)
        mid.addStretch(1)
        # 올리기 →
        up = QVBoxLayout()
        up.setSpacing(4)
        up_lab = QLabel("올리기")
        up_lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        up_lab.setStyleSheet(
            f"font-size: 11.5px; color: {p.primary}; font-weight: 500;"
        )
        up_line = QLabel("────────▶")
        up_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        up_line.setStyleSheet(f"font-size: 12px; color: {p.primary};")
        up.addWidget(up_lab)
        up.addWidget(up_line)
        mid.addLayout(up)
        # ← 받아오기
        dn = QVBoxLayout()
        dn.setSpacing(4)
        dn_line = QLabel("◀────────")
        dn_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dn_line.setStyleSheet(f"font-size: 12px; color: {p.text_faint};")
        dn_lab = QLabel("받아오기")
        dn_lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dn_lab.setStyleSheet(f"font-size: 11.5px; color: {p.text_muted};")
        dn.addWidget(dn_line)
        dn.addWidget(dn_lab)
        mid.addLayout(dn)
        mid.addStretch(1)
        mid_w = QWidget()
        mid_w.setFixedWidth(118)
        mid_w.setLayout(mid)
        row.addWidget(mid_w)
        row.addWidget(
            self._card(
                p,
                lines=[
                    ("GitHub", "obMuted"),
                    ("seong/my-project", "obMono"),
                    ("GitHub (원격) — 보내야 밖에 남습니다", "obBody"),
                ],
            ),
            1,
        )
        lay.addLayout(row)
        foot = QLabel(
            "만들고 올리기·받기·동기화는 이 화살표(올리기 / 받아오기) 쪽 일입니다. "
            "커밋하기 전에는 GitHub에 그 내용이 없습니다. "
            "받아오기·올리고 보내기를 누를 때만 양쪽이 맞춰집니다."
        )
        foot.setObjectName("obBody")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        lay.addStretch(1)
        return w

    def _page_commits(self, p: Palette) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(22)
        card = QFrame()
        card.setObjectName("obCard")
        cl = QHBoxLayout(card)
        cl.setContentsMargins(24, 26, 24, 26)
        cl.setSpacing(0)
        nodes = [
            ("첫 커밋", False),
            ("로그인 추가", False),
            ("색 수정", False),
            ("지금", True),
        ]
        for idx, (name, current) in enumerate(nodes):
            col = QVBoxLayout()
            col.setSpacing(9)
            col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            dot = QLabel("●" if current else "○")
            if current:
                dot.setStyleSheet(
                    f"font-size: 16px; color: {p.primary};"
                )
            else:
                dot.setStyleSheet(
                    f"font-size: 14px; color: {p.border_outline};"
                )
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab = QLabel(name)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setWordWrap(True)
            if current:
                lab.setStyleSheet(
                    f"font-size: 11.5px; color: {p.primary}; font-weight: 500;"
                )
            else:
                lab.setStyleSheet(f"font-size: 11.5px; color: {p.text_muted};")
            col.addWidget(dot)
            col.addWidget(lab)
            wrap = QWidget()
            wrap.setFixedWidth(96)
            wrap.setLayout(col)
            cl.addWidget(wrap)
            if idx < len(nodes) - 1:
                line = QFrame()
                line.setFixedHeight(2)
                line.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
                # last segment before "지금" is primary-colored
                if idx == len(nodes) - 2:
                    line.setStyleSheet(f"background: {p.primary}; border: none;")
                else:
                    line.setStyleSheet(
                        f"background: {p.border_input}; border: none;"
                    )
                cl.addWidget(line, 1, Qt.AlignmentFlag.AlignTop)
                # vertical offset for line ~ center of dots
                cl.setAlignment(line, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(card)
        foot = QLabel(
            "점 하나가 커밋(commit) 하나입니다. "
            "책상 위 수정만으로는 부족하고, 봉인해 내 서고(로컬 저장소)에 꽂아야 기록이 됩니다. "
            "git commit 전까지는 GitHub에 그 내용이 없습니다."
        )
        foot.setObjectName("obBody")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        lay.addStretch(1)
        return w

    def _page_loop(self, p: Palette) -> QWidget:
        """Why Git: four places + product tabs (no rename of UI words)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # Product words kept; manuscript metaphor; formal terms in parentheses.
        rows: tuple[tuple[str, str, str], ...] = (
            (
                "1 · 커밋 (commit)",
                "책상 위 원고를 봉인해 내 서고에 꽂습니다. (로컬 저장소)",
                "왜: 나중에 이 기록을 가리킬 수 있습니다. 커밋 전 수정은 GitHub에 안 갑니다.",
            ),
            (
                "2 · 만들고 올리기 / 올리고 보내기 (push)",
                "내 서고에 있는 봉인 기록을 GitHub(원격)로 보냅니다.",
                "왜: 밖과 맞추고 다른 자리에서도 이어 씁니다. 자동 클라우드 동기화가 아닙니다.",
            ),
            (
                "3 · 받아오기 (pull)",
                "GitHub에 더 새 기록이 있으면 이 폴더 쪽으로 가져옵니다.",
                "왜: 어느 쪽이 앞선 장을 가졌는지 보고 맞춥니다. 겹치면 충돌이 납니다.",
            ),
            (
                "4 · 다시 고치기",
                "작업 폴더에서 파일을 수정한 뒤 1번(커밋)으로 돌아갑니다.",
                "클론업 탭은 이 길을 나눈 것입니다. 성공한 뒤 ‘네 자리’를 보면 그림이 고정됩니다.",
            ),
        )
        for title, body, why in rows:
            card = QFrame()
            card.setObjectName("obCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.setSpacing(6)
            t = QLabel(title)
            t.setObjectName("obCardTitle")
            t.setStyleSheet(
                f"font-size: 13.5px; font-weight: 600; color: {p.primary};"
            )
            b = QLabel(body)
            b.setObjectName("obBody")
            b.setWordWrap(True)
            y = QLabel(why)
            y.setObjectName("obMuted")
            y.setWordWrap(True)
            y.setStyleSheet(f"font-size: 12px; color: {p.text_muted};")
            cl.addWidget(t)
            cl.addWidget(b)
            cl.addWidget(y)
            lay.addWidget(card)

        foot = QLabel(
            "「충돌」은 같은 줄을 양쪽에서 고쳐 자동 합치기가 멈춘 상태입니다. "
            "「충돌 취소」는 합치기 시도를 취소합니다. "
            "「커밋 내역」은 남겨 둔 커밋 목록입니다. 둘은 다른 버튼입니다. "
            "설정 > 용어 안내에서 같은 말을 다시 볼 수 있습니다."
        )
        foot.setObjectName("obBody")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        lay.addStretch(1)
        return w

    def _page_history_mode(self, p: Palette) -> QWidget:
        """
        시안: 커밋 내역 읽기전용 / 지워지지않습니다 — 두 모드를 고르는 단계.

        Other onboarding pages use badge · title · body · footer-meta cards
        (folders / undo / safety). This page used a thin click-to-select
        pair that felt sparse; keep the same choice, match that density.
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)

        row = QHBoxLayout()
        row.setSpacing(18)
        self._hm_readonly = self._history_mode_card(
            p,
            badge="기본 · 권장",
            title="읽기 전용",
            body=(
                "지난 시점의 내용을 확인만 합니다. "
                "이 창에서는 무엇을 눌러도 파일이 바뀌지 않습니다."
            ),
            meta="목록 보기 · 파일은 그대로",
        )
        self._hm_readonly["card"].clicked.connect(
            lambda: self._set_history_mode(False)
        )
        self._hm_revert = self._history_mode_card(
            p,
            badge="선택",
            title="되돌리기 허용",
            body=(
                "「이 시점으로 되돌리기」로 예전 내용을 되살린 "
                "새 커밋을 하나 더 쌓을 수 있습니다. "
                "지금까지의 기록은 그대로 남습니다."
            ),
            meta="기록은 지워지지 않습니다 · 설정 > 안전에서 변경",
        )
        self._hm_revert["card"].clicked.connect(
            lambda: self._set_history_mode(True)
        )
        row.addWidget(self._hm_readonly["card"], 1)
        row.addWidget(self._hm_revert["card"], 1)
        lay.addLayout(row)

        foot = QLabel(
            "카드를 눌러 고르면 바로 저장됩니다. "
            "설정 > 안전 > 「커밋 내역에서 되돌리기 허용」에서도 바꿀 수 있습니다."
        )
        foot.setObjectName("obBody")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        lay.addStretch(1)

        self._refresh_history_mode_cards()
        return w

    @staticmethod
    def _history_mode_card(
        p: Palette,
        *,
        badge: str,
        title: str,
        body: str,
        meta: str,
    ) -> dict:
        """
        Selectable card: brand solid when selected, with filled text panels
        (body / meta) so copy is not floating on bare green.
        """
        card = _SelectableCard()
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setMinimumHeight(220)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        outer = QHBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        rail = QFrame()
        rail.setObjectName("obHmRail")
        rail.setFixedWidth(4)
        outer.addWidget(rail)

        inner = QWidget()
        inner.setObjectName("obHmInner")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(16, 16, 16, 14)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(10)
        badge_lab = QLabel(badge)
        badge_lab.setObjectName("obHmBadge")
        pick_lab = QLabel()
        pick_lab.setObjectName("obHmPick")
        pick_lab.setFixedWidth(22)
        pick_lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(badge_lab, 0)
        head.addStretch(1)
        head.addWidget(pick_lab, 0)
        lay.addLayout(head)
        lay.addSpacing(12)

        title_lab = QLabel(title)
        title_lab.setObjectName("obHmTitle")
        title_lab.setWordWrap(True)
        lay.addWidget(title_lab)
        lay.addSpacing(10)

        # Body sits in a filled panel (not bare text on the card)
        body_panel = QFrame()
        body_panel.setObjectName("obHmBodyPanel")
        bp = QVBoxLayout(body_panel)
        bp.setContentsMargins(12, 11, 12, 11)
        bp.setSpacing(0)
        body_lab = QLabel(body)
        body_lab.setObjectName("obHmBody")
        body_lab.setWordWrap(True)
        bp.addWidget(body_lab)
        lay.addWidget(body_panel, 1)
        lay.addSpacing(10)

        meta_panel = QFrame()
        meta_panel.setObjectName("obHmMetaPanel")
        mp = QVBoxLayout(meta_panel)
        mp.setContentsMargins(12, 10, 12, 10)
        mp.setSpacing(0)
        meta_lab = QLabel(meta)
        meta_lab.setObjectName("obHmMeta")
        meta_lab.setWordWrap(True)
        mp.addWidget(meta_lab)
        lay.addWidget(meta_panel)

        outer.addWidget(inner, 1)

        return {
            "card": card,
            "rail": rail,
            "inner": inner,
            "badge": badge_lab,
            "badge_text": badge,
            "pick": pick_lab,
            "title": title_lab,
            "body_panel": body_panel,
            "body": body_lab,
            "meta_panel": meta_panel,
            "meta": meta_lab,
        }

    def _set_history_mode(self, enabled: bool) -> None:
        self._history_revert = enabled
        save_history_revert_enabled(enabled)
        self._refresh_history_mode_cards()

    def _refresh_history_mode_cards(self) -> None:
        p = active_palette()
        self._style_history_mode_card(
            self._hm_readonly, p, selected=not self._history_revert
        )
        self._style_history_mode_card(
            self._hm_revert, p, selected=self._history_revert
        )

    @staticmethod
    def _style_history_mode_card(
        parts: dict, p: Palette, *, selected: bool
    ) -> None:
        card: _SelectableCard = parts["card"]
        rail: QFrame = parts["rail"]
        inner: QWidget = parts["inner"]
        badge: QLabel = parts["badge"]
        pick: QLabel = parts["pick"]
        title: QLabel = parts["title"]
        body_panel: QFrame = parts["body_panel"]
        body: QLabel = parts["body"]
        meta_panel: QFrame = parts["meta_panel"]
        meta: QLabel = parts["meta"]
        badge_text = parts["badge_text"]

        # Selected: solid brand card; body/meta in filled panels; ✓ + near-white type.
        # Unselected: warm paper with muted filled text boxes.
        if selected:
            on = p.text_on_primary
            if getattr(p, "name", "light") == "dark":
                on_body = "#14352b"
                on_meta = "#1a4034"
                panel = "#3d9a7c"  # lighter brand wash on bright primary
                panel_meta = "#389075"
                badge_fg, badge_bg = p.primary_soft, on
            else:
                on_body = "#f3faf7"
                on_meta = "#e4f3ec"
                # Slightly lighter teal panels on deep primary
                panel = "#2a8570"
                panel_meta = "#247a66"
                badge_fg, badge_bg = p.primary, on

            card.setStyleSheet(
                f"QFrame {{ background: {p.primary}; "
                f"border: 1px solid {p.primary_hover}; border-radius: 8px; }}"
            )
            rail.setStyleSheet(
                f"background: {p.primary_hover}; border: none; "
                f"border-top-left-radius: 7px; border-bottom-left-radius: 7px;"
            )
            inner.setStyleSheet("background: transparent;")
            badge.setText(badge_text)
            badge.setStyleSheet(
                f"font-size: 11px; font-weight: 600; color: {badge_fg}; "
                f"background: {badge_bg}; padding: 4px 10px; border-radius: 4px;"
            )
            pick.setText("✓")
            pick.setStyleSheet(
                f"font-size: 15px; font-weight: 700; color: {on}; "
                f"background: transparent;"
            )
            title.setStyleSheet(
                f"font-size: 16px; font-weight: 600; color: {on}; "
                f"background: transparent;"
            )
            body_panel.setStyleSheet(
                f"QFrame#obHmBodyPanel {{ background: {panel}; "
                f"border: none; border-radius: 6px; }}"
            )
            body.setStyleSheet(
                f"font-size: 12.5px; color: {on_body}; line-height: 1.45; "
                f"background: transparent;"
            )
            meta_panel.setStyleSheet(
                f"QFrame#obHmMetaPanel {{ background: {panel_meta}; "
                f"border: none; border-radius: 6px; }}"
            )
            meta.setStyleSheet(
                f"font-size: 12.5px; color: {on_meta}; background: transparent;"
            )
        else:
            card.setStyleSheet(
                f"QFrame {{ background: {p.bg_window}; "
                f"border: 1px solid {p.border_soft}; border-radius: 8px; }}"
            )
            rail.setStyleSheet(
                f"background: {p.border_divider}; border: none; "
                f"border-top-left-radius: 7px; border-bottom-left-radius: 7px;"
            )
            inner.setStyleSheet("background: transparent;")
            badge.setText(badge_text)
            badge.setStyleSheet(
                f"font-size: 11px; font-weight: 600; color: {p.text_muted}; "
                f"background: {p.bg_muted}; padding: 4px 10px; border-radius: 4px;"
            )
            pick.setText("")
            pick.setStyleSheet(
                f"font-size: 15px; color: {p.text_faint}; background: transparent;"
            )
            title.setStyleSheet(
                f"font-size: 16px; font-weight: 600; color: {p.text}; "
                f"background: transparent;"
            )
            body_panel.setStyleSheet(
                f"QFrame#obHmBodyPanel {{ background: {p.bg_muted}; "
                f"border: 1px solid {p.border_soft}; border-radius: 6px; }}"
            )
            body.setStyleSheet(
                f"font-size: 12.5px; color: {p.text_secondary}; line-height: 1.45; "
                f"background: transparent;"
            )
            meta_panel.setStyleSheet(
                f"QFrame#obHmMetaPanel {{ background: {p.bg_hint}; "
                f"border: 1px solid {p.border_soft}; border-radius: 6px; }}"
            )
            meta.setStyleSheet(
                f"font-size: 12.5px; color: {p.text_muted}; background: transparent;"
            )

    def _page_cost(self, p: Palette) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(0)
        headers = ("하는 일", "얻는 것", "잃는 것")
        for col, h in enumerate(headers):
            lab = QLabel(h)
            lab.setStyleSheet(
                f"font-size: 11.5px; font-weight: 600; color: {p.text_muted}; "
                f"padding: 0 14px 9px; border-bottom: 2px solid {p.text};"
            )
            grid.addWidget(lab, 0, col)
        for r, (action, gain, loss, risky) in enumerate(_COST_ROWS, start=1):
            bg = "#fbf6ee" if risky and p.name == "light" else (
                p.bg_hint if risky else p.bg_window
            )
            if p.name == "dark" and risky:
                bg = p.bg_hint
            loss_c = p.warn_text if risky else p.text_muted
            loss_w = "600" if risky else "400"
            for c, text, weight, color in (
                (0, action, "500", p.text),
                (1, gain, "400", p.text_secondary),
                (2, loss, loss_w, loss_c),
            ):
                cell = QLabel(text)
                cell.setWordWrap(True)
                cell.setStyleSheet(
                    f"font-size: {'13px' if c == 0 else '12.5px'}; "
                    f"font-weight: {weight}; color: {color}; "
                    f"background: {bg}; padding: 11px 14px; "
                    f"border-bottom: 1px solid {p.border_divider};"
                )
                grid.addWidget(cell, r, c)
        grid.setColumnStretch(0, 19)
        grid.setColumnStretch(1, 20)
        grid.setColumnStretch(2, 20)
        lay.addLayout(grid)
        foot = QLabel(
            "대가를 치르는 것은 굵게 표시된 하나뿐입니다. 나머지는 마음 놓고 하셔도 됩니다."
        )
        foot.setObjectName("obBody")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        lay.addStretch(1)
        return w

    def _page_undo(self, p: Palette) -> QWidget:
        """
        되돌리기는 한 가지 방법뿐입니다 — 기록을 지우는 방식(강제 push)은
        남의 사본을 깨뜨릴 수 있는 유일한 동작이라 이 앱에서 제외했습니다.
        이전엔 두 방법을 나란히 비교했지만, 없는 기능을 가르치는 셈이라
        하나로 정리했습니다.
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)

        card = QFrame()
        card.setObjectName("obCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 22, 20, 22)
        cl.setSpacing(11)
        h1 = QLabel("기록을 남기고 되돌립니다")
        h1.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {p.text};"
        )
        h1.setWordWrap(True)
        b1 = QLabel(
            "예전 내용을 되살린 새 커밋을 하나 더 쌓습니다. "
            "지운 것이 없으니 되돌리기를 또 되돌릴 수 있습니다."
        )
        b1.setWordWrap(True)
        b1.setObjectName("obBody")
        f1 = QLabel("대가: 기록이 한 줄 길어집니다")
        f1.setStyleSheet(
            f"font-size: 12.5px; color: {p.text_secondary}; "
            f"padding-top: 11px; border-top: 1px solid {p.border_soft};"
        )
        cl.addWidget(h1)
        cl.addWidget(b1)
        cl.addWidget(f1)
        lay.addWidget(card)

        foot = QLabel(
            "실행 직전에 무엇이 바뀌는지 파일 목록으로 먼저 보여드립니다."
        )
        foot.setObjectName("obBody")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        lay.addStretch(1)
        return w

    def _page_safety(self, p: Palette) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(11)
        for title, body in _SAFETY_ROWS:
            row = QFrame()
            row.setObjectName("obCard")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(18, 15, 18, 15)
            rl.setSpacing(14)
            dot = QLabel("●")
            dot.setStyleSheet(f"font-size: 8px; color: {p.primary};")
            dot.setFixedWidth(14)
            col = QVBoxLayout()
            col.setSpacing(4)
            t = QLabel(title)
            t.setStyleSheet(
                f"font-size: 13.5px; font-weight: 600; color: {p.text};"
            )
            t.setWordWrap(True)
            b = QLabel(body)
            b.setObjectName("obBody")
            b.setWordWrap(True)
            col.addWidget(t)
            col.addWidget(b)
            rl.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            rl.addLayout(col, 1)
            lay.addWidget(row)
        foot = QLabel(
            "이 안내는 오른쪽 위 「도움말」에서 언제든 다시 볼 수 있습니다."
        )
        foot.setObjectName("obBody")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        lay.addStretch(1)
        return w

    def _card(self, p: Palette, *, lines: list[tuple[str, str]]) -> QFrame:
        f = QFrame()
        f.setObjectName("obCard")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(20, 22, 20, 22)
        lay.setSpacing(7)
        for text, role in lines:
            lab = QLabel(text)
            lab.setWordWrap(True)
            if role == "obMuted":
                lab.setStyleSheet(f"font-size: 12px; color: {p.text_muted};")
            elif role == "obMono":
                lab.setStyleSheet(
                    f"font-size: 14px; font-weight: 500; color: {p.text}; "
                    f"font-family: Consolas, 'Cascadia Mono', monospace;"
                )
            else:
                lab.setObjectName("obBody")
            lay.addWidget(lab)
        return f

    # --- navigation ---
    def _go(self, i: int) -> None:
        self._i = max(0, min(i, len(_STEPS) - 1))
        self._sync_ui()

    @Slot()
    def _on_prev(self) -> None:
        self._go(self._i - 1)

    @Slot()
    def _on_next(self) -> None:
        if self._i >= len(_STEPS) - 1:
            self.accept()
            return
        self._go(self._i + 1)

    @Slot()
    def _on_skip(self) -> None:
        # Design: skip jumps to last step (user still presses 시작하기)
        self._go(len(_STEPS) - 1)

    def _sync_ui(self) -> None:
        p = active_palette()
        step = _STEPS[self._i]
        self._title.setText(step.title)
        self._lead.setText(step.lead)
        self._stack.setCurrentIndex(self._i)
        self._step_lbl.setText(f"{self._i + 1} / {len(_STEPS)}")
        last = self._i >= len(_STEPS) - 1
        self._btn_prev.setVisible(self._i > 0)
        self._btn_skip.setVisible(not last)
        self._btn_next.setText("시작하기" if last else "다음")
        for n, d in enumerate(self._dots):
            if n == self._i:
                d.setStyleSheet(
                    f"background: {p.primary}; border-radius: 4px; border: none;"
                )
            else:
                d.setStyleSheet(
                    f"background: {p.border_input}; border-radius: 4px; border: none;"
                )

    @staticmethod
    def _qss(p: Palette) -> str:
        return f"""
        QDialog {{
            background: {p.bg_app};
            color: {p.text};
        }}
        QWidget#obShell {{
            background: {p.bg_app};
        }}
        QFrame#obCardShell {{
            background: {p.bg_window};
            border: 1px solid {p.border};
            border-radius: 10px;
        }}
        QFrame#obTitleBar, QFrame#obFooter {{
            background: {p.bg_bar};
            border: none;
        }}
        QFrame#obTitleBar {{
            border-bottom: 1px solid {p.border_soft};
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
        }}
        QFrame#obFooter {{
            border-top: 1px solid {p.border_divider};
            border-bottom-left-radius: 10px;
            border-bottom-right-radius: 10px;
        }}
        QLabel#obTitle {{
            font-size: 13px;
            font-weight: 600;
            color: {p.text};
        }}
        QLabel#obStepMeta {{
            font-size: 12px;
            color: {p.text_muted};
        }}
        QWidget#obBody {{
            background: {p.bg_window};
        }}
        QLabel#obHeadline {{
            font-size: 22px;
            font-weight: 600;
            color: {p.text};
            letter-spacing: -0.01em;
        }}
        QLabel#obLead {{
            font-size: 14px;
            color: {p.text_secondary};
            line-height: 1.4;
        }}
        QLabel#obBody {{
            font-size: 13px;
            color: {p.text_secondary};
        }}
        QFrame#obCard {{
            background: {p.bg_muted};
            border: 1px solid {p.border_soft};
            border-radius: 8px;
        }}
        QPushButton#obPrimary {{
            background: {p.primary};
            color: {p.text_on_primary};
            border: 1px solid {p.primary};
            border-radius: 5px;
            padding: 0 22px;
            min-height: 34px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton#obPrimary:hover {{
            background: {p.primary_hover};
            border-color: {p.primary_hover};
        }}
        QPushButton#obSecondary {{
            background: {p.bg_window};
            color: {p.text};
            border: 1px solid {p.border_outline};
            border-radius: 5px;
            padding: 0 18px;
            min-height: 34px;
            font-size: 12.5px;
        }}
        QPushButton#obSecondary:hover {{
            background: {p.bg_hint};
        }}
        QPushButton#obSkip {{
            color: {p.text_muted};
            font-size: 12.5px;
            padding: 0 14px;
            min-height: 34px;
            border: none;
            background: transparent;
        }}
        QPushButton#obSkip:hover {{
            color: {p.text};
        }}
        QPushButton#obDot {{
            min-width: 8px;
            max-width: 8px;
            min-height: 8px;
            max-height: 8px;
            padding: 0;
        }}
        """


def show_onboarding(parent: QWidget | None = None) -> bool:
    """
    Show onboarding modally in F11-style true fullscreen (taskbar hidden).

    Returns True if the user finished (시작하기 / accept), False if dismissed
    without finishing (Escape closes as reject). F11 toggles windowed mode
    with a proper centered geometry (does not leave a broken empty frame).
    """
    dlg = OnboardingDialog(parent)
    # showEvent → _enter_fullscreen(); do not pre-set WindowFullScreen alone
    # (that path + Frameless was leaving a broken window on F11 exit).
    return dlg.exec() == QDialog.DialogCode.Accepted
