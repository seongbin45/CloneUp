"""First-run onboarding — desin/CloneUp 첫 실행 안내.dc.html.

Five short steps for beginners. Shown once after install; reopen via 도움말.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
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

from app.ui.theme import Palette, active_palette


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
        "커밋은 돌아올 수 있는 지점입니다",
        "사진을 찍어두는 것과 같습니다. 찍어둔 만큼 돌아갈 수 있습니다.",
    ),
    _Step(
        "cost",
        "무엇이 대가를 치르는지 먼저 보세요",
        "대부분의 동작은 잃는 것이 없습니다. 조심할 것은 둘뿐입니다.",
    ),
    _Step(
        "undo",
        "되돌리는 방법은 두 가지입니다",
        "이름은 비슷하지만 대가가 전혀 다릅니다.",
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
        "기록 남기고 되돌리기",
        "예전 내용이 돌아옵니다",
        "기록이 한 줄 길어집니다",
        False,
    ),
    (
        "기록 지우고 되돌리기",
        "기록이 깔끔해집니다",
        "남의 사본이 어긋나고, 되돌릴 수 없습니다",
        True,
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
    """Modal multi-step first-run guide."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._i = 0
        p = active_palette()
        self.setWindowTitle("클론업 시작하기")
        self.setModal(True)
        self.setMinimumSize(720, 520)
        self.resize(880, 600)
        self.setStyleSheet(self._qss(p))

        root = QVBoxLayout(self)
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
        self._step_lbl = QLabel("1 / 5")
        self._step_lbl.setObjectName("obStepMeta")
        bar_l.addWidget(title)
        bar_l.addStretch(1)
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

        self._sync_ui()

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
                    ("보관되고, 다른 곳에서 받을 수 있는 사본", "obBody"),
                ],
            ),
            1,
        )
        lay.addLayout(row)
        foot = QLabel(
            "둘은 자동으로 맞춰지지 않습니다. 이 앱의 모든 버튼은 결국 이 화살표 둘 중 하나입니다."
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
            "점 하나가 커밋 하나입니다. 커밋할 때마다 그 순간의 폴더 전체가 통째로 "
            "저장되고, 언제든 그 점으로 돌아갈 수 있습니다. 자주 할수록 돌아갈 곳이 많아집니다."
        )
        foot.setObjectName("obBody")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        lay.addStretch(1)
        return w

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
            "대가를 치르는 것은 굵게 표시된 둘뿐입니다. 나머지는 마음 놓고 하셔도 됩니다."
        )
        foot.setObjectName("obBody")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        lay.addStretch(1)
        return w

    def _page_undo(self, p: Palette) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        row = QHBoxLayout()
        row.setSpacing(18)
        # recommended
        a = QFrame()
        a.setObjectName("obCard")
        al = QVBoxLayout(a)
        al.setContentsMargins(20, 22, 20, 22)
        al.setSpacing(11)
        t1 = QLabel("기본 · 권장")
        t1.setStyleSheet(
            f"font-size: 11.5px; font-weight: 600; color: {p.primary};"
        )
        h1 = QLabel("기록을 남기고 되돌리기")
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
        al.addWidget(t1)
        al.addWidget(h1)
        al.addWidget(b1)
        al.addStretch(1)
        al.addWidget(f1)
        # advanced
        b = QFrame()
        b.setObjectName("obWarnCard")
        bl = QVBoxLayout(b)
        bl.setContentsMargins(20, 22, 20, 22)
        bl.setSpacing(11)
        t2 = QLabel("고급 · 주의")
        t2.setStyleSheet(
            f"font-size: 11.5px; font-weight: 600; color: {p.warn_text};"
        )
        h2 = QLabel("기록까지 지우고 되돌리기")
        h2.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {p.text};"
        )
        h2.setWordWrap(True)
        b2 = QLabel(
            "커밋을 아예 없앱니다. 이미 올린 커밋이라면 "
            "그 사본을 받아 간 사람의 폴더가 어긋납니다."
        )
        b2.setWordWrap(True)
        b2.setObjectName("obBody")
        f2 = QLabel("대가: 되돌릴 수 없습니다")
        f2.setStyleSheet(
            f"font-size: 12.5px; font-weight: 600; color: {p.warn_text}; "
            f"padding-top: 11px; border-top: 1px solid {p.warn_border};"
        )
        bl.addWidget(t2)
        bl.addWidget(h2)
        bl.addWidget(b2)
        bl.addStretch(1)
        bl.addWidget(f2)
        row.addWidget(a, 1)
        row.addWidget(b, 1)
        lay.addLayout(row)
        foot = QLabel(
            "어느 쪽을 고르든, 실행 직전에 무엇이 바뀌는지 파일 목록으로 먼저 보여드립니다."
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
        warn_bg = "#fbf6ee" if p.name == "light" else p.bg_hint
        return f"""
        QDialog {{
            background: {p.bg_window};
            color: {p.text};
        }}
        QFrame#obTitleBar, QFrame#obFooter {{
            background: {p.bg_bar};
            border: none;
        }}
        QFrame#obTitleBar {{
            border-bottom: 1px solid {p.border_soft};
        }}
        QFrame#obFooter {{
            border-top: 1px solid {p.border_divider};
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
        QFrame#obWarnCard {{
            background: {warn_bg};
            border: 1px solid {p.warn_border};
            border-left: 4px solid {p.warn_dot};
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
    Show onboarding modally.

    Returns True if the user finished (시작하기 / accept), False if dismissed
    without finishing (rare — Escape closes as reject).
    """
    dlg = OnboardingDialog(parent)
    return dlg.exec() == QDialog.DialogCode.Accepted
