"""
Compact GitHub connect wizard (PAT only).

Short pages, minimal copy. Extra tips stay collapsed under 「자세히」.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.auth.pat_urls import (
    classic_pat_create_url,
    fine_pat_create_url,
    workflow_pat_create_url,
)
from app.config import is_device_flow_allowed
from app.ui.theme import Palette, active_palette

# Default path matches 「만들고 올리기」 = POST /user/repos + push.
# Classic `repo` can create private/public repos. Fine-grained "this repo only
# + Contents" cannot: the new name is not in the list yet, and Contents ≠ create.
# Note = CloneUp-YYYYMMDD-HHMMSS via classic_pat_create_url() each open.

PAT_LIST_URL = "https://github.com/settings/tokens"


def _pat_create_url() -> str:
    return classic_pat_create_url()


def _pat_create_url_fine() -> str:
    return fine_pat_create_url()


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
        lambda: QDesktopServices.openUrl(QUrl(_pat_create_url()))
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


def _dialog_style(p: Palette) -> str:
    return f"""
    QDialog {{
        background: {p.bg_window};
    }}
    QDialog#connectWebDialog {{
        background: #fbfaf8;
    }}
    QWidget#connOuter {{
        background: #fbfaf8;
    }}
    QLabel#wizTitle {{
        color: {p.text};
        font-size: 17px;
        font-weight: 600;
        background: transparent;
        border: none;
    }}
    QLabel#wizLead {{
        color: #4a453b;
        font-size: 13px;
        background: transparent;
        border: none;
    }}
    QLabel#wizMeta {{
        color: #6d675c;
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
        background: #fbfaf8;
        border: none;
    }}
    QFrame#connHeader {{
        background: #f2efe9;
        border: none;
        border-bottom: 1px solid #ddd8d0;
    }}
    QFrame#connTrack {{
        background: #f2efe9;
        border: 1px solid #e6e1d8;
        border-radius: 7px;
    }}
    QFrame#connGuideCard {{
        background: #fbfaf8;
        border: 1px solid #c9c5bd;
        border-radius: 10px;
    }}
    QWidget#connGuideOuter {{
        background: #fbfaf8;
    }}
    QFrame#connBrowser {{
        background: #ffffff;
        border: 1px solid #cdc8bf;
        border-radius: 7px;
    }}
    QFrame#connAddrBar {{
        background: #f2efe9;
        border: none;
        border-bottom: 1px solid #ddd8d0;
    }}
    QFrame#connUrlBox {{
        background: #fbfaf8;
        border: 1px solid #cdc8bf;
        border-radius: 4px;
        min-height: 24px;
        max-height: 24px;
    }}
    QLineEdit#connUrlInner {{
        background: transparent;
        border: none;
        padding: 0;
        font-size: 11.5px;
        color: #4a453b;
        font-family: "IBM Plex Mono", Consolas, monospace;
        min-height: 20px;
        max-height: 22px;
    }}
    QLineEdit#connUrl {{
        background: #fbfaf8;
        border: 1px solid #cdc8bf;
        border-radius: 4px;
        padding: 2px 10px;
        font-size: 11.5px;
        color: #4a453b;
        font-family: "IBM Plex Mono", Consolas, monospace;
        min-height: 22px;
        max-height: 24px;
    }}
    QFrame#connWatch {{
        background: #f4f1e8;
        border-left: 3px solid #1f6f5c;
        border-top: none;
        border-right: none;
        border-bottom: none;
        border-radius: 0 6px 6px 0;
    }}
    QFrame#connWatchWarn {{
        background: #fbf6ee;
        border-left: 3px solid #8a6d12;
        border-top: none;
        border-right: none;
        border-bottom: none;
        border-radius: 0 6px 6px 0;
    }}
    QLabel#connWatchTag {{
        font-size: 12.5px;
        font-weight: 600;
        color: #1f6f5c;
        background: transparent;
        border: none;
    }}
    QLabel#connWatchTagWarn {{
        font-size: 12.5px;
        font-weight: 600;
        color: #8a6d12;
        background: transparent;
        border: none;
    }}
    QFrame#connFooter {{
        background: #f2efe9;
        border: none;
        border-top: 1px solid #e6e1d8;
    }}
    QComboBox#connExpiryCombo {{
        background: #fbfaf8;
        border: 1px solid #cdc8bf;
        border-radius: 6px;
        padding: 6px 10px;
        min-height: 28px;
        font-size: 12.5px;
        color: #3d382f;
    }}
    QComboBox#connExpiryCombo::drop-down {{
        border: none;
        width: 22px;
    }}
    QPushButton#connNavMini {{
        background: #fbfaf8;
        border: 1px solid #cdc8bf;
        border-radius: 4px;
        min-width: 18px;
        max-width: 18px;
        min-height: 18px;
        max-height: 18px;
        padding: 0;
        font-size: 10px;
        color: #6d675c;
    }}
    QPushButton#connNavMini:disabled {{
        color: #b7b1a5;
    }}
    QLineEdit#patEdit {{
        padding: 10px 13px;
        font-size: 13px;
        border: 1px solid #cdc8bf;
        border-radius: 6px;
        background: #ffffff;
        color: #2f2b24;
        font-family: "IBM Plex Mono", Consolas, monospace;
        min-height: 40px;
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
        background: #f2efe9;
        color: #b3ac9e;
        border: 1px solid #ddd8d0;
    }}
    QPushButton#btnSecondary {{
        background: #fbfaf8;
        color: #3d382f;
        border: 1px solid #b7b1a5;
        border-radius: 5px;
        padding: 8px 16px;
        font-weight: 500;
        font-size: 12.5px;
        min-height: 36px;
    }}
    QPushButton#btnSecondary:hover {{
        background: #f4f1e8;
    }}
    QPushButton#btnSecondary:disabled {{
        background: #f2efe9;
        color: #b3ac9e;
        border: 1px solid #ddd8d0;
    }}
    QPushButton#btnGhost {{
        background: transparent;
        color: #6d675c;
        border: none;
        padding: 4px 6px;
        font-size: 12.5px;
    }}
    QPushButton#btnGhost:hover {{
        color: #3d382f;
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
_CONNECT_GUIDE_OPACITY = 0.72

# Clipboard auto-advance: detect a copied PAT without sniffing browser traffic.
_TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")


def _looks_like_github_token(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 20 or " " in t or "\n" in t:
        return False
    return any(t.startswith(p) for p in _TOKEN_PREFIXES)


# Web-mode stack: choice first (no library/start page), then WebView (Path A)
_WEB_PAGE_CHOICE = 0
_WEB_PAGE_WEB = 1


class ConnectGitHubWizard(QDialog):
    """
    PAT connect wizard.

    Path A: embedded Qt WebEngine (this dialog only).
    Path B: user chooses external browser → this dialog closes, then
    ``ExternalBrowserPatGuide`` runs alone (main_window). Never nested.
    """

    def __init__(self, parent: QWidget | None = None, *, reauth: bool = False) -> None:
        # No QWidget parent → dragging this dialog does not raise the main window.
        self._anchor = parent
        super().__init__(None)
        self._token = ""
        self._token_expires_at: str | None = None  # from WebView page scrape
        self._want_device = False
        self._want_external = False  # Path B: close wizard, main runs Guide alone
        self._reauth = reauth
        self._via_fine = False
        self._browser_opened = False
        self._clip_seen = ""
        self._web_pane = None
        self._ui_now = 0
        self._ui_max = 0
        self._web_live_stage = None  # GitHubPageStage | None
        self._key_row: QWidget | None = None
        self._key_note: QLabel | None = None
        self._web_cta: QPushButton | None = None
        self._web_cta_note: QLabel | None = None
        self._web_url: QLineEdit | None = None
        self._web_back_btn: QPushButton | None = None
        self._web_fwd_btn: QPushButton | None = None
        self._web_url_editing = False
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
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
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
            # Choice only at first — WebView page is added lazily on Path A.
            # Keeping WebEngine in the stack made sizeHint/~layout thrash the
            # choice window height (tall↔short pulse).
            self._stack.addWidget(self._page_choice())
            self._choice_index = _WEB_PAGE_CHOICE
            self._web_index = -1
            self._paste_index = -1
            self._web_page_built = False
            self._progress.hide()  # counter lives inside the card
        else:
            for i, (title, body) in enumerate(_STEPS):
                if i == _STEP_PASTE:
                    self._stack.addWidget(self._page_paste(title, body))
                else:
                    self._stack.addWidget(self._page_guide(i, title, body))
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
        if self._use_web:
            self._go(self._choice_index)
            # Final size applied in showEvent → _fit_choice_dialog (compact)
        else:
            self._go(_STEP_START)
            self._place_center_on_anchor()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Choice-first: compact dialog. Maximize only when entering WebView.
        if self._use_web and not getattr(self, "_web_sized", False):
            self._web_sized = True
            QTimer.singleShot(0, self._fit_choice_dialog)

    def _screen_for_dialog(self):
        from app.util.screen_fit import screen_for_widget

        return screen_for_widget(self, anchor=self._anchor)

    def _place_normal_web_size(self) -> None:
        """□ restore size: 16:9 client, centered in the work area (DPI-aware)."""
        from app.util.screen_fit import place_normal_16x9

        place_normal_16x9(self, anchor=self._anchor)

    def _on_choice_page(self) -> bool:
        return (
            self._use_web
            and self._stack.currentIndex() == self._choice_index
        )

    def _fit_choice_dialog(self) -> None:
        """Compact window sized to the choice card only (stable — no resize loop)."""
        from app.util.screen_fit import read_screen_info, screen_for_widget
        from PySide6.QtCore import Qt

        if getattr(self, "_fitting_choice", False):
            return
        self._fitting_choice = True
        try:
            # Suppress changeEvent → _place_normal_web_size (fought this fit).
            self._suppress_state_fit = True
            st = self.windowState()
            if st & (
                Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen
            ):
                self.setWindowState(Qt.WindowState.WindowNoState)
            self.showNormal()
            # Size from choice *page* only (dialog sizeHint includes WebView ~900px).
            page = self._stack.widget(self._choice_index)
            ph = page.sizeHint() if page is not None else None
            pw = int(ph.width()) if ph is not None and ph.width() > 0 else 520
            phh = int(ph.height()) if ph is not None and ph.height() > 0 else 340
            w = max(480, min(560, max(pw, 520)))
            h = max(300, min(380, phh + 48))
            info = read_screen_info(screen_for_widget(self, anchor=self._anchor))
            if info is not None:
                w = min(w, max(400, info.available_w - 48))
                h = min(h, max(280, info.available_h - 48))
            # Fixed size so the stack/WebView cannot stretch the shell again
            self.setMinimumSize(w, h)
            self.setFixedSize(w, h)
            self._place_center_on_anchor()
        except Exception:
            self.setFixedSize(520, 340)
            self._place_center_on_anchor()
        finally:
            self._fitting_choice = False
            QTimer.singleShot(300, self._clear_suppress_state_fit)

    def _clear_suppress_state_fit(self) -> None:
        self._suppress_state_fit = False

    def _fit_web_dialog(self) -> None:
        """
        Maximize into the taskbar-safe work area when entering WebView (Path A).

        □ restores to 16:9 via ``_place_normal_web_size()``.
        Does **not** use FullScreen — that breaks under Windows display scaling.
        """
        from app.util.screen_fit import apply_work_area_maximized, clear_size_locks

        try:
            self._suppress_state_fit = True
            # Unlock choice setFixedSize before maximizing
            self.setMinimumSize(640, 360)
            self.setMaximumSize(16777215, 16777215)
            self.showNormal()
            self._place_normal_web_size()
            clear_size_locks(self)
            apply_work_area_maximized(self, anchor=self._anchor)
        except Exception:
            self.resize(1280, 720)
        finally:
            QTimer.singleShot(300, self._clear_suppress_state_fit)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if not self._use_web:
            return
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QWindowStateChangeEvent

        if event.type() != QEvent.Type.WindowStateChange:
            return
        # Choice screen must stay compact — never apply 16:9 restore here
        if self._on_choice_page() or getattr(self, "_suppress_state_fit", False):
            return
        # Leaving maximized (or legacy FullScreen) on WebView → 16:9 restore
        old = Qt.WindowState.WindowNoState
        if isinstance(event, QWindowStateChangeEvent):
            old = event.oldState()
        now = self.windowState()
        leaving_max = bool(old & Qt.WindowState.WindowMaximized) and not bool(
            now & Qt.WindowState.WindowMaximized
        )
        leaving_fs = bool(old & Qt.WindowState.WindowFullScreen) and not bool(
            now & Qt.WindowState.WindowFullScreen
        )
        if (leaving_max or leaving_fs) and not self.isMinimized():
            QTimer.singleShot(50, self._place_normal_web_size)

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

    def _apply_detected_token(self, text: str) -> None:
        if hasattr(self, "_edit") and self._edit is not None:
            self._edit.setText(text)
        # Capture expiration scraped from the create/issued page (if any)
        if self._web_pane is not None:
            exp = getattr(self._web_pane, "last_token_expires_at", None)
            if exp:
                self._token_expires_at = str(exp)
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
        QTimer.singleShot(0, self._run_auto_finish)

    def _run_auto_finish(self) -> None:
        self._auto_finish_pending = False
        if not self.isVisible():
            return
        raw = ""
        if hasattr(self, "_edit") and self._edit is not None:
            raw = (self._edit.text() or "").strip()
        if not _looks_like_github_token(raw):
            return
        self._finish()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_clipboard_watch()
        super().closeEvent(event)

    def reject(self) -> None:
        self._stop_clipboard_watch()
        super().reject()

    def accept(self) -> None:
        self._stop_clipboard_watch()
        super().accept()

    def token(self) -> str:
        return self._token

    def token_expires_at(self) -> str | None:
        """ISO-8601 / ``none`` from WebView page scrape, if known."""
        return self._token_expires_at

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
            # CHOICE (0) · WEB (lazy) — never nest external guide here
            if index == self._choice_index or index <= _WEB_PAGE_CHOICE:
                index = self._choice_index
            else:
                self._ensure_web_page()
                index = self._web_index
            self._stack.setCurrentIndex(index)
            self.setWindowOpacity(1.0)
            if index == self._choice_index:
                self._progress.setText("로그인 방식")
                QTimer.singleShot(0, self._fit_choice_dialog)
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
        self._ensure_web_page()
        self._stack.setCurrentIndex(self._web_index)
        self.setWindowOpacity(1.0)
        if self._ui_now == 0 and self._ui_max == 0:
            self._paint_web_guide(0)
        else:
            self._paint_web_guide(self._ui_now)
        self._fit_web_dialog()

    def _open_create_page(self) -> None:
        # Classic + repo — required path for 「만들고 올리기」 (create repo).
        self._via_fine = False
        url = _pat_create_url()
        if self._use_web:
            self._start_web(url)
            return
        QDesktopServices.openUrl(QUrl(url))
        self._mark_browser_opened()
        self._go(_STEP_WORK)

    def _open_fine_and_paste(self) -> None:
        self._via_fine = True
        url = _pat_create_url_fine()
        if self._use_web:
            self._start_web(url)
            return
        QDesktopServices.openUrl(QUrl(url))
        self._mark_browser_opened()
        self._go(_STEP_WORK)

    def _reload_pat_create_fresh_note(self) -> None:
        """After Note collision — open classic form with a new CloneUp-date-time Note."""
        url = _pat_create_url_fine() if self._via_fine else _pat_create_url()
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
        self._ensure_web_page()
        self._browser_opened = True
        if not self._clip_timer.isActive():
            self._clip_timer.start()
        self._go_web()
        if self._web_pane is not None:
            self._web_pane.load_url(url)

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

    def _page_choice(self) -> QWidget:
        """First screen: pick WebView (Path A) or external browser (Path B)."""
        # Height follows content — no Expanding/stretch (avoids elongated bottom)
        card = QFrame()
        card.setObjectName("connGuideCard")
        card.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )

        head = QLabel(
            "새 키로 다시 연결"
            if self._reauth
            else "로그인 방식을 고르세요"
        )
        head.setObjectName("wizTitle")
        head.setWordWrap(True)

        lead = QLabel(
            "어디서 로그인할지 고르세요. 창은 하나만 사용합니다.\n"
            "Google·패스키가 편하면 브라우저를 골라도 됩니다.\n"
            "키 목록·세분 키는 설정에서 열 수 있습니다."
        )
        lead.setObjectName("wizLead")
        lead.setWordWrap(True)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(12)
        lay.addWidget(head)
        lay.addWidget(lead)

        btn_web = QPushButton("앱 안에서 로그인")
        btn_web.setObjectName("btnPrimary")
        btn_web.setDefault(True)
        btn_web.setToolTip("CloneUp 창 안에서 GitHub 로그인·키 만들기를 진행합니다.")
        btn_web.clicked.connect(self._start_webview_path)

        btn_ext = QPushButton("브라우저에서 로그인")
        btn_ext.setObjectName("btnSecondary")
        btn_ext.setToolTip(
            "OS 브라우저 + 작은 안내 창만 사용합니다. "
            "이 연결 마법사는 닫힙니다."
        )
        btn_ext.clicked.connect(self._start_external_path)

        lay.addWidget(btn_web)
        lay.addWidget(btn_ext)

        nav = QHBoxLayout()
        nav.setSpacing(10)
        btn_cancel = QPushButton("취소")
        btn_cancel.setObjectName("btnGhost")
        btn_cancel.clicked.connect(self.reject)
        nav.addWidget(btn_cancel)
        nav.addStretch(1)
        lay.addSpacing(4)
        lay.addLayout(nav)
        return card

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
        lock.setStyleSheet(
            "font-size:10px;color:#1f6f5c;border:none;background:transparent;"
        )
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
        only.setObjectName("wizMeta")
        only.setStyleSheet("font-size:11px;color:#6d675c;border:none;")
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
        br_lay.addWidget(addr)
        br_lay.addWidget(self._web_pane, 1)
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

        # footer
        footer = QFrame()
        footer.setObjectName("connFooter")
        footer.setFixedHeight(72)
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(22, 0, 22, 0)
        foot.setSpacing(12)
        btn_cancel = QPushButton("취소")
        btn_cancel.setObjectName("btnGhost")
        btn_cancel.clicked.connect(self.reject)
        btn_back = QPushButton("← 이전")
        btn_back.setObjectName("btnGhost")
        btn_back.clicked.connect(lambda: self._go(self._choice_index))
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
        self._web_cta = QPushButton("다음")
        self._web_cta.setObjectName("btnPrimary")
        self._web_cta.setEnabled(False)
        self._web_cta.clicked.connect(self._on_web_cta)
        foot.addWidget(btn_cancel)
        foot.addWidget(btn_back)
        foot.addWidget(self._btn_switch_external)
        foot.addStretch(1)
        foot.addWidget(self._expiry_lab)
        foot.addWidget(self._expiry_combo)
        foot.addStretch(1)
        foot.addWidget(self._web_cta_note)
        foot.addWidget(self._web_cta)

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
        """시안: 15×15 circle (border-radius: 50%)."""

        class _CircleMark(QWidget):
            def __init__(self, *, done: bool, cur: bool) -> None:
                super().__init__()
                self._done = done
                self._cur = cur
                self.setFixedSize(15, 15)
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

            def paintEvent(self, event) -> None:  # noqa: N802
                from PySide6.QtGui import QColor, QPainter, QPen

                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                # Inset 0.5 so the 1px stroke sits fully inside the 15×15 box
                rect = self.rect().adjusted(1, 1, -1, -1)
                if self._done:
                    p.setBrush(QColor("#1f6f5c"))
                    p.setPen(QPen(QColor("#1f6f5c"), 1))
                    p.drawEllipse(rect)
                    p.setPen(QColor("#fbfaf8"))
                    font = p.font()
                    font.setPixelSize(9)
                    font.setBold(True)
                    p.setFont(font)
                    p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "✓")
                elif self._cur:
                    p.setBrush(QColor("#fbfaf8"))
                    p.setPen(QPen(QColor("#1f6f5c"), 1))
                    p.drawEllipse(rect)
                else:
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(QColor("#cdc8bf"), 1))
                    p.drawEllipse(rect)
                p.end()

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
            if cur:
                lab.setStyleSheet(
                    "color:#1f6f5c;font-weight:600;font-size:12.5px;"
                    "background:transparent;border:none;"
                )
                cell.setStyleSheet(
                    "QFrame { background:#fbfaf8; border-radius:5px; border:none; }"
                )
            elif done:
                lab.setStyleSheet(
                    "color:#4a453b;font-size:12.5px;"
                    "background:transparent;border:none;"
                )
                cell.setStyleSheet("QFrame { background:transparent; border:none; }")
            else:
                lab.setStyleSheet(
                    "color:#8b8477;font-size:12.5px;"
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
                    "color:#b7b1a5;font-size:11px;"
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
        if self._web_cta is None or self._web_cta_note is None:
            return
        from app.ui.connect_webview import step_copy

        copy = step_copy(self._ui_now)
        # CTA always uses btnPrimary — disabled QSS matches 시안 gray next
        self._web_cta.setObjectName("btnPrimary")
        if self._ui_now < 3:
            self._web_cta.setText("다음")
            self._web_cta.setEnabled(False)
            self._web_cta_note.setText(str(copy["ctaNote"]))
        else:
            has = bool((self._edit.text() or "").strip()) if hasattr(self, "_edit") else False
            tok_ok = _looks_like_github_token(
                (self._edit.text() or "").strip() if hasattr(self, "_edit") else ""
            )
            self._web_cta.setText("연결")
            self._web_cta.setEnabled(has)
            if tok_ok:
                self._web_cta_note.setText("키를 인식했어요. 자동으로 연결합니다…")
                self._schedule_auto_finish()
            else:
                self._web_cta_note.setText(
                    "" if has else "키가 보이거나 복사되면 자동으로 연결됩니다"
                )
        self._web_cta.style().unpolish(self._web_cta)
        self._web_cta.style().polish(self._web_cta)

    def _on_web_cta(self) -> None:
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
            self._web_pane.apply_expiration_choice(val)

    def _sync_expiry_to_webview(self) -> None:
        """Push current combo selection into the page (after tokens/new loads)."""
        if self._expiry_combo is None or self._web_pane is None:
            return
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
            # On create form, apply footer Expiration before auto Generate
            if st in (
                GitHubPageStage.TOKEN_CLASSIC_NEW,
                GitHubPageStage.TOKEN_FINE_NEW,
            ):
                QTimer.singleShot(200, self._sync_expiry_to_webview)
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

        if kind == "rejected":
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
            return

        if kind == "token_error":
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
            return

        if kind == "current" and idx is not None:
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
            # Critical: pass live_stage so /settings/tokens gets list overlay
            # (Generate new token…), not generic "키를 만들어 주세요"
            self._paint_web_guide(i, live_stage=live)
            visible = str((meta or {}).get("visible_pat") or "")
            if visible:
                self._apply_detected_token(visible)
            return

    def _on_google_oauth_external(self, url: str) -> None:
        """
        Google sign-in cannot run inside Qt WebEngine.

        Immediately switch to Path B (same as clicking
        「브라우저에서 로그인으로 바꾸기」) — do not nest a guide under this wizard.
        """
        _ = url
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
            QMessageBox.warning(self, "키 없음", "키를 붙여 넣은 뒤 연결을 누르세요.")
            return
        if len(raw) < 20:
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
