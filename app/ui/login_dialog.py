"""
Compact GitHub connect wizard (PAT only).

Short pages, minimal copy. Extra tips stay collapsed under 「자세히」.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# Browser box stack pages
_STACK_SESSION = 0
_STACK_LOADING = 1
_STACK_WEB = 2
_SPIN_FRAMES = ("◐", "◓", "◑", "◒")


from app.auth.pat_urls import (
    classic_pat_create_url,
    fine_pat_create_url,
    make_pat_note,
    note_from_pat_create_url,
    workflow_pat_create_url,
)
from app.config import is_device_flow_allowed
from app.ui.theme import Palette, active_palette

# Default path matches 「만들고 올리기」 = POST /user/repos + push.
# Classic `repo` can create private/public repos. Fine-grained "this repo only
# + Contents" cannot: the new name is not in the list yet, and Contents ≠ create.
# Note = CloneUp-YYYYMMDD-HHMMSS via classic_pat_create_url() each open.

PAT_LIST_URL = "https://github.com/settings/tokens"


def _pat_create_url(*, note: str | None = None) -> tuple[str, str]:
    """Return ``(url, note)`` with a fresh unique Note."""
    n = (note or "").strip() or make_pat_note()
    return classic_pat_create_url(note=n), n


def _pat_create_url_fine(*, note: str | None = None) -> tuple[str, str]:
    n = (note or "").strip() or make_pat_note()
    return fine_pat_create_url(note=n), n


# Public aliases for scripts / help dialogs (call each time for a fresh Note)
PAT_CREATE_URL = classic_pat_create_url  # callable
PAT_CREATE_URL_FINE = fine_pat_create_url  # callable
WORKFLOW_PAT_CREATE_URL = workflow_pat_create_url  # callable


def show_missing_repo_help(
    parent: QWidget | None,
    *,
    current_scopes: str = "",
    offer_reconnect: bool = True,
) -> bool:
    """
    Short, scannable dialog when PAT lacks ``repo``.

    Returns True if user chose to open the connect wizard again.
    """
    p = active_palette()
    dlg = QDialog(parent)
    dlg.setWindowTitle("저장소 권한")
    dlg.setModal(True)
    dlg.setMinimumWidth(400)
    dlg.setMaximumWidth(440)
    dlg.setStyleSheet(_dialog_style(p))

    title = QLabel("이 키로는 아직 연결할 수 없어요")
    title.setObjectName("wizTitle")
    title.setWordWrap(True)

    # One line cause — no essay
    why = QLabel("저장소 권한(repo)이 꺼져 있습니다.")
    why.setObjectName("wizLead")
    why.setWordWrap(True)

    steps = QLabel(
        "A) 같은 키(classic): GitHub 토큰 페이지에서 「repo」 켠 뒤\n"
        "   설정 → 「권한 다시 확인」\n"
        "B) 새 키: 아래에서 만들기 → 「repo」 한 줄 ✓ → 복사 → 다시 연결\n"
        "   · repo:status / public_repo 만 켜면 부족합니다 · 만료 90일 권장"
    )
    steps.setObjectName("wizBox")
    steps.setWordWrap(True)

    scopes = (current_scopes or "").strip()
    if scopes and scopes not in ("(없음)", "unknown"):
        try:
            from app.auth.token_store import format_scopes_display

            scopes = format_scopes_display(scopes) or scopes
        except Exception:
            pass
    detail_bits = [
        "classic 키는 웹에서 권한(scope)을 바꿀 수 있습니다. "
        "바꾼 뒤에는 앱에서 「권한 다시 확인」을 눌러 주세요.",
        "Select scopes 목록이 길어도 CloneUp은 「repo」만 필요합니다 "
        "(workflow 파일이 있을 때만 별도 안내로 workflow를 추가합니다).",
    ]
    if scopes and scopes not in ("(없음)",):
        detail_bits.append(f"이 키에 있던 권한: {scopes}")
    detail = _DetailToggle("\n".join(detail_bits))

    btn_create = QPushButton("1. 새 키 만들기")
    btn_create.setObjectName("btnPrimary")
    btn_create.setDefault(True)
    btn_create.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl(_pat_create_url()[0]))
    )

    reconnect = {"go": False}

    def _reconnect() -> None:
        reconnect["go"] = True
        dlg.accept()

    btn_again = QPushButton("3. 다시 연결")
    btn_again.setObjectName("btnPrimary")
    if offer_reconnect:
        btn_again.clicked.connect(_reconnect)
    else:
        btn_again.hide()

    btn_close = QPushButton("닫기")
    btn_close.setObjectName("btnGhost")
    btn_close.clicked.connect(dlg.reject)

    # Numbered actions match the 3 steps above
    actions = QHBoxLayout()
    actions.setSpacing(8)
    actions.addWidget(btn_create, 1)
    if offer_reconnect:
        actions.addWidget(btn_again, 1)

    bottom = QHBoxLayout()
    bottom.addWidget(btn_close)
    bottom.addStretch(1)

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 14, 16, 12)
    lay.setSpacing(8)
    lay.addWidget(title)
    lay.addWidget(why)
    lay.addWidget(steps)
    lay.addLayout(actions)
    lay.addWidget(detail)
    lay.addLayout(bottom)

    dlg.exec()
    return bool(reconnect["go"])


def parse_scopes_from_missing_repo_message(message: str) -> str:
    """Extract trailing scope list from format_missing_repo_scope_error text."""
    for line in (message or "").splitlines():
        if line.startswith("이 키에 있던 권한:"):
            return line.split(":", 1)[-1].strip()
    return ""


def show_missing_workflow_scope_help(
    parent: QWidget | None,
    *,
    offer_reconnect: bool = True,
) -> bool:
    """
    Short, scannable dialog for a push that failed because the repo has
    .github/workflows/*.yml files and the PAT lacks `workflow` on top of
    `repo`. Reactive only — shown after a real push failure proves this
    specific repo needs the scope, never suggested up front (most repos
    don't have workflow files, so the default connect flow stays `repo`-only).

    Returns True if user chose to open the connect wizard again.
    """
    p = active_palette()
    dlg = QDialog(parent)
    dlg.setWindowTitle("워크플로 파일 권한")
    dlg.setModal(True)
    dlg.setMinimumWidth(400)
    dlg.setMaximumWidth(440)
    dlg.setStyleSheet(_dialog_style(p))

    title = QLabel("워크플로 파일이 있어 권한이 하나 더 필요해요")
    title.setObjectName("wizTitle")
    title.setWordWrap(True)

    why = QLabel(
        "이 폴더에 .github/workflows 파일이 있습니다. "
        "이 파일을 바꾸려면 「repo」 말고 「workflow」 권한도 있어야 합니다."
    )
    why.setObjectName("wizLead")
    why.setWordWrap(True)

    steps = QLabel(
        "1. 아래에서 새 키 만들기 (repo · workflow 미리 체크됨)\n"
        "2. 만료 90일 권장\n"
        "3. 생성 → 복사 → 다시 연결"
    )
    steps.setObjectName("wizBox")
    steps.setWordWrap(True)

    detail = _DetailToggle(
        "classic 키는 웹에서 「workflow」를 추가할 수 있습니다. "
        "추가한 뒤 설정 → 「권한 다시 확인」을 누르세요.\n"
        "워크플로 파일이 없는 저장소라면 이 권한은 필요 없습니다 — "
        "그래서 기본 연결 화면에서는 요청하지 않습니다."
    )

    btn_create = QPushButton("1. 새 키 만들기")
    btn_create.setObjectName("btnPrimary")
    btn_create.setDefault(True)
    btn_create.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl(workflow_pat_create_url()))
    )

    reconnect = {"go": False}

    def _reconnect() -> None:
        reconnect["go"] = True
        dlg.accept()

    btn_again = QPushButton("3. 다시 연결")
    btn_again.setObjectName("btnPrimary")
    if offer_reconnect:
        btn_again.clicked.connect(_reconnect)
    else:
        btn_again.hide()

    btn_close = QPushButton("닫기")
    btn_close.setObjectName("btnGhost")
    btn_close.clicked.connect(dlg.reject)

    actions = QHBoxLayout()
    actions.setSpacing(8)
    actions.addWidget(btn_create, 1)
    if offer_reconnect:
        actions.addWidget(btn_again, 1)

    bottom = QHBoxLayout()
    bottom.addWidget(btn_close)
    bottom.addStretch(1)

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(16, 14, 16, 12)
    lay.setSpacing(8)
    lay.addWidget(title)
    lay.addWidget(why)
    lay.addWidget(steps)
    lay.addLayout(actions)
    lay.addWidget(detail)
    lay.addLayout(bottom)

    dlg.exec()
    return bool(reconnect["go"])


def _warn_soft_bg(p: Palette) -> str:
    """Amber panel fill — light mock #fbf6ee / #fff8e8, dark Settings-like."""
    return "#2e2a1e" if p.name == "dark" else "#fbf6ee"


def _away_banner_bg(p: Palette) -> str:
    return "#2e2a1e" if p.name == "dark" else "#fff8e8"


def _away_banner_border(p: Palette) -> str:
    return "#6b5a28" if p.name == "dark" else "#e0c97a"


def _away_banner_text(p: Palette) -> str:
    return "#d4c48a" if p.name == "dark" else "#5c4a12"


def _dialog_style(p: Palette) -> str:
    """Connect / PAT help dialogs — light + dark via ``active_palette()``."""
    warn_bg = _warn_soft_bg(p)
    away_bg = _away_banner_bg(p)
    away_bd = _away_banner_border(p)
    away_fg = _away_banner_text(p)
    return f"""
    QDialog {{
        background: {p.bg_window};
    }}
    QDialog#connectWebDialog {{
        background: {p.bg_window};
    }}
    QWidget#connOuter {{
        background: {p.bg_window};
    }}
    QLabel#wizTitle {{
        color: {p.text};
        font-size: 17px;
        font-weight: 600;
        background: transparent;
        border: none;
    }}
    QLabel#wizLead {{
        color: {p.text_secondary};
        font-size: 13px;
        background: transparent;
        border: none;
    }}
    QLabel#wizMeta {{
        color: {p.text_muted};
        font-size: 12.5px;
        background: transparent;
        border: none;
    }}
    QLabel#wizBox {{
        color: {p.text_secondary};
        font-size: 12.5px;
        background: {p.bg_muted};
        border: 1px solid {p.border_soft};
        border-radius: 8px;
        padding: 10px 12px;
    }}
    QLabel#wizProgress {{
        color: {p.primary};
        font-size: 12.5px;
        font-weight: 600;
        font-family: "IBM Plex Mono", Consolas, monospace;
        background: transparent;
        border: none;
    }}
    QLabel#wizDetail {{
        color: {p.text_muted};
        font-size: 12px;
        padding: 4px 2px;
    }}
    QFrame#connCard {{
        background: {p.bg_window};
        border: none;
    }}
    QFrame#connHeader {{
        background: {p.bg_bar};
        border: none;
        border-bottom: 1px solid {p.border_soft};
    }}
    QFrame#connTrack {{
        background: {p.bg_bar};
        border: 1px solid {p.border_divider};
        border-radius: 7px;
    }}
    QFrame#connGuideCard {{
        background: {p.bg_window};
        border: 1px solid {p.border};
        border-radius: 14px;
    }}
    QWidget#connGuideOuter {{
        background: {p.bg_window};
    }}
    QFrame#flowProgressTrack {{
        background: {p.border_divider};
        border: none;
        max-height: 3px;
        min-height: 3px;
    }}
    QFrame#flowProgressFill {{
        background: {p.primary};
        border: none;
        max-height: 3px;
        min-height: 3px;
    }}
    QLabel#flowHeaderTitle {{
        font-size: 12.5px;
        color: {p.text_muted};
        background: transparent;
        border: none;
    }}
    QPushButton#flowBack {{
        background: transparent;
        color: {p.text};
        border: none;
        font-size: 17px;
        padding: 0 4px;
        min-width: 28px;
        max-width: 28px;
    }}
    QPushButton#flowBack:disabled {{
        color: {p.border_input};
    }}
    QPushButton#flowBack:hover:!disabled {{
        color: {p.primary};
    }}
    QLabel#flowHeroTitle {{
        font-size: 24px;
        font-weight: 700;
        color: {p.text};
        background: transparent;
        border: none;
        letter-spacing: -0.4px;
    }}
    QLabel#flowHeroLead {{
        font-size: 14.5px;
        color: {p.text_muted};
        background: transparent;
        border: none;
    }}
    QFrame#flowOptionCard {{
        background: {p.bg_muted};
        border: 2px solid transparent;
        border-radius: 16px;
    }}
    QFrame#flowOptionCard:hover {{
        background: {p.hover_muted};
    }}
    QFrame#flowOptionCard[selected="true"] {{
        background: {p.bg_window};
        border: 2px solid {p.primary};
    }}
    QLabel#flowOptionTitle {{
        font-size: 16px;
        font-weight: 600;
        color: {p.text};
        background: transparent;
        border: none;
    }}
    QLabel#flowOptionBody {{
        font-size: 13.5px;
        color: {p.text_muted};
        background: transparent;
        border: none;
    }}
    QLabel#flowOptionTag {{
        font-size: 11px;
        font-weight: 600;
        color: {p.text_on_primary};
        background: {p.primary};
        border: none;
        border-radius: 999px;
        padding: 3px 9px;
    }}
    QFrame#flowIntroRow {{
        background: {p.bg_muted};
        border: none;
        border-radius: 12px;
    }}
    QLabel#flowIntroNum {{
        font-size: 12px;
        font-weight: 600;
        color: {p.primary};
        background: {p.bg_window};
        border: none;
        border-radius: 11px;
        min-width: 22px;
        max-width: 22px;
        min-height: 22px;
        max-height: 22px;
        qproperty-alignment: AlignCenter;
    }}
    QLabel#flowIntroText {{
        font-size: 13.5px;
        color: {p.text_secondary};
        background: transparent;
        border: none;
    }}
    QPushButton#flowCta {{
        background: {p.primary};
        color: {p.text_on_primary};
        border: 1px solid {p.primary};
        border-radius: 14px;
        font-size: 16px;
        font-weight: 600;
        min-height: 56px;
        padding: 0 20px;
    }}
    QPushButton#flowCta:hover {{
        background: {p.primary_hover};
    }}
    QPushButton#flowCta:disabled {{
        background: {p.bg_muted};
        color: {p.text_disabled};
        border: 1px solid {p.bg_muted};
    }}
    QFrame#connBrowser {{
        background: {p.bg_input};
        border: 1px solid {p.border_input};
        border-radius: 7px;
    }}
    QFrame#connAddrBar {{
        background: {p.bg_bar};
        border: none;
        border-bottom: 1px solid {p.border_soft};
    }}
    QFrame#connUrlBox {{
        background: {p.bg_window};
        border: 1px solid {p.border_input};
        border-radius: 4px;
        min-height: 24px;
        max-height: 24px;
    }}
    QLineEdit#connUrlInner {{
        background: transparent;
        border: none;
        padding: 0;
        font-size: 11.5px;
        color: {p.text_secondary};
        font-family: "IBM Plex Mono", Consolas, monospace;
        min-height: 20px;
        max-height: 22px;
    }}
    QLineEdit#connUrl {{
        background: {p.bg_window};
        border: 1px solid {p.border_input};
        border-radius: 4px;
        padding: 2px 10px;
        font-size: 11.5px;
        color: {p.text_secondary};
        font-family: "IBM Plex Mono", Consolas, monospace;
        min-height: 22px;
        max-height: 24px;
    }}
    QLabel#connLock {{
        font-size: 10px;
        color: {p.primary};
        border: none;
        background: transparent;
    }}
    QLabel#connUrlOnly {{
        font-size: 11px;
        color: {p.text_muted};
        border: none;
        background: transparent;
    }}
    QFrame#connWatch {{
        background: {p.bg_hint};
        border-left: 3px solid {p.primary};
        border-top: none;
        border-right: none;
        border-bottom: none;
        border-radius: 0 6px 6px 0;
    }}
    QFrame#connWatchWarn {{
        background: {warn_bg};
        border-left: 3px solid {p.warn_border};
        border-top: none;
        border-right: none;
        border-bottom: none;
        border-radius: 0 6px 6px 0;
    }}
    QLabel#connWatchTag {{
        font-size: 12.5px;
        font-weight: 600;
        color: {p.primary};
        background: transparent;
        border: none;
    }}
    QLabel#connWatchTagWarn {{
        font-size: 12.5px;
        font-weight: 600;
        color: {p.warn_text};
        background: transparent;
        border: none;
    }}
    QFrame#connFooter {{
        background: {p.bg_bar};
        border: none;
        border-top: 1px solid {p.border_divider};
    }}
    QFrame#connAwayBanner {{
        background: {away_bg};
        border: 1px solid {away_bd};
        border-radius: 8px;
    }}
    QLabel#connAwayBannerText {{
        font-size: 12.5px;
        font-weight: 500;
        color: {away_fg};
        border: none;
        background: transparent;
    }}
    QPushButton#connAwayCancel {{
        background: {p.bg_window};
        color: {p.text};
        border: 1px solid {p.border_outline};
        border-radius: 5px;
        padding: 4px 12px;
        font-weight: 500;
        font-size: 12px;
        min-height: 28px;
    }}
    QPushButton#connAwayCancel:hover {{
        background: {p.bg_hint};
    }}
    QWidget#connSessionChoice {{
        background: {p.bg_window};
        border: none;
    }}
    QWidget#connLoadingPanel {{
        background: {p.bg_window};
        border: none;
    }}
    QLabel#connLoadingSpin {{
        font-size: 42px;
        color: {p.primary};
        border: none;
        background: transparent;
    }}
    QLabel#connLoadingText {{
        font-size: 14px;
        font-weight: 500;
        color: {p.text_secondary};
        border: none;
        background: transparent;
    }}
    QProgressBar#connLoadingBar {{
        background: {p.border_divider};
        border: none;
        border-radius: 3px;
        max-height: 6px;
        min-height: 6px;
    }}
    QProgressBar#connLoadingBar::chunk {{
        background: {p.primary};
        border-radius: 3px;
    }}
    QLabel#connSessionTitle {{
        font-size: 16px;
        font-weight: 600;
        color: {p.text};
        border: none;
        background: transparent;
    }}
    QLabel#connSessionLead {{
        font-size: 13px;
        color: {p.text_secondary};
        border: none;
        background: transparent;
    }}
    QComboBox#connExpiryCombo {{
        background: {p.bg_window};
        border: 1px solid {p.border_input};
        border-radius: 6px;
        padding: 6px 10px;
        min-height: 28px;
        font-size: 12.5px;
        color: {p.text};
    }}
    QComboBox#connExpiryCombo::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox#connExpiryCombo QAbstractItemView {{
        background: {p.bg_window};
        color: {p.text};
        border: 1px solid {p.border_input};
        selection-background-color: {p.primary};
        selection-color: {p.text_on_primary};
    }}
    QPushButton#connNavMini {{
        background: {p.bg_window};
        border: 1px solid {p.border_input};
        border-radius: 4px;
        min-width: 18px;
        max-width: 18px;
        min-height: 18px;
        max-height: 18px;
        padding: 0;
        font-size: 10px;
        color: {p.text_muted};
    }}
    QPushButton#connNavMini:disabled {{
        color: {p.text_disabled};
    }}
    QLineEdit#patEdit {{
        padding: 10px 13px;
        font-size: 13px;
        border: 1px solid {p.border_input};
        border-radius: 6px;
        background: {p.bg_input};
        color: {p.text};
        font-family: "IBM Plex Mono", Consolas, monospace;
        min-height: 40px;
        selection-background-color: {p.primary};
    }}
    QPushButton#btnPrimary {{
        background: {p.primary};
        color: {p.text_on_primary};
        border: 1px solid {p.primary};
        border-radius: 6px;
        padding: 8px 26px;
        font-weight: 600;
        font-size: 13.5px;
        min-height: 40px;
    }}
    QPushButton#btnPrimary:hover {{
        background: {p.primary_hover};
    }}
    QPushButton#btnPrimary:disabled {{
        background: {p.bg_muted};
        color: {p.text_disabled};
        border: 1px solid {p.border_soft};
    }}
    QPushButton#btnSecondary {{
        background: {p.bg_window};
        color: {p.text};
        border: 1px solid {p.border_outline};
        border-radius: 5px;
        padding: 8px 16px;
        font-weight: 500;
        font-size: 12.5px;
        min-height: 36px;
    }}
    QPushButton#btnSecondary:hover {{
        background: {p.bg_hint};
    }}
    QPushButton#btnSecondary:disabled {{
        background: {p.bg_muted};
        color: {p.text_disabled};
        border: 1px solid {p.border_soft};
    }}
    QPushButton#btnGhost {{
        background: transparent;
        color: {p.text_muted};
        border: none;
        padding: 4px 6px;
        font-size: 12.5px;
    }}
    QPushButton#btnGhost:hover {{
        color: {p.text};
    }}
    """


class _DetailToggle(QWidget):
    """Collapsed-by-default extra tips to keep the dialog short."""

    def __init__(self, body: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._open = False
        self._btn = QPushButton("자세히 ▾")
        self._btn.setObjectName("btnGhost")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._toggle)
        self._body = QLabel(body)
        self._body.setObjectName("wizDetail")
        self._body.setWordWrap(True)
        self._body.hide()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self._btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._body)

    def _toggle(self) -> None:
        self._open = not self._open
        self._body.setVisible(self._open)
        self._btn.setText("접기 ▴" if self._open else "자세히 ▾")


class _FlowMethodIcon(QWidget):
    """Painted method glyph — app window or globe+egress (palette-aware)."""

    def __init__(
        self,
        kind: str,
        *,
        primary: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._kind = kind  # "app" | "browser"
        self._primary = bool(primary)
        self.setFixedSize(40, 40)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        pal = active_palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Rounded tile
        tile = QRectF(0.5, 0.5, 39.0, 39.0)
        if self._primary:
            p.setBrush(QColor(pal.primary))
            p.setPen(Qt.PenStyle.NoPen)
            fg = QColor(pal.text_on_primary)
        else:
            p.setBrush(QColor(pal.bg_muted))
            p.setPen(QPen(QColor(pal.border_soft), 1.0))
            fg = QColor(pal.text_secondary)
        p.drawRoundedRect(tile, 11.0, 11.0)

        pen = QPen(fg, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        if self._kind == "app":
            self._paint_app_window(p, fg)
        else:
            self._paint_browser_globe(p, fg)
        p.end()

    def _paint_app_window(self, p: QPainter, fg: QColor) -> None:
        # Compact app window: frame + title bar + three dots + content line
        win = QRectF(9.5, 11.0, 21.0, 17.5)
        p.drawRoundedRect(win, 2.5, 2.5)
        # Title bar
        p.drawLine(
            win.left() + 0.5,
            win.top() + 5.0,
            win.right() - 0.5,
            win.top() + 5.0,
        )
        # Traffic-light dots
        p.setBrush(fg)
        p.setPen(Qt.PenStyle.NoPen)
        for i, x in enumerate((win.left() + 3.2, win.left() + 7.0, win.left() + 10.8)):
            del i
            p.drawEllipse(QRectF(x, win.top() + 1.6, 2.2, 2.2))
        # Content hint lines
        p.setPen(QPen(fg, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        y0 = win.top() + 9.0
        p.drawLine(win.left() + 3.5, y0, win.right() - 3.5, y0)
        p.drawLine(win.left() + 3.5, y0 + 3.5, win.left() + 12.5, y0 + 3.5)

    def _paint_browser_globe(self, p: QPainter, fg: QColor) -> None:
        # Globe (left) + egress arrow (top-right)
        cx, cy, r = 16.5, 21.0, 8.2
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        # Meridian
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.quadTo(cx + r * 0.55, cy, cx, cy + r)
        path.moveTo(cx, cy - r)
        path.quadTo(cx - r * 0.55, cy, cx, cy + r)
        p.drawPath(path)
        # Latitude
        p.drawLine(cx - r + 0.8, cy, cx + r - 0.8, cy)
        # Outbound arrow
        p.setPen(QPen(fg, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(24.5, 12.5, 31.5, 12.5)
        p.drawLine(31.5, 12.5, 31.5, 19.5)
        p.drawLine(24.0, 20.0, 31.5, 12.5)


class _FlowOptionCard(QFrame):
    """시안 「연결 흐름」방식 선택 카드 — 클릭 한 번에 경로 확정."""

    clicked = Signal()

    def __init__(
        self,
        *,
        icon_kind: str,
        title: str,
        body: str,
        tag: str = "",
        primary_icon: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("flowOptionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        self._selected = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        icon = _FlowMethodIcon(icon_kind, primary=primary_icon)
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(5)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("flowOptionTitle")
        title_row.addWidget(t)
        if tag:
            tag_lab = QLabel(tag)
            tag_lab.setObjectName("flowOptionTag")
            title_row.addWidget(tag_lab)
        title_row.addStretch(1)
        text_col.addLayout(title_row)
        b = QLabel(body)
        b.setObjectName("flowOptionBody")
        b.setWordWrap(True)
        text_col.addWidget(b)
        lay.addLayout(text_col, 1)
        self._apply_selected_style()

    def set_selected(self, on: bool) -> None:
        self._selected = bool(on)
        self._apply_selected_style()

    def _apply_selected_style(self) -> None:
        pal = active_palette()
        if self._selected:
            self.setStyleSheet(
                f"QFrame#flowOptionCard {{"
                f"background:{pal.bg_window};"
                f"border:2px solid {pal.primary};"
                f"border-radius:16px;}}"
            )
        else:
            self.setStyleSheet(
                f"QFrame#flowOptionCard {{"
                f"background:{pal.bg_muted};"
                f"border:2px solid transparent;"
                f"border-radius:16px;}}"
                f"QFrame#flowOptionCard:hover {{"
                f"background:{pal.hover_muted};}}"
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


# Guided classic PAT path. Browser work is ONE screen (no click-sync).
# Indices match _STEPS / stacked pages.
_STEP_START = 0
_STEP_BROWSER = 1
_STEP_WORK = 2
_STEP_PASTE = 3

_STEPS: tuple[tuple[str, str], ...] = (
    (
        "시작",
        "클론업이 GitHub와 이야기하려면 「키」가 필요합니다.\n"
        "키는 비밀번호 대용이며, 이 컴퓨터에만 저장됩니다.\n"
        "\n"
        "만들고 올리기(새 저장소)를 쓰려면 classic 키를 만듭니다.",
    ),
    (
        "브라우저 열기",
        "아래 버튼을 누르면 GitHub가 열립니다.\n"
        "바로 키 화면이 열릴 수도 있고, 먼저 로그인·인증 화면이 열릴 수도 있습니다.",
    ),
    (
        "브라우저에서 진행",
        "이 창은 브라우저를 따라 한 칸씩 넘어가지 않습니다.\n"
        "브라우저에서 아래를 순서대로 하신 뒤, 마지막에 키를 복사하세요.\n"
        "복사되면 이 창이 붙여넣기로 자동 이동합니다.\n"
        "\n"
        "① 로그인·인증\n"
        "   · 처음: 계정 로그인 → 이메일 코드 또는 패스키\n"
        "   · 이미 계정 있음: 바로 키 화면이거나, 코드·패스키만\n"
        "② Expiration(만료) — 90일 이상 권장\n"
        "③ Select scopes에서 「repo」 한 줄만 켜기\n"
        "   (repo:status / public_repo 만으로는 부족)\n"
        "④ Generate token\n"
        "⑤ 초록 ghp_… 키 전체 복사 (이 화면을 닫으면 다시 안 보임)",
    ),
    (
        "붙여넣기",
        "키가 칸에 들어왔는지 확인한 뒤 「연결」을 누르세요.\n"
        "(브라우저에서 복사만 해도 이 단계로 올 수 있습니다.)",
    ),
)


# Only while guiding over the browser (not on 시작 / 붙여넣기).
# High transparency (~90% clear) so the browser behind stays easy to see.
_CONNECT_GUIDE_OPACITY = 0.10

# Clipboard auto-advance: detect a copied PAT without sniffing browser traffic.
_TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")


def _looks_like_github_token(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 20 or " " in t or "\n" in t:
        return False
    return any(t.startswith(p) for p in _TOKEN_PREFIXES)


# Web-mode stack (시안 「연결 흐름」): intro → choice → WebView (lazy Path A)
_WEB_PAGE_INTRO = 0
_WEB_PAGE_CHOICE = 1
_WEB_PAGE_WEB = 2


class ConnectGitHubWizard(QDialog):
    """
    PAT connect wizard.

    Path A: embedded Qt WebEngine (this dialog only).
    Path B: user chooses external browser → this dialog closes, then
    ``ExternalBrowserPatGuide`` runs alone (main_window). Never nested.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        reauth: bool = False,
        log: Callable[[str], None] | None = None,
    ) -> None:
        # No QWidget parent → dragging this dialog does not raise the main window.
        self._anchor = parent
        super().__init__(None)
        self._ui_log = log
        self._token = ""
        self._token_expires_at: str | None = None  # from WebView page scrape
        self._pat_note = ""  # Note used on GitHub create form
        self._want_device = False
        self._want_external = False  # Path B: close wizard, main runs Guide alone
        self._reauth = reauth
        self._accepted_logged = False
        self._via_fine = False
        self._browser_opened = False
        self._clip_seen = ""
        self._web_pane = None
        self._ui_now = 0
        self._ui_max = 0
        self._web_live_stage = None  # GitHubPageStage | None
        self._key_row: QWidget | None = None
        self._key_note: QLabel | None = None
        self._web_cta: QPushButton | None = None  # legacy; unused (auto-finish)
        self._web_cta_note: QLabel | None = None
        self._web_back_footer: QPushButton | None = None  # footer 「← 이전」
        self._web_url: QLineEdit | None = None
        self._web_back_btn: QPushButton | None = None
        self._web_fwd_btn: QPushButton | None = None
        self._web_url_editing = False
        # Off-family URL → countdown back to classic tokens/new
        self._away_banner: QFrame | None = None
        self._away_banner_lab: QLabel | None = None
        self._away_timer: QTimer | None = None
        self._away_secs_left = 0
        self._away_countdown_active = False
        # Existing WebEngine GitHub session: keep vs logout before first load
        self._pending_web_url: str = ""
        self._browser_stack: QStackedWidget | None = None
        self._session_choice: QWidget | None = None
        self._loading_panel: QWidget | None = None
        self._loading_spin_lab: QLabel | None = None
        self._loading_text_lab: QLabel | None = None
        self._loading_spin_timer: QTimer | None = None
        self._loading_spin_i = 0
        self._session_status_lab: QLabel | None = None
        self._session_awaiting_choice = False  # True until keep/logout clicked
        self._session_probing = False  # cookie check in progress (choice UI hidden)
        self._web_page_loading = False  # WebView loadStarted…Finished
        self._session_confirm_phase = ""  # "" | "pre" | "post"
        self._session_login_confirm_done = False  # post-login confirm once
        self._saw_github_login_page = False  # fresh login vs existing session
        self._session_resume_url = ""  # URL to restore after post-login confirm
        self._track_host: QWidget | None = None
        self._track_lay: QHBoxLayout | None = None
        self._web_watch: QFrame | None = None
        self._web_watch_tag: QLabel | None = None
        self._web_watch_body: QLabel | None = None
        self._web_counter: QLabel | None = None
        self._web_step_name: QLabel | None = None
        self._web_stage_title: QLabel | None = None
        self._web_hint: QLabel | None = None
        self._btn_switch_external: QPushButton | None = None
        self._expiry_combo: QComboBox | None = None
        self._expiry_lab: QLabel | None = None
        self._external_guide = None  # must stay unused (no nested guide)
        from app.ui.connect_webview import webengine_available

        self._use_web = webengine_available()
        p = active_palette()

        self.setWindowTitle("CloneUp — GitHub 연결")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowOpacity(1.0)
        # Normal chrome: title bar + close (X). Never frameless / FullScreen.
        # Do not use WindowStaysOnTopHint — other apps (browser) must be able
        # to come in front of this dialog.
        # Always include Maximize in the initial flags. Toggling
        # WindowMaximizeButtonHint via setWindowFlag() while this
        # ApplicationModal dialog is in exec() **hides** the window on
        # Windows and ends exec() as Rejected — main then logs
        # 「연결 안내 취소」 even though WebView may still issue a PAT.
        # Intro/choice pages keep Maximize disabled in practice via
        # fixed size + changeEvent (reject maximize on narrow pages).
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        try:
            from app.ui.icons import load_app_icon

            ic = load_app_icon()
            if not ic.isNull():
                self.setWindowIcon(ic)
        except Exception:
            pass
        if self._use_web:
            self.setObjectName("connectWebDialog")
            # Soft floor for choice; WebView path raises mins in _fit_web_dialog.
            # Do not use 640×360 here — that alone elongates the choice card.
            self.setMinimumSize(440, 280)
            # Do not call adjustSize() in web mode — it collapses QWebEngineView.
        else:
            self.setMinimumWidth(440)
            self.setMaximumWidth(520)
            self.setMinimumHeight(0)
        self.setStyleSheet(_dialog_style(p))

        self._progress = QLabel()
        self._progress.setObjectName("wizProgress")
        self._progress.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        if self._use_web:
            # 시안 「연결 흐름」: intro → choice → WebView(lazy Path A).
            # WebEngine stays out of the stack until Path A (size thrash).
            self._stack.addWidget(self._page_intro())
            self._stack.addWidget(self._page_choice())
            self._intro_index = _WEB_PAGE_INTRO
            self._choice_index = _WEB_PAGE_CHOICE
            self._web_index = -1
            self._paste_index = -1
            self._web_page_built = False
            self._progress.hide()  # thin bar lives inside flow pages
        else:
            for i, (title, body) in enumerate(_STEPS):
                if i == _STEP_PASTE:
                    self._stack.addWidget(self._page_paste(title, body))
                else:
                    self._stack.addWidget(self._page_guide(i, title, body))
            self._intro_index = -1
            self._choice_index = -1
            self._web_index = -1
            self._paste_index = _STEP_PASTE

        self._clip_timer = QTimer(self)
        self._clip_timer.setInterval(500)
        self._clip_timer.timeout.connect(self._poll_clipboard_for_token)

        root = QVBoxLayout(self)
        if self._use_web:
            # 시안: 바깥 회색(#e8e6e1) + 카드 주변 여백
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
        else:
            root.setContentsMargins(18, 16, 18, 14)
            root.setSpacing(10)
        root.addWidget(self._progress)
        root.addWidget(self._stack, 1)
        self._suppress_state_fit = False
        self._fitting_choice = False
        self._auto_finish_pending = False
        self._choice_size: tuple[int, int] | None = None
        self._clamping_choice = False
        self._normal_fit_gen = 0
        self._normal_fit_expected = 0
        if self._use_web:
            # 시안 step0: 항상 「GitHub 계정을 연결할게요」인트로부터
            # (재연결이어도 동일 — 한 화면에 하나만)
            self._go(self._intro_index)
            # Final size applied in showEvent → _fit_choice_dialog (compact)
        else:
            self._go(_STEP_START)
            self._place_center_on_anchor()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Intro/choice must always re-fit: a remembered Maximized / tall-thin
        # "normal" geometry on 1920×1080 broke the first-guidance card.
        if self._use_web and self._on_flow_narrow_page():
            # 0ms + delayed: first paint, then after restore chrome settles.
            QTimer.singleShot(0, self._fit_choice_dialog)
            QTimer.singleShot(50, self._fit_choice_dialog)
        self._place_away_banner()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Choice pages: clamp without setFixedSize (Fixed + DPR≈2 caused
        # QWindowsWindow::setGeometry spam: want 1000×1054 vs max 500×527).
        if (
            self._use_web
            and self._on_flow_narrow_page()
            and self._choice_size is not None
            and not self._clamping_choice
            and not getattr(self, "_fitting_choice", False)
        ):
            cw, ch = self._choice_size
            if self.width() != cw or self.height() != ch:
                self._clamping_choice = True
                try:
                    self.resize(cw, ch)
                finally:
                    self._clamping_choice = False
        self._place_away_banner()

    def _screen_for_dialog(self):
        from app.util.screen_fit import screen_for_widget

        return screen_for_widget(self, anchor=self._anchor)

    def _place_normal_web_size(self) -> None:
        """□ restore size: 16:9 client, centered in the work area (DPI-aware)."""
        if getattr(self, "_suppress_state_fit", False):
            return
        if self._on_flow_narrow_page():
            return
        # Ignore stale timers from maximize flicker during _fit_web_dialog.
        if getattr(self, "_normal_fit_gen", 0) != getattr(
            self, "_normal_fit_expected", 0
        ):
            return
        from app.util.screen_fit import place_normal_16x9

        place_normal_16x9(self, anchor=self._anchor)

    def _schedule_place_normal_web_size(self, *, delay_ms: int = 50) -> None:
        gen = int(getattr(self, "_normal_fit_gen", 0)) + 1
        self._normal_fit_gen = gen
        self._normal_fit_expected = gen
        QTimer.singleShot(delay_ms, self._place_normal_web_size)

    def _bump_normal_fit_gen(self) -> None:
        """Invalidate pending □-restore timers (used while entering maximize)."""
        self._normal_fit_gen = int(getattr(self, "_normal_fit_gen", 0)) + 1
        self._normal_fit_expected = -1

    def _on_flow_narrow_page(self) -> bool:
        """Intro or method-choice (시안 narrow) — not the WebView shell."""
        if not self._use_web:
            return False
        idx = self._stack.currentIndex()
        return idx in (
            getattr(self, "_intro_index", -1),
            getattr(self, "_choice_index", -1),
        )

    def _on_choice_page(self) -> bool:
        return self._on_flow_narrow_page()

    def _set_maximize_button(self, enabled: bool) -> None:
        """No-op for window flags while modal.

        Historically this called ``setWindowFlag(Maximize…)`` when entering
        WebView. On Windows that hides an ApplicationModal ``QDialog`` and
        can finish ``exec()`` as ``Rejected`` (main log: 연결 안내 취소)
        even after Generate token succeeded in the WebView.

        Maximize hint is set once in ``__init__``. Narrow intro/choice pages
        still block maximize via ``changeEvent`` + fixed size.
        """
        _ = enabled
        return

    def _fit_choice_dialog(self) -> None:
        """Compact window sized to intro/choice card (stable — no resize loop).

        Cross-check (1920×1080 vs 2880×1080): a Maximized / remembered tall
        "normal" geometry + ``resize()`` left a vertical strip on the right.
        Fix: leave Maximized, then ``setGeometry`` to an explicit centered
        client rect in ``availableGeometry`` (not move-after-resize).
        """
        from app.util.screen_fit import (
            center_client_in_available,
            clear_size_locks,
            compute_choice_dialog_size,
            guard_choice_client_size,
            read_screen_info,
            sanitize_choice_chrome,
            screen_for_widget,
        )
        from PySide6.QtCore import Qt

        if getattr(self, "_fitting_choice", False):
            return
        self._fitting_choice = True
        try:
            # Suppress changeEvent → _place_normal_web_size (fought this fit).
            self._suppress_state_fit = True
            self._set_maximize_button(False)
            st = self.windowState()
            if st & (
                Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen
            ):
                self.setWindowState(Qt.WindowState.WindowNoState)
            self.showNormal()
            clear_size_locks(self)
            # Size from the flow *card* (not the Expanding stack sizeHint).
            idx = self._stack.currentIndex()
            page = self._stack.widget(idx)
            card = None
            if page is not None:
                page.adjustSize()
                card = page.findChild(QFrame, "connGuideCard")
                if card is not None:
                    card.adjustSize()
            src = card if card is not None else page
            ph = src.sizeHint() if src is not None else None
            pw = int(ph.width()) if ph is not None and ph.width() > 0 else 500
            phh = int(ph.height()) if ph is not None and ph.height() > 0 else 480
            info = read_screen_info(screen_for_widget(self, anchor=self._anchor))
            if info is None:
                w, h = compute_choice_dialog_size(1920, 1040, hint_w=pw, hint_h=phh)
                ax = ay = 0
                aw, ah = 1920, 1040
            else:
                w, h = compute_choice_dialog_size(
                    info.available_w,
                    info.available_h,
                    hint_w=pw,
                    hint_h=phh,
                )
                ax, ay = info.available_x, info.available_y
                aw, ah = info.available_w, info.available_h
            # Measure chrome after showNormal — sanitize absurd restore deltas
            # that would collapse width to ~320 and lock a tall strip.
            try:
                fg = self.frameGeometry()
                geo = self.geometry()
                chrome_w = max(0, fg.width() - geo.width())
                chrome_h = max(0, fg.height() - geo.height())
            except Exception:
                chrome_w, chrome_h = 26, 71
            chrome_w, chrome_h = sanitize_choice_chrome(chrome_w, chrome_h)
            cx, cy, w, h = center_client_in_available(
                ax,
                ay,
                aw,
                ah,
                w,
                h,
                chrome_w=chrome_w,
                chrome_h=chrome_h,
            )
            w, h = guard_choice_client_size(w, h)
            self._choice_size = (w, h)
            # Soft minimum only — do NOT setMaximumSize(w,h) (DPI Fixed fight).
            # resizeEvent + _choice_size keep the compact shell; changeEvent
            # still rejects Maximize on narrow pages.
            self.setMinimumSize(min(w, 440), min(h, 280))
            self.setGeometry(cx, cy, w, h)
            try:
                self._wiz_log(
                    f"[연결] choice 기하 {w}x{h} @({cx},{cy}) "
                    f"avail={aw}x{ah} dpr="
                    f"{getattr(info, 'dpr', '?')}"
                )
            except Exception:
                pass
        except Exception:
            self._choice_size = (520, 500)
            clear_size_locks(self)
            self.setMinimumSize(440, 280)
            self.resize(520, 500)
            self._place_center_on_anchor()
        finally:
            self._fitting_choice = False
            QTimer.singleShot(300, self._clear_suppress_state_fit)
            # Second pass after Maximized→Normal chrome settles (high DPI).
            QTimer.singleShot(100, self._refit_choice_if_collapsed)

    def _refit_choice_if_collapsed(self) -> None:
        """If chrome race locked a strip, run fit again once settled."""
        if not self._use_web or not self._on_flow_narrow_page():
            return
        if getattr(self, "_fitting_choice", False):
            return
        try:
            w = int(self.width())
            h = max(1, int(self.height()))
        except Exception:
            return
        if w >= 450 and (w / h) >= 0.75:
            return
        QTimer.singleShot(0, self._fit_choice_dialog)

    def _clear_suppress_state_fit(self) -> None:
        self._suppress_state_fit = False

    def _fit_web_dialog(self) -> None:
        """
        Maximize into the taskbar-safe work area when entering WebView (Path A).

        □ restores to 16:9 via ``_place_normal_web_size()``.
        Does **not** use FullScreen — that breaks under Windows display scaling.

        Intentionally skips an intermediate ``_place_normal_web_size()`` before
        maximize — that path issued a cascade of ``setGeometry`` attempts
        (1280→1920→2592) against leftover choice fixed-size locks on Windows.
        """
        from app.util.screen_fit import apply_work_area_maximized, clear_size_locks

        try:
            self._suppress_state_fit = True
            self._bump_normal_fit_gen()
            self._choice_size = None
            # Unlock choice min size before maximizing.
            clear_size_locks(self)
            self.setMinimumSize(640, 360)
            self.setMaximumSize(16777215, 16777215)
            self._set_maximize_button(True)
            self.showNormal()
            apply_work_area_maximized(self, anchor=self._anchor)
        except Exception:
            clear_size_locks(self)
            self.setMinimumSize(640, 360)
            self.showMaximized()
        finally:
            # Longer than any leave-max → place_normal(50ms) from maximize flicker.
            QTimer.singleShot(600, self._clear_suppress_state_fit)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if not self._use_web:
            return
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QWindowStateChangeEvent

        if event.type() != QEvent.Type.WindowStateChange:
            return
        if getattr(self, "_suppress_state_fit", False):
            return

        old = Qt.WindowState.WindowNoState
        if isinstance(event, QWindowStateChangeEvent):
            old = event.oldState()
        now = self.windowState()

        # Intro/choice: reject Maximize (fixed compact card). Prevents the
        # Windows bug where Maximize + setFixedSize slides the window down-left.
        if self._on_flow_narrow_page():
            became_max = bool(now & Qt.WindowState.WindowMaximized) and not bool(
                old & Qt.WindowState.WindowMaximized
            )
            became_fs = bool(now & Qt.WindowState.WindowFullScreen) and not bool(
                old & Qt.WindowState.WindowFullScreen
            )
            if became_max or became_fs:
                self._suppress_state_fit = True
                self.setWindowState(Qt.WindowState.WindowNoState)
                QTimer.singleShot(0, self._fit_choice_dialog)
                QTimer.singleShot(50, self._fit_choice_dialog)
            return

        # Leaving maximized (or legacy FullScreen) on WebView → 16:9 restore
        leaving_max = bool(old & Qt.WindowState.WindowMaximized) and not bool(
            now & Qt.WindowState.WindowMaximized
        )
        leaving_fs = bool(old & Qt.WindowState.WindowFullScreen) and not bool(
            now & Qt.WindowState.WindowFullScreen
        )
        if (leaving_max or leaving_fs) and not self.isMinimized():
            self._schedule_place_normal_web_size(delay_ms=50)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Legacy FullScreen escape hatch; maximized uses title-bar □
        if (
            self._use_web
            and event.key() == Qt.Key.Key_Escape
            and bool(self.windowState() & Qt.WindowState.WindowFullScreen)
        ):
            self.showNormal()
            self._place_normal_web_size()
            event.accept()
            return
        super().keyPressEvent(event)

    def _place_center_on_anchor(self) -> None:
        if self._anchor is None:
            return
        try:
            if not self._use_web:
                self.adjustSize()
            ag = self._anchor.frameGeometry()
            g = self.frameGeometry()
            g.moveCenter(ag.center())
            self.move(g.topLeft())
        except Exception:
            pass

    def _place_bottom_right(self) -> None:
        """After browser opens: bottom-right (taskbar-safe available area)."""
        margin = 24
        try:
            self.adjustSize()
            screen = None
            if self._anchor is not None:
                screen = self._anchor.screen()
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is None:
                return
            avail = screen.availableGeometry()
            g = self.frameGeometry()
            x = avail.right() - g.width() - margin + 1
            y = avail.bottom() - g.height() - margin + 1
            self.move(max(avail.left() + margin, x), max(avail.top() + margin, y))
        except Exception:
            pass

    def _mark_browser_opened(self) -> None:
        first = not self._browser_opened
        self._browser_opened = True
        if first:
            self._place_bottom_right()
        if not self._clip_timer.isActive():
            self._clip_timer.start()

    def _stop_clipboard_watch(self) -> None:
        if self._clip_timer.isActive():
            self._clip_timer.stop()

    def _poll_clipboard_for_token(self) -> None:
        """
        When the user copies a GitHub PAT in the browser, jump to paste.

        We do **not** inspect browser URLs or network traffic — only the
        clipboard contents after the user has already copied the key.
        """
        if not self._browser_opened:
            return
        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        text = (clip.text() or "").strip()
        if not _looks_like_github_token(text):
            return
        if text == self._clip_seen:
            return
        self._clip_seen = text
        self._apply_detected_token(text)

    def _open_url_in_external_browser(self, url: str) -> None:
        """Open ``url`` in the OS browser and yield the screen (minimize).

        Clipboard watch stays on so a copied key can restore the dialog.
        """
        QDesktopServices.openUrl(QUrl(url))
        self._browser_opened = True
        if not self._clip_timer.isActive():
            self._clip_timer.start()
        # Get out of the way so the browser can be used comfortably
        self.showMinimized()

    def _restore_from_yield(self) -> None:
        """Bring the dialog back after external-browser yield / token detect."""
        if self.isMinimized():
            if self._use_web:
                from app.util.screen_fit import apply_work_area_maximized

                apply_work_area_maximized(self, anchor=self._anchor)
            else:
                self.showNormal()
        self.setWindowOpacity(1.0)
        self.raise_()
        self.activateWindow()

    def _wiz_log(self, message: str) -> None:
        """Tee connect-wizard lifecycle to terminal + optional main textLog."""
        from app.util.log_mask import mask_secrets_in_text

        line = mask_secrets_in_text(message or "")
        if not line.strip():
            return
        try:
            print(line)
        except Exception:
            pass
        if self._ui_log is not None:
            try:
                self._ui_log(line)
            except Exception:
                pass

    def _apply_detected_token(self, text: str) -> None:
        if hasattr(self, "_edit") and self._edit is not None:
            self._edit.setText(text)
        # Capture expiration scraped from the create/issued page (if any)
        if self._web_pane is not None:
            exp = getattr(self._web_pane, "last_token_expires_at", None)
            if exp:
                self._token_expires_at = str(exp)
        tok_ok = _looks_like_github_token((text or "").strip())
        self._wiz_log(
            f"[연결] 키 인식 len={len((text or '').strip())} "
            f"형식={'OK' if tok_ok else '아님'} "
            f"만료={self._token_expires_at or '—'}"
        )
        if self._use_web:
            if self._stack.currentIndex() != self._web_index:
                self._go_web()
            self.setWindowOpacity(1.0)
            # Jump guide to step 4 (키 복사) and reveal the key field.
            self._ui_max = 3
            self._paint_web_guide(3)
            self._sync_web_cta()
            if self._web_cta_note is not None:
                self._web_cta_note.setText("키를 인식했어요. 자동으로 연결합니다…")
        else:
            if self._stack.currentIndex() != _STEP_PASTE:
                self._go(_STEP_PASTE)
        self._restore_from_yield()
        # Screen / clipboard PAT → finish without requiring 「연결」 click
        self._schedule_auto_finish()

    def _schedule_auto_finish(self) -> None:
        """When a PAT is in the field, accept without a second click."""
        if self._auto_finish_pending:
            return
        raw = ""
        if hasattr(self, "_edit") and self._edit is not None:
            raw = (self._edit.text() or "").strip()
        if not _looks_like_github_token(raw):
            return
        self._auto_finish_pending = True
        self._wiz_log("[연결] 자동 연결 예약")
        QTimer.singleShot(0, self._run_auto_finish)

    def _run_auto_finish(self) -> None:
        self._auto_finish_pending = False
        # Do not require isVisible(). A brief hide from window-flag / state
        # changes must not drop a PAT that is already in the field — that
        # used to look like 「연결 안내 취소」 after a successful Generate.
        if self.result() == int(QDialog.DialogCode.Accepted):
            self._wiz_log("[연결] 자동 연결 생략 — 이미 Accepted")
            return
        raw = ""
        if hasattr(self, "_edit") and self._edit is not None:
            raw = (self._edit.text() or "").strip()
        if not _looks_like_github_token(raw):
            self._wiz_log("[연결] 자동 연결 중단 — 키 형식 아님")
            return
        self._wiz_log("[연결] 자동 연결 실행 → accept")
        self._finish()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._accepted_logged and self.result() != int(
            QDialog.DialogCode.Accepted
        ):
            has = bool((self._token or "").strip()) or (
                hasattr(self, "_edit")
                and _looks_like_github_token((self._edit.text() or "").strip())
            )
            self._wiz_log(
                "[연결] 창 닫힘 "
                + ("(키는 있었음)" if has else "(키 없음)")
            )
        self._dismiss_away_return_banner()
        self._stop_clipboard_watch()
        super().closeEvent(event)

    def reject(self) -> None:
        has = bool((self._token or "").strip()) or (
            hasattr(self, "_edit")
            and _looks_like_github_token((self._edit.text() or "").strip())
        )
        self._wiz_log(
            "[연결] reject "
            + ("— 키는 필드에 있었음" if has else "— 사용자 취소/닫기")
        )
        self._dismiss_away_return_banner()
        self._stop_clipboard_watch()
        super().reject()

    def accept(self) -> None:
        self._accepted_logged = True
        self._wiz_log(
            f"[연결] accept "
            f"external={self._want_external} device={self._want_device} "
            f"token_len={len((self._token or '').strip())} "
            f"만료={self._token_expires_at or '—'}"
        )
        self._dismiss_away_return_banner()
        self._stop_clipboard_watch()
        super().accept()

    def token(self) -> str:
        return self._token

    def token_expires_at(self) -> str | None:
        """ISO-8601 / ``none`` from WebView page scrape, if known."""
        return self._token_expires_at

    def token_note(self) -> str:
        """Note / name CloneUp put on the GitHub token create form."""
        return (self._pat_note or "").strip()

    def wants_device_flow(self) -> bool:
        return self._want_device

    def wants_external_browser(self) -> bool:
        """Path B: wizard closed so main can run ExternalBrowserPatGuide alone."""
        return bool(self._want_external)

    def _sync_opacity(self, index: int) -> None:
        """Translucent only on the browser-work screen after the browser opens."""
        over_browser = self._browser_opened and index == _STEP_WORK
        self.setWindowOpacity(
            _CONNECT_GUIDE_OPACITY if over_browser else 1.0
        )

    def _ensure_web_page(self) -> None:
        """Build the WebView stack page once (Path A only)."""
        if not self._use_web or getattr(self, "_web_page_built", False):
            return
        self._stack.addWidget(self._page_web())
        self._web_index = self._stack.count() - 1
        self._paste_index = self._web_index
        self._web_page_built = True

    def _go(self, index: int) -> None:
        if self._use_web:
            # INTRO · CHOICE · WEB (lazy) — never nest external guide here
            intro_i = getattr(self, "_intro_index", _WEB_PAGE_INTRO)
            choice_i = self._choice_index
            if index == intro_i:
                index = intro_i
            elif index == choice_i:
                index = choice_i
                self._dismiss_away_return_banner()
                self._pending_web_url = ""
                self._session_awaiting_choice = False
                self._session_probing = False
                self._session_confirm_phase = ""
                self._session_resume_url = ""
                if self._web_pane is not None:
                    try:
                        self._web_pane.set_automation_paused(False)
                    except Exception:
                        pass
                self._show_browser_web()
            else:
                self._ensure_web_page()
                index = self._web_index
                # Unlock choice fixed size before WebEngine page is shown.
                from app.util.screen_fit import clear_size_locks

                self._suppress_state_fit = True
                clear_size_locks(self)
                self.setMinimumSize(640, 360)
            self._stack.setCurrentIndex(index)
            self.setWindowOpacity(1.0)
            if index in (intro_i, choice_i):
                QTimer.singleShot(0, self._fit_choice_dialog)
                QTimer.singleShot(50, self._fit_choice_dialog)
            else:
                self._paint_web_guide(self._ui_now)
                QTimer.singleShot(0, self._fit_web_dialog)
            # Never adjustSize() here — it shrinks the WebEngine view.
            return
        n = len(_STEPS)
        index = max(0, min(index, n - 1))
        self._stack.setCurrentIndex(index)
        short = _STEPS[index][0]
        self._progress.setText(f"{index + 1} / {n}  ·  {short}")
        self._sync_opacity(index)
        self.adjustSize()
        if index == _STEP_PASTE:
            self._edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _go_web(self) -> None:
        from app.util.screen_fit import clear_size_locks

        self._ensure_web_page()
        # Unlock choice fixed size BEFORE swapping in WebEngine — otherwise Qt
        # tries ~1000px geometries against max 500×527 (console spam).
        self._suppress_state_fit = True
        clear_size_locks(self)
        self.setMinimumSize(640, 360)
        self._stack.setCurrentIndex(self._web_index)
        self.setWindowOpacity(1.0)
        if self._ui_now == 0 and self._ui_max == 0:
            self._paint_web_guide(0)
        else:
            self._paint_web_guide(self._ui_now)
        self._fit_web_dialog()

    def _remember_pat_note(self, url: str = "", note: str = "") -> None:
        n = (note or "").strip() or note_from_pat_create_url(url)
        if n:
            self._pat_note = n

    def _on_pat_create_note(self, note: str) -> None:
        """Sync from WebPane.load_url (auto-open / reissue / away-return)."""
        n = (note or "").strip()
        if n:
            self._pat_note = n

    def _open_create_page(self) -> None:
        # Classic + repo — required path for 「만들고 올리기」 (create repo).
        self._via_fine = False
        url, note = _pat_create_url()
        self._remember_pat_note(url, note)
        if self._use_web:
            self._start_web(url)
            return
        QDesktopServices.openUrl(QUrl(url))
        self._mark_browser_opened()
        self._go(_STEP_WORK)

    def _open_fine_and_paste(self) -> None:
        self._via_fine = True
        url, note = _pat_create_url_fine()
        self._remember_pat_note(url, note)
        if self._use_web:
            self._start_web(url)
            return
        QDesktopServices.openUrl(QUrl(url))
        self._mark_browser_opened()
        self._go(_STEP_WORK)

    def _reload_pat_create_fresh_note(self) -> None:
        """After Note collision — open classic form with a new CloneUp-date-time Note."""
        url, note = (
            _pat_create_url_fine() if self._via_fine else _pat_create_url()
        )
        self._remember_pat_note(url, note)
        if self._use_web and self._web_pane is not None:
            self._web_pane.load_url(url)
            if self._web_hint is not None:
                from app.ui.connect_webview import guide_lead

                self._web_hint.setText(
                    guide_lead("새 Note 이름으로 다시 열었습니다. Generate token을 누르세요.")
                )
            return
        QDesktopServices.openUrl(QUrl(url))

    def _start_web(self, url: str) -> None:
        """Open Web page; if a prior GitHub WebEngine session exists, ask first."""
        self._ensure_web_page()
        self._browser_opened = True
        self._pending_web_url = (url or "").strip()
        self._remember_pat_note(url)
        self._session_login_confirm_done = False
        self._saw_github_login_page = False
        self._session_confirm_phase = ""
        self._session_resume_url = ""
        if self._web_pane is not None:
            try:
                self._web_pane.set_automation_paused(False)
            except Exception:
                pass
        if not self._clip_timer.isActive():
            self._clip_timer.start()
        self._go_web()
        self._begin_session_gate()

    def _build_session_choice_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("connSessionChoice")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(40, 36, 40, 36)
        lay.setSpacing(14)
        lay.addStretch(1)

        title = QLabel("이전에 GitHub에 로그인한 세션이 남아 있습니다")
        title.setObjectName("connSessionTitle")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        lead = QLabel(
            "같은 계정으로 이어가려면 「유지하기」를 누르세요.\n"
            "다른 계정으로 하려면 「로그아웃하기」를 누른 뒤 다시 로그인합니다.\n"
            "선택하기 전에는 페이지를 열지 않습니다."
        )
        lead.setObjectName("connSessionLead")
        lead.setWordWrap(True)
        lead.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._session_status_lab = QLabel("세션을 확인하는 중…")
        self._session_status_lab.setObjectName("wizMeta")
        self._session_status_lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        btn_keep = QPushButton("기존 세션 유지하기")
        btn_keep.setObjectName("btnPrimary")
        btn_keep.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_keep.clicked.connect(self._on_session_keep)

        btn_logout = QPushButton("기존 세션 로그아웃하기")
        btn_logout.setObjectName("btnSecondary")
        btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_logout.clicked.connect(self._on_session_logout)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_keep)
        btn_row.addWidget(btn_logout)
        btn_row.addStretch(1)

        lay.addWidget(title)
        lay.addWidget(lead)
        lay.addSpacing(8)
        lay.addWidget(self._session_status_lab)
        lay.addSpacing(4)
        lay.addLayout(btn_row)
        lay.addStretch(2)
        # Buttons enabled only after probe confirms a session
        btn_keep.setEnabled(False)
        btn_logout.setEnabled(False)
        self._session_btn_keep = btn_keep
        self._session_btn_logout = btn_logout
        return panel

    def _build_loading_panel(self) -> QWidget:
        """Spinner page shown during session probe / page load (not white blank)."""
        panel = QWidget()
        panel.setObjectName("connLoadingPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(40, 36, 40, 36)
        lay.setSpacing(16)
        lay.addStretch(1)

        spin = QLabel(_SPIN_FRAMES[0])
        spin.setObjectName("connLoadingSpin")
        spin.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._loading_spin_lab = spin

        text = QLabel("잠시만요…")
        text.setObjectName("connLoadingText")
        text.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        text.setWordWrap(True)
        self._loading_text_lab = text

        bar = QProgressBar()
        bar.setObjectName("connLoadingBar")
        bar.setRange(0, 0)  # indeterminate busy
        bar.setTextVisible(False)
        bar.setFixedWidth(160)
        bar_row = QHBoxLayout()
        bar_row.addStretch(1)
        bar_row.addWidget(bar)
        bar_row.addStretch(1)

        lay.addWidget(spin)
        lay.addWidget(text)
        lay.addLayout(bar_row)
        lay.addStretch(2)

        self._loading_spin_timer = QTimer(self)
        self._loading_spin_timer.setInterval(90)
        self._loading_spin_timer.timeout.connect(self._tick_loading_spin)
        return panel

    def _tick_loading_spin(self) -> None:
        if self._loading_spin_lab is None:
            return
        self._loading_spin_i = (self._loading_spin_i + 1) % len(_SPIN_FRAMES)
        self._loading_spin_lab.setText(_SPIN_FRAMES[self._loading_spin_i])

    def _show_browser_loading(self, message: str = "잠시만요…") -> None:
        if self._loading_text_lab is not None:
            self._loading_text_lab.setText(message)
        if self._browser_stack is not None:
            self._browser_stack.setCurrentIndex(_STACK_LOADING)
        if self._loading_spin_timer is not None and not self._loading_spin_timer.isActive():
            self._loading_spin_timer.start()

    def _show_browser_web(self) -> None:
        if self._loading_spin_timer is not None:
            self._loading_spin_timer.stop()
        if self._browser_stack is not None:
            self._browser_stack.setCurrentIndex(_STACK_WEB)

    def _show_browser_session(self) -> None:
        if self._loading_spin_timer is not None:
            self._loading_spin_timer.stop()
        if self._browser_stack is not None:
            self._browser_stack.setCurrentIndex(_STACK_SESSION)

    def _on_web_load_started(self) -> None:
        if self._session_awaiting_choice or getattr(self, "_session_probing", False):
            return
        # Don't cover session UI; only when WebView is the active intent
        if self._browser_stack is not None and self._browser_stack.currentIndex() == _STACK_SESSION:
            return
        self._web_page_loading = True
        self._show_browser_loading("페이지를 불러오는 중…")

    def _on_web_load_finished_ui(self, ok: bool) -> None:
        _ = ok
        self._web_page_loading = False
        if self._session_awaiting_choice or getattr(self, "_session_probing", False):
            return
        if self._browser_stack is not None and self._browser_stack.currentIndex() == _STACK_SESSION:
            return
        self._show_browser_web()

    def _freeze_webview_while_session_ui(self) -> None:
        """Stop every WebView job while keep/logout choice is visible."""
        self._dismiss_away_return_banner()
        if self._web_pane is None:
            return
        try:
            self._web_pane.set_automation_paused(True)
        except Exception:
            pass

    def _begin_session_gate(self) -> None:
        """
        Probe cookies first — do **not** show the keep/logout panel until
        a session is confirmed (avoids flash when there is no session).

        - Session found → show keep/logout and wait.
        - No session → load WebView immediately (choice UI never appears).
        """
        from app.ui.webview_session import probe_github_webengine_session

        # Probe in progress: spinner only — never flash the "기존 세션" panel
        self._session_probing = True
        self._session_awaiting_choice = False
        self._session_confirm_phase = ""
        self._freeze_webview_while_session_ui()
        self._show_browser_loading("세션을 확인하는 중…")
        if self._web_pane is not None:
            try:
                self._web_pane._view.setUrl(QUrl("about:blank"))
            except Exception:
                pass

        url = self._pending_web_url
        profile = None
        if self._web_pane is not None:
            try:
                profile = self._web_pane.engine_profile()
            except Exception:
                profile = None
        if profile is None:
            self._session_probing = False
            self._reveal_webview_and_load(url)
            return

        def _done(has_session: bool) -> None:
            if not getattr(self, "_session_probing", False):
                return
            self._session_probing = False
            if has_session:
                self._session_confirm_phase = "pre"
                self._show_session_choice_ready(phase="pre")
                return
            # No session — choice UI was never shown
            self._session_awaiting_choice = False
            self._session_confirm_phase = ""
            self._reveal_webview_and_load(url)

        try:
            probe_github_webengine_session(profile, _done, parent=self)
        except Exception:
            self._session_probing = False
            self._session_awaiting_choice = False
            self._session_confirm_phase = ""
            self._reveal_webview_and_load(url)

    def _show_session_choice_ready(self, *, phase: str = "pre") -> None:
        """Wait for explicit keep or logout. ``phase``: pre (before load) | post."""
        self._session_awaiting_choice = True
        self._session_confirm_phase = phase
        self._freeze_webview_while_session_ui()
        self._show_browser_session()
        if self._session_status_lab is not None:
            if phase == "post":
                self._session_status_lab.setText(
                    "로그인된 세션이 확인되었습니다. "
                    "유지하거나 로그아웃을 고르세요."
                )
            else:
                self._session_status_lab.setText(
                    "아래에서 유지하거나 로그아웃을 고르세요."
                )
        keep = getattr(self, "_session_btn_keep", None)
        logout = getattr(self, "_session_btn_logout", None)
        if keep is not None:
            keep.setEnabled(True)
        if logout is not None:
            logout.setEnabled(True)

    def _pause_webview_for_post_login_confirm(self) -> None:
        """Existing-session login detected — hide WebView and ask again."""
        if self._session_login_confirm_done or self._session_awaiting_choice:
            return
        if self._saw_github_login_page:
            # User signed in fresh this visit — no second confirm
            self._session_login_confirm_done = True
            return
        cur = self._current_webview_url()
        self._session_resume_url = cur or self._pending_web_url or ""
        self._freeze_webview_while_session_ui()
        if self._web_pane is not None:
            # Kill page so nothing continues underneath the choice UI
            try:
                from PySide6.QtCore import QUrl

                self._web_pane._view.setUrl(QUrl("about:blank"))
            except Exception:
                pass
        self._show_session_choice_ready(phase="post")

    def _reveal_webview_and_load(self, url: str) -> None:
        # While waiting for keep/logout, block any accidental load
        if self._session_awaiting_choice:
            return
        if self._web_pane is not None:
            try:
                self._web_pane.set_automation_paused(False)
            except Exception:
                pass
        self._session_probing = False
        self._show_browser_loading("페이지를 불러오는 중…")
        target = (url or self._pending_web_url or "").strip()
        self._pending_web_url = ""
        if self._web_pane is not None and target:
            try:
                self._web_pane.load_url(target)
            except Exception:
                self._show_browser_web()
        else:
            self._show_browser_web()

    def _on_session_keep(self) -> None:
        phase = self._session_confirm_phase
        if self._session_status_lab is not None:
            self._session_status_lab.setText("세션을 유지하고 이동합니다…")
        self._session_awaiting_choice = False
        self._session_confirm_phase = ""
        if phase == "post":
            self._session_login_confirm_done = True
            resume = (self._session_resume_url or "").strip()
            self._session_resume_url = ""
            # Prefer token create so flow continues cleanly after blanking
            if not resume or resume.startswith("about:"):
                resume = self._pending_web_url
                if not resume:
                    resume, note = _pat_create_url()
                    self._remember_pat_note(resume, note)
            self._reveal_webview_and_load(resume)
            return
        url = self._pending_web_url
        self._reveal_webview_and_load(url)

    def _on_session_logout(self) -> None:
        """
        Discard WebEngine GitHub session reliably:

        1) Open ``/logout`` **while cookies still exist** (server invalidate)
        2) ``deleteAllCookies`` (persistent ``user_session`` is not a session cookie)
        3) Open classic token-create (redirects to Sign in when wiped)
        """
        from app.ui.webview_session import (
            GITHUB_LOGOUT_URL,
            clear_github_webengine_cookies,
        )

        phase = self._session_confirm_phase
        if self._session_status_lab is not None:
            self._session_status_lab.setText("세션을 지우는 중…")
        keep = getattr(self, "_session_btn_keep", None)
        logout_btn = getattr(self, "_session_btn_logout", None)
        if keep is not None:
            keep.setEnabled(False)
        if logout_btn is not None:
            logout_btn.setEnabled(False)

        if phase == "post":
            self._session_login_confirm_done = True
            self._session_resume_url = ""

        create_url, note = _pat_create_url()
        self._remember_pat_note(create_url, note)
        profile = None
        if self._web_pane is not None:
            try:
                profile = self._web_pane.engine_profile()
            except Exception:
                profile = None

        def _finish_to_create() -> None:
            if self._web_pane is not None:
                try:
                    self._web_pane.reset_connect_flow_state()
                    self._web_pane.set_automation_paused(False)
                except Exception:
                    pass
            self._token_nav_opened_reset()
            self._saw_github_login_page = False
            self._session_awaiting_choice = False
            self._session_confirm_phase = ""
            self._show_browser_loading("페이지를 불러오는 중…")
            if self._web_pane is not None:
                try:
                    self._web_pane.load_url(create_url, force=True)
                except Exception:
                    self._show_browser_web()

        def _wipe_then_create() -> None:
            if profile is None:
                _finish_to_create()
                return

            def _after_wipe() -> None:
                _finish_to_create()

            try:
                clear_github_webengine_cookies(profile, _after_wipe)
            except Exception:
                _finish_to_create()

        # Leave choice UI; keep automation paused until wipe finishes
        self._session_awaiting_choice = False
        self._session_confirm_phase = ""
        self._pending_web_url = ""
        self._freeze_webview_while_session_ui()
        self._show_browser_loading("세션을 지우는 중…")
        # Server-side logout first (cookies still present); force bypasses pause
        if self._web_pane is not None:
            try:
                self._web_pane.load_url(GITHUB_LOGOUT_URL, force=True)
            except Exception:
                pass
        # Then client cookie wipe + token-create
        QTimer.singleShot(1100, _wipe_then_create)

    def _token_nav_opened_reset(self) -> None:
        """Dialog-side flags tied to a discarded browser session."""
        self._dismiss_away_return_banner()
        self._ui_max = 0
        self._ui_now = 0

    def _page_guide(self, index: int, title: str, body: str) -> QWidget:
        # Inner column — when web dialog is maximized, center a readable card
        # so title/body are not stuck to the top-left corner.
        inner = QWidget()
        inner.setObjectName("connGuideInner")
        if self._use_web and index == _STEP_START:
            inner.setMaximumWidth(520)
            inner.setMinimumWidth(400)

        head = QLabel(title)
        head.setObjectName("wizTitle")
        head.setWordWrap(True)
        head.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        lead = QLabel(body)
        lead.setObjectName("wizLead")
        lead.setWordWrap(True)
        lead.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        lay = QVBoxLayout(inner)
        if self._use_web and index == _STEP_START:
            lay.setContentsMargins(28, 24, 28, 24)
            lay.setSpacing(14)
        else:
            lay.setContentsMargins(4, 4, 4, 4)
            lay.setSpacing(8)
        lay.addWidget(head)
        lay.addWidget(lead)

        if index == _STEP_START:
            detail = _DetailToggle(
                "키는 채팅·캡처·메일에 붙이지 마세요.\n"
                "만료되면 새 키를 만들어 다시 연결합니다.\n"
                "GitHub 영문: Tokens (classic) · Generate new token · repo.\n"
                "키 목록·세분 키는 설정에서 열 수 있습니다."
            )
            lay.addWidget(detail)

            if is_device_flow_allowed():
                btn_dev = QPushButton("개발용 장치 코드")
                btn_dev.setObjectName("btnGhost")
                btn_dev.clicked.connect(self._pick_device)
                lay.addWidget(btn_dev)

        # Primary actions per step
        nav = QHBoxLayout()
        nav.setSpacing(10)
        btn_cancel = QPushButton("취소")
        btn_cancel.setObjectName("btnGhost")
        btn_cancel.clicked.connect(self.reject)
        nav.addWidget(btn_cancel)

        if index > _STEP_START:
            btn_back = QPushButton("← 이전")
            btn_back.setObjectName("btnGhost")
            btn_back.clicked.connect(lambda: self._go(index - 1))
            nav.addWidget(btn_back)

        nav.addStretch(1)

        if index == _STEP_BROWSER:
            btn_open = QPushButton("브라우저에서 만들기")
            btn_open.setObjectName("btnPrimary")
            btn_open.setDefault(True)
            btn_open.setToolTip(
                "Tokens (classic) 새 키 페이지를 엽니다. scopes=repo 가 미리 켜져 있습니다."
            )
            btn_open.clicked.connect(self._open_create_page)
            nav.addWidget(btn_open)

            def _opened_manual() -> None:
                self._mark_browser_opened()
                self._go(_STEP_WORK)

            btn_next = QPushButton("열었어요 →")
            btn_next.setObjectName("btnSecondary")
            btn_next.clicked.connect(_opened_manual)
            nav.addWidget(btn_next)
        elif index == _STEP_WORK:
            # No mid-flow 「했어요」 — browser is the source of truth until copy.
            btn_next = QPushButton("키 복사했어요 →")
            btn_next.setObjectName("btnPrimary")
            btn_next.setDefault(True)
            btn_next.setToolTip("복사가 자동으로 안 잡히면 눌러 주세요.")
            btn_next.clicked.connect(lambda: self._go(_STEP_PASTE))
            nav.addWidget(btn_next)
        else:
            # Non-web START only
            btn_next = QPushButton("다음 →")
            btn_next.setObjectName("btnPrimary")
            btn_next.setDefault(True)
            btn_next.clicked.connect(lambda: self._go(index + 1))
            nav.addWidget(btn_next)

        lay.addSpacing(8)
        lay.addLayout(nav)
        return inner

    def _flow_progress_pct(self, *, intro: bool) -> float:
        """시안 progress: 시작 ~8%, 방식 선택 ~28%."""
        return 0.08 if intro else 0.28

    def _build_flow_progress(self, pct: float) -> QWidget:
        track = QFrame()
        track.setObjectName("flowProgressTrack")
        track.setFixedHeight(3)
        row = QHBoxLayout(track)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        fill = QFrame()
        fill.setObjectName("flowProgressFill")
        fill.setFixedHeight(3)
        rest = QWidget()
        rest.setFixedHeight(3)
        p = max(0.0, min(1.0, float(pct)))
        # Integer stretch weights (시안 진행 비율)
        fill_w = max(1, int(round(p * 1000)))
        rest_w = max(1, 1000 - fill_w)
        row.addWidget(fill, fill_w)
        row.addWidget(rest, rest_w)
        return track

    def _build_flow_header(self, *, back_enabled: bool, on_back) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 14, 20, 8)
        row.setSpacing(12)
        back = QPushButton("←")
        back.setObjectName("flowBack")
        back.setEnabled(back_enabled)
        back.setCursor(
            Qt.CursorShape.PointingHandCursor
            if back_enabled
            else Qt.CursorShape.ArrowCursor
        )
        if back_enabled and on_back is not None:
            back.clicked.connect(on_back)
        title = QLabel("GitHub 연결")
        title.setObjectName("flowHeaderTitle")
        row.addWidget(back, 0)
        row.addWidget(title, 0)
        row.addStretch(1)
        return bar

    def _flow_narrow_shell(
        self,
        *,
        progress_pct: float,
        back_enabled: bool,
        on_back,
        body: QWidget,
    ) -> QWidget:
        """시안 narrow 카드: 3px 진행바 + 헤더 + 본문 (위로 붙임)."""
        outer = QWidget()
        outer.setObjectName("connGuideOuter")
        outer.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        card = QFrame()
        card.setObjectName("connGuideCard")
        card.setMinimumWidth(480)
        card.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_flow_progress(progress_pct))
        lay.addWidget(
            self._build_flow_header(back_enabled=back_enabled, on_back=on_back)
        )
        lay.addWidget(body, 0)
        # Center horizontally: AlignTop alone does not stretch H, and on an
        # oversized shell the card looked like a tall strip stuck to one edge
        # (seen on 1920×1080). HCenter + Top keeps the 시안 card readable.
        outer_lay.addWidget(
            card,
            0,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        )
        return outer

    def _page_intro(self) -> QWidget:
        """시안 step0 — 「GitHub 계정을 연결할게요」(첫 연결·재연결 공통)."""
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(40, 8, 40, 28)
        lay.setSpacing(22)

        head = QLabel("GitHub 계정을 연결할게요")
        head.setObjectName("flowHeroTitle")
        head.setWordWrap(True)
        if self._reauth:
            lead = QLabel(
                "새 키로 다시 연결합니다. 한 번만 해두면 다음부터는 바로 올리고 받을 수 있어요."
            )
        else:
            lead = QLabel("한 번만 해두면 다음부터는 바로 올리고 받을 수 있어요.")
        lead.setObjectName("flowHeroLead")
        lead.setWordWrap(True)
        lay.addWidget(head)
        lay.addWidget(lead)

        intro_bits = (
            "GitHub에 로그인합니다. 비밀번호는 클론업을 거치지 않습니다.",
            "클론업이 쓸 키를 하나 만듭니다. 저장소를 읽고 쓰는 권한만 담습니다.",
            "키는 이 컴퓨터에만 저장됩니다. 어디로도 보내지 않습니다.",
        )
        for i, text in enumerate(intro_bits, start=1):
            row = QFrame()
            row.setObjectName("flowIntroRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(16, 15, 16, 15)
            rl.setSpacing(13)
            num = QLabel(str(i))
            num.setObjectName("flowIntroNum")
            num.setFixedSize(22, 22)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pal = active_palette()
            num.setStyleSheet(
                f"QLabel#flowIntroNum {{"
                f"background:{pal.bg_window};color:{pal.primary};"
                f"border:none;border-radius:11px;font-size:12px;font-weight:600;}}"
            )
            lab = QLabel(text)
            lab.setObjectName("flowIntroText")
            lab.setWordWrap(True)
            rl.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)
            rl.addWidget(lab, 1)
            lay.addWidget(row)

        cta = QPushButton("시작하기")
        cta.setObjectName("flowCta")
        cta.setDefault(True)
        cta.setCursor(Qt.CursorShape.PointingHandCursor)
        cta.clicked.connect(lambda: self._go(self._choice_index))
        lay.addWidget(cta)

        skip = QPushButton("취소")
        skip.setObjectName("btnGhost")
        skip.clicked.connect(self.reject)
        lay.addWidget(skip, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(0)

        return self._flow_narrow_shell(
            progress_pct=self._flow_progress_pct(intro=True),
            back_enabled=False,
            on_back=None,
            body=body,
        )

    def _page_choice(self) -> QWidget:
        """시안 step1 — 앱 안 / 브라우저 방식 선택 (재연결 포함)."""
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(40, 8, 40, 28)
        lay.setSpacing(22)

        # 시안 step1 카피 (재연결이어도 동일 — 인트로에서 이미 맥락을 줌)
        head = QLabel("어떤 방법이 편하세요?")
        lead = QLabel("둘 다 결과는 같아요. 언제든 바꿀 수 있습니다.")
        head.setObjectName("flowHeroTitle")
        head.setWordWrap(True)
        lead.setObjectName("flowHeroLead")
        lead.setWordWrap(True)
        lay.addWidget(head)
        lay.addWidget(lead)

        self._opt_web = _FlowOptionCard(
            icon_kind="app",
            title="앱 안에서",
            body="창 하나로 끝나요. 로그인하면 키까지 만들어 드립니다.",
            tag="간편",
            primary_icon=True,
        )
        self._opt_web.setToolTip(
            "CloneUp 창 안에서 GitHub 로그인·키 만들기를 진행합니다."
        )
        self._opt_web.clicked.connect(self._pick_webview_option)

        self._opt_browser = _FlowOptionCard(
            icon_kind="browser",
            title="브라우저에서",
            body="Google·패스키로 로그인하신다면 이쪽이어야 합니다.",
            tag="",
            primary_icon=False,
        )
        self._opt_browser.setToolTip(
            "OS 브라우저 + 작은 안내 창만 사용합니다. 이 연결 마법사는 닫힙니다."
        )
        self._opt_browser.clicked.connect(self._pick_browser_option)

        lay.addWidget(self._opt_web)
        lay.addWidget(self._opt_browser)

        # 시안: 선택 전 「다음」은 흐림(비활성). 카드 클릭이 곧 확정이라 CTA는 안내만.
        hint = QLabel("위에서 방법을 고르면 바로 이어집니다.")
        hint.setObjectName("flowHeroLead")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)

        cancel = QPushButton("취소")
        cancel.setObjectName("btnGhost")
        cancel.clicked.connect(self.reject)
        lay.addWidget(cancel, 0, Qt.AlignmentFlag.AlignHCenter)

        return self._flow_narrow_shell(
            progress_pct=self._flow_progress_pct(intro=False),
            back_enabled=True,
            on_back=lambda: self._go(self._intro_index),
            body=body,
        )

    def _pick_webview_option(self) -> None:
        if getattr(self, "_opt_web", None) is not None:
            self._opt_web.set_selected(True)
        if getattr(self, "_opt_browser", None) is not None:
            self._opt_browser.set_selected(False)
        self._start_webview_path()

    def _pick_browser_option(self) -> None:
        if getattr(self, "_opt_browser", None) is not None:
            self._opt_browser.set_selected(True)
        if getattr(self, "_opt_web", None) is not None:
            self._opt_web.set_selected(False)
        self._start_external_path()

    def _start_webview_path(self) -> None:
        """Path A — this wizard only; never create ExternalBrowserPatGuide."""
        self._want_external = False
        if self._via_fine:
            self._open_fine_and_paste()
        else:
            self._open_create_page()
        # WebView needs the large maximized chrome; choice used a compact window
        QTimer.singleShot(0, self._fit_web_dialog)

    def _start_external_path(self) -> None:
        """Path B — close this wizard; main_window runs Guide alone."""
        self._want_external = True
        self._want_device = False
        self._token = ""
        self._stop_clipboard_watch()
        # Fully close so only one connect UI is visible
        self.done(int(QDialog.DialogCode.Accepted))

    def _page_web(self) -> QWidget:
        """시안 본문: 카운터·제목·트랙·브라우저·안내·푸터.

        창 제목/아이콘만 OS 타이틀바에 두고, 바깥 회색·카드 헤더 로고·
        하단 「앱이 감지하는 것」 박스는 넣지 않습니다.
        """
        from app.ui.connect_webview import GitHubConnectWebPane, step_copy

        outer = QWidget()
        outer.setObjectName("connOuter")
        outer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # --- top caption row (시안: 단계 힌트) ---
        top_row = QWidget()
        top_lay = QHBoxLayout(top_row)
        top_lay.setContentsMargins(22, 12, 22, 0)
        top_lay.setSpacing(12)
        top_lab = QLabel("단계")
        top_lab.setObjectName("wizMeta")
        top_hint = QLabel("웹 화면은 앱이 감지해 단계를 스스로 넘깁니다")
        top_hint.setObjectName("wizMeta")
        top_lay.addWidget(top_lab)
        top_lay.addStretch(1)
        top_lay.addWidget(top_hint)

        # --- main body (no logo header; fills window cream bg) ---
        card = QFrame()
        card.setObjectName("connCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # title block — padding 18 22 14
        title_block = QWidget()
        tb = QVBoxLayout(title_block)
        tb.setContentsMargins(22, 14, 22, 14)
        tb.setSpacing(8)
        prog_row = QHBoxLayout()
        prog_row.setSpacing(9)
        self._web_counter = QLabel("1 / 4")
        self._web_counter.setObjectName("wizProgress")
        self._web_step_name = QLabel("로그인")
        self._web_step_name.setObjectName("wizMeta")
        prog_row.addWidget(self._web_counter)
        prog_row.addWidget(self._web_step_name)
        prog_row.addStretch(1)
        self._web_stage_title = QLabel(str(step_copy(0)["title"]))
        self._web_stage_title.setObjectName("wizTitle")
        self._web_stage_title.setWordWrap(True)
        self._web_hint = QLabel(str(step_copy(0)["lead"]))
        self._web_hint.setObjectName("wizLead")
        self._web_hint.setWordWrap(True)
        self._web_hint.setMaximumWidth(780)
        tb.addLayout(prog_row)
        tb.addWidget(self._web_stage_title)
        tb.addWidget(self._web_hint)

        # track — margin 0 22 14
        track_wrap = QWidget()
        tw = QVBoxLayout(track_wrap)
        tw.setContentsMargins(22, 0, 22, 14)
        tw.setSpacing(0)
        self._track_host = QFrame()
        self._track_host.setObjectName("connTrack")
        self._track_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._track_host.setFixedHeight(46)
        self._track_lay = QHBoxLayout(self._track_host)
        self._track_lay.setContentsMargins(14, 8, 14, 8)
        self._track_lay.setSpacing(4)
        self._rebuild_track(0)
        tw.addWidget(self._track_host)

        # browser chrome — margin 0 22
        browser_wrap = QWidget()
        bw = QVBoxLayout(browser_wrap)
        bw.setContentsMargins(22, 0, 22, 0)
        bw.setSpacing(0)
        browser = QFrame()
        browser.setObjectName("connBrowser")
        browser.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        br_lay = QVBoxLayout(browser)
        br_lay.setContentsMargins(0, 0, 0, 0)
        br_lay.setSpacing(0)

        addr = QFrame()
        addr.setObjectName("connAddrBar")
        addr.setFixedHeight(40)
        addr_lay = QHBoxLayout(addr)
        addr_lay.setContentsMargins(12, 0, 12, 0)
        addr_lay.setSpacing(10)
        self._web_back_btn = QPushButton("←")
        self._web_back_btn.setObjectName("connNavMini")
        self._web_back_btn.setToolTip("이전 페이지")
        self._web_back_btn.setEnabled(False)
        self._web_back_btn.clicked.connect(self._on_web_back)
        self._web_fwd_btn = QPushButton("→")
        self._web_fwd_btn.setObjectName("connNavMini")
        self._web_fwd_btn.setToolTip("다음 페이지")
        self._web_fwd_btn.setEnabled(False)
        self._web_fwd_btn.clicked.connect(self._on_web_forward)
        # URL field group: editable address (Enter to go)
        url_box = QFrame()
        url_box.setObjectName("connUrlBox")
        url_box_lay = QHBoxLayout(url_box)
        url_box_lay.setContentsMargins(10, 0, 10, 0)
        url_box_lay.setSpacing(8)
        lock = QLabel("🔒")
        lock.setObjectName("connLock")
        self._web_url = QLineEdit()
        self._web_url.setReadOnly(False)
        self._web_url.setObjectName("connUrlInner")
        self._web_url.setText("https://github.com/")
        self._web_url.setCursorPosition(0)
        self._web_url.setFrame(False)
        self._web_url.setPlaceholderText("주소를 입력한 뒤 Enter")
        self._web_url.setToolTip("주소를 수정한 뒤 Enter로 이동합니다")
        self._web_url.returnPressed.connect(self._on_web_url_commit)
        self._web_url.editingFinished.connect(self._on_web_url_edit_finished)
        # While typing, don't let live navigation overwrite the field
        self._web_url.textEdited.connect(lambda _t: self._mark_web_url_editing(True))
        url_box_lay.addWidget(lock)
        url_box_lay.addWidget(self._web_url, 1)
        only = QLabel("github.com 에서만 열립니다")
        only.setObjectName("connUrlOnly")
        addr_lay.addWidget(self._web_back_btn)
        addr_lay.addWidget(self._web_fwd_btn)
        addr_lay.addWidget(url_box, 1)
        addr_lay.addWidget(only)

        self._web_pane = GitHubConnectWebPane(browser)
        self._web_pane.stage_changed.connect(self._on_web_stage)
        self._web_pane.url_changed.connect(self._on_web_url)
        self._web_pane.history_changed.connect(self._on_web_history)
        self._web_pane.token_found.connect(self._apply_detected_token)
        self._web_pane.load_failed.connect(self._on_web_load_failed)
        self._web_pane.external_oauth_needed.connect(self._on_google_oauth_external)
        self._web_pane.token_form_error.connect(self._on_web_token_form_error)
        self._web_pane.flow_classified.connect(self._on_webview_flow_classified)
        self._web_pane.token_reissue.connect(self._on_web_token_reissue)
        self._web_pane.pat_create_note.connect(self._on_pat_create_note)

        # Browser body: session choice | loading spinner | WebView
        self._session_choice = self._build_session_choice_panel()
        self._loading_panel = self._build_loading_panel()
        self._browser_stack = QStackedWidget(browser)
        self._browser_stack.setObjectName("connBrowserStack")
        self._browser_stack.addWidget(self._session_choice)  # _STACK_SESSION
        self._browser_stack.addWidget(self._loading_panel)  # _STACK_LOADING
        self._browser_stack.addWidget(self._web_pane)  # _STACK_WEB
        self._browser_stack.setCurrentIndex(_STACK_WEB)
        try:
            self._web_pane._view.loadStarted.connect(self._on_web_load_started)
            self._web_pane._view.loadFinished.connect(self._on_web_load_finished_ui)
        except Exception:
            pass

        br_lay.addWidget(addr)
        br_lay.addWidget(self._browser_stack, 1)
        bw.addWidget(browser, 1)

        # watch banner — margin 14 22 0
        watch_wrap = QWidget()
        ww = QVBoxLayout(watch_wrap)
        ww.setContentsMargins(22, 14, 22, 0)
        ww.setSpacing(0)
        self._web_watch = QFrame()
        self._web_watch.setObjectName("connWatch")
        watch_lay = QHBoxLayout(self._web_watch)
        watch_lay.setContentsMargins(14, 11, 14, 11)
        watch_lay.setSpacing(11)
        self._web_watch_tag = QLabel("기다리는 중")
        self._web_watch_tag.setObjectName("connWatchTag")
        self._web_watch_body = QLabel("")
        self._web_watch_body.setObjectName("wizLead")
        self._web_watch_body.setWordWrap(True)
        watch_lay.addWidget(self._web_watch_tag, 0, Qt.AlignmentFlag.AlignTop)
        watch_lay.addWidget(self._web_watch_body, 1)
        ww.addWidget(self._web_watch)

        # key row — margin 14 22 0, step 4 only
        key_wrap = QWidget()
        kw = QVBoxLayout(key_wrap)
        kw.setContentsMargins(22, 14, 22, 0)
        kw.setSpacing(8)
        self._key_row = QWidget()
        key_lay = QHBoxLayout(self._key_row)
        key_lay.setContentsMargins(0, 0, 0, 0)
        key_lay.setSpacing(10)
        self._edit = QLineEdit()
        self._edit.setObjectName("patEdit")
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("키가 여기 채워지거나, 직접 붙여 넣으세요")
        self._edit.setClearButtonEnabled(True)
        self._edit.setMinimumHeight(40)
        self._edit.textChanged.connect(lambda _t: self._sync_web_cta())
        btn_paste = QPushButton("붙여넣기")
        btn_paste.setObjectName("btnSecondary")
        btn_paste.clicked.connect(self._paste_clipboard)
        self._btn_toggle = QPushButton("보기")
        self._btn_toggle.setObjectName("btnSecondary")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.toggled.connect(self._on_toggle_visible)
        key_lay.addWidget(self._edit, 1)
        key_lay.addWidget(btn_paste)
        key_lay.addWidget(self._btn_toggle)
        self._key_note = QLabel("")
        self._key_note.setObjectName("wizMeta")
        self._key_note.setWordWrap(True)
        kw.addWidget(self._key_row)
        kw.addWidget(self._key_note)
        key_wrap.hide()  # shown only on step 4 via _paint_web_guide
        self._key_wrap = key_wrap

        # footer — 3-column grid so 만료일 sits on the true horizontal center
        # (left cancel vs right primary were unequal → HBox stretch looked left-biased)
        footer = QFrame()
        footer.setObjectName("connFooter")
        footer.setFixedHeight(72)
        foot = QGridLayout(footer)
        foot.setContentsMargins(22, 0, 22, 0)
        foot.setHorizontalSpacing(12)
        foot.setVerticalSpacing(0)
        btn_cancel = QPushButton("취소")
        btn_cancel.setObjectName("btnGhost")
        btn_cancel.clicked.connect(self.reject)
        # Path switch (closes WebView wizard; main opens Guide alone)
        self._btn_switch_external = QPushButton("브라우저에서 로그인으로 바꾸기")
        self._btn_switch_external.setObjectName("btnSecondary")
        self._btn_switch_external.setToolTip(
            "이 창을 닫고 브라우저 안내만 사용합니다. 창은 하나만 남습니다."
        )
        self._btn_switch_external.clicked.connect(self._start_external_path)
        self._btn_switch_external.hide()

        # Center: PAT Expiration (mirrors GitHub classic options)
        self._expiry_lab = QLabel("만료일")
        self._expiry_lab.setObjectName("wizMeta")
        self._expiry_combo = QComboBox()
        self._expiry_combo.setObjectName("connExpiryCombo")
        self._expiry_combo.setMinimumWidth(140)
        self._expiry_combo.setToolTip(
            "GitHub 키 만료 기간입니다. 폼의 Expiration과 맞추고 연결 시 함께 저장합니다."
        )
        for label, value in (
            ("7일", "7"),
            ("30일", "30"),
            ("60일", "60"),
            ("90일 (권장)", "90"),
            ("만료 없음", ""),
        ):
            self._expiry_combo.addItem(label, value)
        # Default: 90 days (beginner-friendly)
        self._expiry_combo.setCurrentIndex(3)
        self._expiry_combo.currentIndexChanged.connect(self._on_expiry_choice_changed)

        self._web_cta_note = QLabel("로그인하면 자동으로 진행됩니다")
        self._web_cta_note.setObjectName("wizMeta")
        # 「다음」CTA removed — same primary slot/style, label is back-to-choice
        self._web_back_footer = QPushButton("이전화면으로 가기")
        self._web_back_footer.setObjectName("btnPrimary")
        self._web_back_footer.setToolTip("연결 방법 선택으로 돌아갑니다")
        self._web_back_footer.clicked.connect(lambda: self._go(self._choice_index))

        left_row = QHBoxLayout()
        left_row.setContentsMargins(0, 0, 0, 0)
        left_row.setSpacing(12)
        left_row.addWidget(btn_cancel)
        left_row.addWidget(self._btn_switch_external)
        left_row.addStretch(1)

        center_row = QHBoxLayout()
        center_row.setContentsMargins(0, 0, 0, 0)
        center_row.setSpacing(12)
        center_row.addWidget(self._expiry_lab)
        center_row.addWidget(self._expiry_combo)

        right_row = QHBoxLayout()
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(12)
        right_row.addStretch(1)
        right_row.addWidget(self._web_cta_note)
        right_row.addWidget(self._web_back_footer)

        foot.addLayout(left_row, 0, 0, Qt.AlignmentFlag.AlignVCenter)
        foot.addLayout(
            center_row, 0, 1, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        foot.addLayout(right_row, 0, 2, Qt.AlignmentFlag.AlignVCenter)
        foot.setColumnStretch(0, 1)
        foot.setColumnStretch(1, 0)
        foot.setColumnStretch(2, 1)

        card_lay.addWidget(title_block, 0)
        card_lay.addWidget(track_wrap, 0)
        card_lay.addWidget(browser_wrap, 1)
        card_lay.addWidget(watch_wrap, 0)
        card_lay.addWidget(key_wrap, 0)
        card_lay.addSpacing(16)
        card_lay.addWidget(footer)

        out = QVBoxLayout(outer)
        out.setContentsMargins(0, 0, 0, 0)
        out.setSpacing(0)
        out.addWidget(top_row, 0)
        out.addWidget(card, 1)

        self._paint_web_guide(0)
        return outer

    @staticmethod
    def _track_mark(done: bool, cur: bool) -> QWidget:
        """시안: 15×15 circle (border-radius: 50%). Palette-aware for dark mode."""

        class _CircleMark(QWidget):
            def __init__(self, *, done: bool, cur: bool) -> None:
                super().__init__()
                self._done = done
                self._cur = cur
                self.setFixedSize(15, 15)
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

            def paintEvent(self, event) -> None:  # noqa: N802
                from PySide6.QtGui import QColor, QPainter, QPen

                pal = active_palette()
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                # Inset 0.5 so the 1px stroke sits fully inside the 15×15 box
                rect = self.rect().adjusted(1, 1, -1, -1)
                if self._done:
                    painter.setBrush(QColor(pal.primary))
                    painter.setPen(QPen(QColor(pal.primary), 1))
                    painter.drawEllipse(rect)
                    painter.setPen(QColor(pal.bg_window))
                    font = painter.font()
                    font.setPixelSize(9)
                    font.setBold(True)
                    painter.setFont(font)
                    painter.drawText(
                        self.rect(), int(Qt.AlignmentFlag.AlignCenter), "✓"
                    )
                elif self._cur:
                    painter.setBrush(QColor(pal.bg_window))
                    painter.setPen(QPen(QColor(pal.primary), 1))
                    painter.drawEllipse(rect)
                else:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(QColor(pal.border_input), 1))
                    painter.drawEllipse(rect)
                painter.end()

        return _CircleMark(done=done, cur=cur)

    def _rebuild_track(self, now: int) -> None:
        from app.ui.connect_webview import UI_STEP_NAMES

        if self._track_lay is None:
            return
        while self._track_lay.count():
            item = self._track_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._track_lay.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._track_lay.setSpacing(4)
        for n, label in enumerate(UI_STEP_NAMES):
            done = n < now
            cur = n == now
            cell = QFrame()
            cell.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
            )
            cell.setFixedHeight(28)
            hl = QHBoxLayout(cell)
            # 시안: current pad 5px 11px, else 5px 7px
            hl.setContentsMargins(11 if cur else 7, 0, 11 if cur else 7, 0)
            hl.setSpacing(7)
            mark = self._track_mark(done, cur)
            lab = QLabel(label)
            lab.setWordWrap(False)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            lab.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
            )
            # Keep Korean step names on one line (no "인증" / "코드" wrap)
            fm = lab.fontMetrics()
            lab.setMinimumWidth(fm.horizontalAdvance(label) + 4)
            pal = active_palette()
            if cur:
                lab.setStyleSheet(
                    f"color:{pal.primary};font-weight:600;font-size:12.5px;"
                    "background:transparent;border:none;"
                )
                cell.setStyleSheet(
                    f"QFrame {{ background:{pal.bg_window}; "
                    f"border-radius:5px; border:none; }}"
                )
            elif done:
                lab.setStyleSheet(
                    f"color:{pal.text_secondary};font-size:12.5px;"
                    "background:transparent;border:none;"
                )
                cell.setStyleSheet("QFrame { background:transparent; border:none; }")
            else:
                lab.setStyleSheet(
                    f"color:{pal.text_faint};font-size:12.5px;"
                    "background:transparent;border:none;"
                )
                cell.setStyleSheet("QFrame { background:transparent; border:none; }")
            hl.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
            hl.addWidget(lab, 0, Qt.AlignmentFlag.AlignVCenter)
            self._track_lay.addWidget(
                cell, 0, Qt.AlignmentFlag.AlignVCenter
            )
            if n < len(UI_STEP_NAMES) - 1:
                ar = QLabel("→")
                ar.setStyleSheet(
                    f"color:{pal.text_disabled};font-size:11px;"
                    "background:transparent;border:none;"
                )
                ar.setFixedWidth(18)
                ar.setFixedHeight(28)
                ar.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._track_lay.addWidget(
                    ar, 0, Qt.AlignmentFlag.AlignVCenter
                )
        self._track_lay.addStretch(1)

    def _paint_web_guide(self, now: int, live_stage: object | None = None) -> None:
        from app.auth.github_page_stage import GitHubPageStage
        from app.ui.connect_webview import guide_overlay_for_stage, step_copy

        now = max(0, min(now, 3))
        self._ui_now = now
        if live_stage is not None:
            self._web_live_stage = live_stage
        copy = step_copy(now)

        # Title/lead — /settings/tokens list overrides with Generate new token copy
        title = str(copy["title"])
        lead = str(copy["lead"])
        step_name = str(copy["stepName"])
        st = self._web_live_stage
        if isinstance(st, GitHubPageStage):
            overlay = guide_overlay_for_stage(st)
            # UNKNOWN overlay only after user has reached key-making territory
            if (
                overlay is not None
                and st == GitHubPageStage.UNKNOWN
                and self._ui_max < 2
            ):
                overlay = None
            if overlay is not None:
                title = str(overlay["title"])
                lead = str(overlay["lead"])
                if overlay.get("stepName"):
                    step_name = str(overlay["stepName"])

        if self._web_counter is not None:
            self._web_counter.setText(f"{now + 1} / 4")
        if self._web_step_name is not None:
            self._web_step_name.setText(step_name)
        self._progress.setText(f"{now + 1} / 4  ·  {step_name}")
        if self._web_stage_title is not None:
            self._web_stage_title.setText(title)
        if self._web_hint is not None:
            self._web_hint.setText(lead)

        # Watch banner: tag + body as separate widgets (시안) — unchanged on list
        warn = bool(copy.get("watchWarn", False)) or str(copy["watchTag"]) == "주의"
        if self._web_watch is not None:
            self._web_watch.setObjectName("connWatchWarn" if warn else "connWatch")
            self._web_watch.style().unpolish(self._web_watch)
            self._web_watch.style().polish(self._web_watch)
            self._web_watch.update()
        if self._web_watch_tag is not None:
            self._web_watch_tag.setText(str(copy["watchTag"]))
            self._web_watch_tag.setObjectName(
                "connWatchTagWarn" if warn else "connWatchTag"
            )
            self._web_watch_tag.style().unpolish(self._web_watch_tag)
            self._web_watch_tag.style().polish(self._web_watch_tag)
        if self._web_watch_body is not None:
            self._web_watch_body.setText(str(copy["watchBody"]))

        self._rebuild_track(now)
        show_key = bool(copy["showKey"])
        key_wrap = getattr(self, "_key_wrap", None)
        if key_wrap is not None:
            key_wrap.setVisible(show_key)
        elif self._key_row is not None:
            self._key_row.setVisible(show_key)
        if self._key_note is not None:
            self._key_note.setVisible(show_key)
            if show_key:
                self._key_note.setText(
                    "복사 버튼을 누르면 이 칸이 채워집니다. "
                    "화면에는 앞자리만 보입니다."
                )
        self._sync_web_cta()

    def _sync_web_cta(self) -> None:
        """Footer status note + auto-finish when a PAT is ready (no 「다음」CTA)."""
        if self._web_cta_note is None:
            return
        from app.ui.connect_webview import step_copy

        copy = step_copy(self._ui_now)
        if self._ui_now < 3:
            self._web_cta_note.setText(str(copy["ctaNote"]))
            return
        has = bool((self._edit.text() or "").strip()) if hasattr(self, "_edit") else False
        tok_ok = _looks_like_github_token(
            (self._edit.text() or "").strip() if hasattr(self, "_edit") else ""
        )
        if tok_ok:
            self._web_cta_note.setText("키를 인식했어요. 자동으로 연결합니다…")
            self._schedule_auto_finish()
        else:
            self._web_cta_note.setText(
                "" if has else "키가 보이거나 복사되면 자동으로 연결됩니다"
            )

    def _on_web_cta(self) -> None:
        # Legacy hook — footer 「다음/연결」removed; keep for any stray callers
        if self._ui_now >= 3:
            self._finish()

    def _expiry_combo_value(self) -> str:
        if self._expiry_combo is None:
            return "90"
        data = self._expiry_combo.currentData()
        return "" if data is None else str(data)

    def _on_expiry_choice_changed(self, _index: int = 0) -> None:
        """Sync footer expiry → WebView Expiration select + pending store value."""
        from app.auth.token_expiry import parse_expires_label

        val = self._expiry_combo_value()
        exp = parse_expires_label(
            val or "none", "No expiration" if not val else f"{val} days"
        )
        if exp:
            self._token_expires_at = exp
        if self._web_pane is not None:
            # Remember for the chained Generate flow (must set DOM before click)
            self._web_pane._pending_expiry_days = val
            if self._session_awaiting_choice:
                return
            # Fast path: hidden input write; do not stall auto-Generate
            self._web_pane.apply_expiration_choice(val, fast=True)

    def _sync_expiry_to_webview(self) -> None:
        """Push current combo selection into the page (after tokens/new loads)."""
        if self._expiry_combo is None or self._web_pane is None:
            return
        # Set pending days first so auto Generate waits on the same value
        self._web_pane._pending_expiry_days = self._expiry_combo_value()
        self._on_expiry_choice_changed(self._expiry_combo.currentIndex())

    def _mark_web_url_editing(self, editing: bool) -> None:
        self._web_url_editing = editing

    def _on_web_url_edit_finished(self) -> None:
        # Focus left the field without Enter — resume syncing from the page
        self._web_url_editing = False
        self._sync_address_bar_from_view(force=False)

    def _sync_address_bar_from_view(self, *, force: bool = False) -> None:
        """Copy the WebView URL into the address field.

        ``force=True`` after ←/→ so the bar always matches the page even if
        the field still has focus. While the user is actively typing
        (``_web_url_editing``), skip unless forced.
        """
        if self._web_url is None or self._web_pane is None:
            return
        if not force and self._web_url_editing:
            return
        try:
            url = self._web_pane._view.url().toString()
        except Exception:
            url = ""
        text = url or "https://github.com/"
        # Avoid cursor jumps when nothing changed
        if self._web_url.text() == text:
            return
        self._web_url.blockSignals(True)
        try:
            self._web_url.setText(text)
            if not self._web_url.hasFocus():
                self._web_url.setCursorPosition(0)
        finally:
            self._web_url.blockSignals(False)

    def _on_web_url(self, url: str) -> None:
        if self._web_url is None:
            return
        # Remember Note from create-form URLs (incl. reissue / away-return)
        n = note_from_pat_create_url(url or "")
        if n:
            self._pat_note = n
        # Only skip while the user is typing — focus alone must not block sync
        # (← left the bar focused and the URL never updated).
        if self._web_url_editing:
            return
        text = url or "https://github.com/"
        if self._web_url.text() == text:
            return
        self._web_url.blockSignals(True)
        try:
            self._web_url.setText(text)
            if not self._web_url.hasFocus():
                self._web_url.setCursorPosition(0)
        finally:
            self._web_url.blockSignals(False)

    def _on_web_history(self, can_back: bool, can_fwd: bool) -> None:
        if self._web_back_btn is not None:
            self._web_back_btn.setEnabled(bool(can_back))
        if self._web_fwd_btn is not None:
            self._web_fwd_btn.setEnabled(bool(can_fwd))
        # History updates on every nav including ←/→ — keep the bar in sync
        self._sync_address_bar_from_view(force=False)

    def _on_web_back(self) -> None:
        if self._web_pane is None:
            return
        if self._session_awaiting_choice:
            return
        self._web_url_editing = False
        if self._web_url is not None:
            self._web_url.clearFocus()
        self._web_pane.go_back()
        # urlChanged is async — force sync on the next tick too
        QTimer.singleShot(0, lambda: self._sync_address_bar_from_view(force=True))
        QTimer.singleShot(100, lambda: self._sync_address_bar_from_view(force=True))

    def _on_web_forward(self) -> None:
        if self._web_pane is None:
            return
        if self._session_awaiting_choice:
            return
        self._web_url_editing = False
        if self._web_url is not None:
            self._web_url.clearFocus()
        self._web_pane.go_forward()
        QTimer.singleShot(0, lambda: self._sync_address_bar_from_view(force=True))
        QTimer.singleShot(100, lambda: self._sync_address_bar_from_view(force=True))

    def _on_web_url_commit(self) -> None:
        """Enter in the address bar → navigate."""
        if self._web_pane is None or self._web_url is None:
            return
        if self._session_awaiting_choice:
            return
        text = self._web_url.text()
        self._web_url_editing = False
        ok = self._web_pane.navigate_to(text)
        if not ok and self._web_hint is not None:
            self._web_hint.setText(
                "주소를 확인하세요. https:// 로 시작하는 웹 주소만 열 수 있습니다."
            )
            self._sync_address_bar_from_view(force=True)

    def _on_web_stage(self, stage: object) -> None:
        from app.auth.github_page_stage import GitHubPageStage
        from app.ui.connect_webview import ui_index_for_stage

        st = stage if isinstance(stage, GitHubPageStage) else GitHubPageStage.UNKNOWN
        ui = ui_index_for_stage(st)
        if ui is not None:
            # Advance sticky max; current follows live page
            self._ui_max = max(self._ui_max, ui)
            self._paint_web_guide(ui, live_stage=st)
            # Create form: only push pending days — WebView's fast
            # expiry→Generate chain applies DOM (avoid a second heavy apply).
            if st in (
                GitHubPageStage.TOKEN_CLASSIC_NEW,
                GitHubPageStage.TOKEN_FINE_NEW,
            ):
                if self._web_pane is not None and self._expiry_combo is not None:
                    self._web_pane._pending_expiry_days = self._expiry_combo_value()
            return
        # Off-map page (e.g. profile) — keep track, refresh title/lead if useful
        if self._ui_max >= 1 or self._ui_now >= 1:
            self._paint_web_guide(self._ui_now, live_stage=st)

    def _on_web_load_failed(self, _msg: str) -> None:
        if self._web_hint is not None:
            self._web_hint.setText(
                "페이지를 불러오지 못했습니다. "
                "「브라우저에서 로그인으로 바꾸기」를 눌러 주세요."
            )

    def _on_web_token_form_error(self, code: str) -> None:
        """WebView PAT form flash — e.g. Note has already been taken."""
        from app.ui.connect_webview import guide_lead

        if code != "note_taken":
            return
        if self._web_hint is not None:
            self._web_hint.setText(
                guide_lead(
                    "Note 이름이 이미 있어요. 새 이름(날짜·시간)으로 다시 엽니다."
                )
            )
        if self._web_stage_title is not None:
            self._web_stage_title.setText("Note 이름이 중복되었습니다")
        if self._btn_switch_external is not None:
            self._btn_switch_external.show()
        # Auto-recover with CloneUp-YYYYMMDD-HHMMSS
        QTimer.singleShot(400, self._reload_pat_create_fresh_note)

    def _on_web_token_reissue(self, attempt: int, maximum: int) -> None:
        """List page had no PAT — loop reopened tokens/new (or exhausted)."""
        from app.ui.connect_webview import guide_lead

        exhausted = bool(
            self._web_pane is not None
            and getattr(self._web_pane, "_reissue_exhausted", False)
        )
        if exhausted:
            if self._web_stage_title is not None:
                self._web_stage_title.setText("키를 자동으로 못 찾았어요")
            if self._web_hint is not None:
                self._web_hint.setText(
                    guide_lead(
                        "Generate token 후 키를 복사해 칸에 넣어 주세요."
                    )
                )
            return
        if self._web_stage_title is not None:
            self._web_stage_title.setText("키를 다시 발급합니다")
        if self._web_hint is not None:
            self._web_hint.setText(
                guide_lead(f"키가 없어 다시 발급합니다 ({attempt}/{maximum}).")
            )

    def _live_stage_from_webview(self) -> object | None:
        """Best-effort GitHubPageStage from the current WebView URL."""
        if self._web_pane is None:
            return None
        try:
            from app.auth.github_page_stage import PageSnapshot, detect_github_page_stage

            url = self._web_pane._view.url().toString()
            title = self._web_pane._view.title() or ""
            return detect_github_page_stage(PageSnapshot(url=url, title=title))
        except Exception:
            return None

    def _current_webview_url(self) -> str:
        if self._web_pane is None:
            return ""
        try:
            return self._web_pane._view.url().toString()
        except Exception:
            return ""

    def _ensure_away_banner(self) -> None:
        """Lazy-build dialog-level overlay (top-right of the whole window)."""
        if self._away_banner is not None:
            return
        banner = QFrame(self)
        banner.setObjectName("connAwayBanner")
        banner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(banner)
        row.setContentsMargins(12, 8, 10, 8)
        row.setSpacing(10)
        lab = QLabel("")
        lab.setObjectName("connAwayBannerText")
        lab.setWordWrap(False)
        btn = QPushButton("취소")
        btn.setObjectName("connAwayCancel")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._on_away_cancel_clicked)
        row.addWidget(lab, 1)
        row.addWidget(btn, 0)
        banner.hide()
        self._away_banner = banner
        self._away_banner_lab = lab

    def _place_away_banner(self) -> None:
        banner = self._away_banner
        if banner is None or not banner.isVisible():
            return
        banner.adjustSize()
        margin_top = 12
        margin_right = 16
        x = max(8, self.width() - banner.width() - margin_right)
        y = margin_top
        banner.move(x, y)
        banner.raise_()

    def _start_away_return_countdown(self) -> None:
        """Off-family site: show 5s banner; do not restart if already counting."""
        from app.ui.webview_flow_detect import (
            away_return_countdown_seconds,
            format_away_return_banner,
        )

        if self._session_awaiting_choice:
            return
        if self._away_countdown_active:
            return
        self._ensure_away_banner()
        self._away_secs_left = away_return_countdown_seconds()
        self._away_countdown_active = True
        if self._away_banner_lab is not None:
            self._away_banner_lab.setText(
                format_away_return_banner(self._away_secs_left)
            )
        if self._away_banner is not None:
            self._away_banner.show()
            self._place_away_banner()
        if self._away_timer is None:
            self._away_timer = QTimer(self)
            self._away_timer.setInterval(1000)
            self._away_timer.timeout.connect(self._tick_away_return)
        self._away_timer.start()

    def _tick_away_return(self) -> None:
        from app.ui.webview_flow_detect import (
            away_return_target_url,
            format_away_return_banner,
        )

        if not self._away_countdown_active:
            return
        self._away_secs_left -= 1
        if self._away_secs_left > 0:
            if self._away_banner_lab is not None:
                self._away_banner_lab.setText(
                    format_away_return_banner(self._away_secs_left)
                )
            self._place_away_banner()
            return
        # Time's up — return to classic token create page
        self._dismiss_away_return_banner()
        if self._web_pane is not None:
            try:
                target = away_return_target_url()
                self._remember_pat_note(target)
                self._web_pane.load_url(target)
            except Exception:
                pass

    def _on_away_cancel_clicked(self) -> None:
        """Stop timer only; stay on the off-family page."""
        self._dismiss_away_return_banner()

    def _dismiss_away_return_banner(self) -> None:
        self._away_countdown_active = False
        self._away_secs_left = 0
        if self._away_timer is not None:
            self._away_timer.stop()
        if self._away_banner is not None:
            self._away_banner.hide()

    def _on_webview_flow_classified(
        self, kind: str, idx: object, meta: dict
    ) -> None:
        """
        Independent WebView twin of browser-guide classify handlers.

        Does not import ExternalBrowserPatGuide — uses webview_flow_detect only.
        Cross-check: every kind must update title/lead or trigger a side effect.
        """
        from app.ui.connect_webview import guide_lead
        from app.ui.webview_flow_detect import guide_copy_for_webview_kind

        method = str((meta or {}).get("method") or "")
        copy = guide_copy_for_webview_kind(kind, method=method)
        live = self._live_stage_from_webview()

        # Session confirm overlay is up — freeze all flow side-effects
        if self._session_awaiting_choice:
            return

        if kind == "rejected":
            self._dismiss_away_return_banner()
            # Google block → update copy, then switch (oauth may also fire)
            if copy and self._web_stage_title is not None:
                self._web_stage_title.setText(copy[0])
            if copy and self._web_hint is not None:
                self._web_hint.setText(guide_lead(copy[1]))
            QTimer.singleShot(0, self._start_external_path)
            return

        if kind == "logged_out":
            self._ui_max = 0
            self._paint_web_guide(0, live_stage=live)
            if copy:
                if self._web_stage_title is not None:
                    self._web_stage_title.setText(copy[0])
                if self._web_hint is not None:
                    self._web_hint.setText(guide_lead(copy[1]))
            # Profile/repos while Sign in·Sign up visible → rollback to token create
            cur = self._current_webview_url()
            from app.ui.webview_flow_detect import should_start_away_return_countdown

            if should_start_away_return_countdown(kind, cur):
                self._start_away_return_countdown()
            else:
                self._dismiss_away_return_banner()
            return

        if kind == "token_error":
            self._dismiss_away_return_banner()
            # note_taken also arrives via token_form_error (reload); reinforce copy
            if copy:
                if self._web_stage_title is not None:
                    self._web_stage_title.setText(copy[0])
                if self._web_hint is not None:
                    self._web_hint.setText(guide_lead(copy[1]))
            return

        if kind == "away":
            if copy:
                if self._web_stage_title is not None:
                    self._web_stage_title.setText(copy[0])
                if self._web_hint is not None:
                    self._web_hint.setText(guide_lead(copy[1]))
            self._start_away_return_countdown()
            return

        if kind == "current" and idx is not None:
            self._dismiss_away_return_banner()
            if method in ("github_login", "google", "apple", "passkey"):
                self._saw_github_login_page = True
            try:
                i = int(idx)
            except (TypeError, ValueError):
                i = 0
            # live_stage so LOGIN overlay/step copy matches URL
            self._paint_web_guide(i, live_stage=live)
            return

        if kind == "reached" and idx is not None:
            try:
                i = int(idx)
            except (TypeError, ValueError):
                return
            self._ui_max = max(self._ui_max, i)
            # Existing session already logged-in → pause WebView, confirm again
            if (
                not self._session_login_confirm_done
                and not self._saw_github_login_page
                and not self._session_awaiting_choice
            ):
                self._paint_web_guide(i, live_stage=live)
                self._pause_webview_for_post_login_confirm()
                return
            # Critical: pass live_stage so /settings/tokens gets list overlay
            # (Generate new token…), not generic "키를 만들어 주세요"
            self._paint_web_guide(i, live_stage=live)
            visible = str((meta or {}).get("visible_pat") or "")
            if visible:
                self._apply_detected_token(visible)
            # Logged-in but not on token pages → rollback to tokens/new
            cur = self._current_webview_url()
            from app.ui.webview_flow_detect import should_start_away_return_countdown

            if should_start_away_return_countdown(kind, cur):
                self._start_away_return_countdown()
            else:
                self._dismiss_away_return_banner()
            return

    def _on_google_oauth_external(self, url: str) -> None:
        """
        Google sign-in cannot run inside Qt WebEngine.

        Immediately switch to Path B (same as clicking
        「브라우저에서 로그인으로 바꾸기」) — do not nest a guide under this wizard.
        """
        _ = url
        self._dismiss_away_return_banner()
        if self._web_hint is not None:
            self._web_hint.setText(
                "Google 로그인은 브라우저에서 이어갑니다. 안내 창으로 바꿉니다…"
            )
        if self._btn_switch_external is not None:
            self._btn_switch_external.show()
        if self._web_cta_note is not None:
            self._web_cta_note.setText("브라우저 안내로 전환 중…")
        # Defer so the WebView navigation handler can finish cleanly
        QTimer.singleShot(0, self._start_external_path)

    def _open_external_from_web(self) -> None:
        """Legacy name — switching paths closes wizard; Guide runs alone."""
        self._start_external_path()

    def _page_paste(self, title: str, body: str) -> QWidget:
        w = QWidget()
        head = QLabel(title)
        head.setObjectName("wizTitle")

        lead = QLabel(body + "\n「붙여넣기」또는 Ctrl+V 를 사용할 수 있습니다.")
        lead.setObjectName("wizLead")
        lead.setWordWrap(True)

        self._edit = QLineEdit()
        self._edit.setObjectName("patEdit")
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("ghp_ 로 시작하는 키 전체")
        self._edit.setClearButtonEnabled(True)

        btn_paste = QPushButton("붙여넣기")
        btn_paste.setObjectName("btnSecondary")
        btn_paste.clicked.connect(self._paste_clipboard)

        self._btn_toggle = QPushButton("보기")
        self._btn_toggle.setObjectName("btnSecondary")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.toggled.connect(self._on_toggle_visible)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        tools.addWidget(btn_paste)
        tools.addWidget(self._btn_toggle)
        tools.addStretch(1)

        detail = _DetailToggle(
            "키가 짧거나 앞뒤가 잘리면 연결이 안 됩니다. "
            "Generate 직후 화면에서 전체를 다시 복사하세요.\n"
            "「보기」로 칸 내용이 ghp_ 로 시작하는지 확인할 수 있습니다.\n"
            "키는 비밀번호와 같습니다. 남에게 보내지 마세요.\n"
            "세분 키로 들어온 경우에도 이 칸에 붙여 넣으면 됩니다."
        )

        nav = QHBoxLayout()
        btn_cancel = QPushButton("취소")
        btn_cancel.setObjectName("btnGhost")
        btn_cancel.clicked.connect(self.reject)
        nav.addWidget(btn_cancel)

        btn_back = QPushButton("← 이전")
        btn_back.setObjectName("btnGhost")

        def _paste_back() -> None:
            self._go(_STEP_WORK if self._browser_opened else _STEP_START)

        btn_back.clicked.connect(_paste_back)
        nav.addWidget(btn_back)
        nav.addStretch(1)

        btn_connect = QPushButton("연결")
        btn_connect.setObjectName("btnPrimary")
        btn_connect.setDefault(True)
        btn_connect.clicked.connect(self._finish)
        nav.addWidget(btn_connect)

        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(head)
        lay.addWidget(lead)
        lay.addWidget(self._edit)
        lay.addLayout(tools)
        lay.addWidget(detail)
        lay.addLayout(nav)
        return w

    def _on_toggle_visible(self, checked: bool) -> None:
        if checked:
            self._edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._btn_toggle.setText("숨김")
        else:
            self._edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._btn_toggle.setText("보기")

    def _paste_clipboard(self) -> None:
        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        text = (clip.text() or "").strip()
        if not text:
            QMessageBox.information(
                self, "클립보드 비어 있음", "브라우저에서 키를 먼저 복사하세요."
            )
            return
        self._edit.setText(text)
        self._edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _finish(self) -> None:
        raw = (self._edit.text() or "").strip()
        if not raw:
            self._wiz_log("[연결] finish 중단 — 키 칸 비어 있음")
            QMessageBox.warning(self, "키 없음", "키를 붙여 넣은 뒤 연결을 누르세요.")
            return
        if len(raw) < 20:
            self._wiz_log(f"[연결] finish 중단 — 키 너무 짧음 len={len(raw)}")
            QMessageBox.warning(
                self, "너무 짧음", "키 전체를 복사했는지 확인하세요."
            )
            return
        self._token = raw
        if not self._token_expires_at and self._web_pane is not None:
            exp = getattr(self._web_pane, "last_token_expires_at", None)
            if exp:
                self._token_expires_at = str(exp)
        self._want_device = False
        self._wiz_log(
            f"[연결] finish → accept 직전 token_len={len(raw)} "
            f"만료={self._token_expires_at or '—'}"
        )
        self.accept()

    def _pick_device(self) -> None:
        self._want_device = True
        self._token = ""
        self.accept()


# ----- Back-compat -----


class LoginMethodDialog(QDialog):
    METHOD_DEVICE = "device"
    METHOD_PAT = "pat"

    def __init__(self, parent: QWidget | None = None, *, reauth: bool = False) -> None:
        super().__init__(parent)
        self._method = self.METHOD_PAT
        self._wizard = ConnectGitHubWizard(parent, reauth=reauth)

    def exec(self) -> int:  # noqa: A003
        code = self._wizard.exec()
        if code == QDialog.DialogCode.Accepted:
            self._method = (
                self.METHOD_DEVICE
                if self._wizard.wants_device_flow()
                else self.METHOD_PAT
            )
            return int(QDialog.DialogCode.Accepted)
        return int(QDialog.DialogCode.Rejected)

    def selected_method(self) -> str:
        return self._method

    def wizard_token(self) -> str:
        return self._wizard.token()


class PatTokenDialog(ConnectGitHubWizard):
    def __init__(self, parent: QWidget | None = None, *, reauth: bool = False) -> None:
        super().__init__(parent, reauth=reauth)
