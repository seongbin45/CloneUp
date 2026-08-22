"""
Compact GitHub connect wizard (PAT only).

Short pages, minimal copy. Extra tips stay collapsed under 「자세히」.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
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

from app.config import is_device_flow_allowed
from app.ui.theme import Palette, active_palette

# Default path matches 「만들고 올리기」 = POST /user/repos + push.
# Classic `repo` can create private/public repos. Fine-grained "this repo only
# + Contents" cannot: the new name is not in the list yet, and Contents ≠ create.
PAT_CREATE_URL = (
    "https://github.com/settings/tokens/new"
    "?scopes=repo&description=CloneUp"
)
# Existing-repo sync only (push/pull Contents). Not default for first publish.
PAT_CREATE_URL_FINE = (
    "https://github.com/settings/personal-access-tokens/new"
    "?name=CloneUp"
    "&contents=write"
)
PAT_LIST_URL = "https://github.com/settings/tokens"

# Only used by show_missing_workflow_scope_help below — a *reactive* dialog
# shown after a push actually fails for lacking `workflow`. Never used by
# the default connect wizard (_page_make_key).
WORKFLOW_PAT_CREATE_URL = (
    "https://github.com/settings/tokens/new"
    "?scopes=repo,workflow&description=CloneUp"
)


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
        lambda: QDesktopServices.openUrl(QUrl(PAT_CREATE_URL))
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
        lambda: QDesktopServices.openUrl(QUrl(WORKFLOW_PAT_CREATE_URL))
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
    QLabel#wizTitle {{
        color: {p.text};
        font-size: 16px;
        font-weight: 700;
    }}
    QLabel#wizLead {{
        color: {p.text_muted};
        font-size: 12.5px;
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
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#wizDetail {{
        color: {p.text_muted};
        font-size: 12px;
        padding: 4px 2px;
    }}
    QLineEdit#patEdit {{
        padding: 10px 12px;
        font-size: 13.5px;
        border: 1px solid {p.border_input};
        border-radius: 8px;
        background: {p.bg_input};
        color: {p.text};
    }}
    QPushButton#btnPrimary {{
        background: {p.primary};
        color: {p.text_on_primary};
        border: none;
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 600;
        font-size: 13px;
        min-height: 32px;
    }}
    QPushButton#btnPrimary:hover {{
        background: {p.primary_hover};
    }}
    QPushButton#btnSecondary {{
        background: {p.bg_muted};
        color: {p.text};
        border: 1px solid {p.border_input};
        border-radius: 8px;
        padding: 8px 12px;
        font-weight: 600;
        font-size: 12.5px;
        min-height: 32px;
    }}
    QPushButton#btnSecondary:hover {{
        background: {p.hover_muted};
    }}
    QPushButton#btnGhost {{
        background: transparent;
        color: {p.text_muted};
        border: none;
        padding: 4px 6px;
        font-size: 12px;
    }}
    QPushButton#btnGhost:hover {{
        color: {p.primary};
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


class ConnectGitHubWizard(QDialog):
    """
    PAT connect wizard.

    Preferred: embedded Qt WebEngine + live page-stage guide.
    Fallback: external browser + checklist (when WebEngine is missing).
    """

    def __init__(self, parent: QWidget | None = None, *, reauth: bool = False) -> None:
        # No QWidget parent → dragging this dialog does not raise the main window.
        self._anchor = parent
        super().__init__(None)
        self._token = ""
        self._want_device = False
        self._reauth = reauth
        self._via_fine = False
        self._browser_opened = False
        self._clip_seen = ""
        self._web_pane = None
        from app.ui.connect_webview import webengine_available

        self._use_web = webengine_available()
        p = active_palette()

        self.setWindowTitle("GitHub 연결")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowOpacity(1.0)
        if self._use_web:
            self.setMinimumWidth(980)
            self.setMinimumHeight(680)
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
            # 0=start, 1=embedded GitHub + guide
            self._stack.addWidget(
                self._page_guide(_STEP_START, _STEPS[_STEP_START][0], _STEPS[_STEP_START][1])
            )
            self._stack.addWidget(self._page_web())
            self._web_index = 1
            self._paste_index = 1  # token field lives on web page
        else:
            for i, (title, body) in enumerate(_STEPS):
                if i == _STEP_PASTE:
                    self._stack.addWidget(self._page_paste(title, body))
                else:
                    self._stack.addWidget(self._page_guide(i, title, body))
            self._web_index = -1
            self._paste_index = _STEP_PASTE

        self._clip_timer = QTimer(self)
        self._clip_timer.setInterval(500)
        self._clip_timer.timeout.connect(self._poll_clipboard_for_token)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        root.addWidget(self._progress)
        root.addWidget(self._stack, 1)
        self._go(_STEP_START)
        if self._use_web:
            self._fit_web_dialog()
        else:
            self._place_center_on_anchor()

    def _fit_web_dialog(self) -> None:
        """Give the embedded GitHub page nearly full available screen space."""
        try:
            screen = None
            if self._anchor is not None:
                screen = self._anchor.screen()
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is None:
                self.resize(1100, 760)
                return
            avail = screen.availableGeometry()
            w = max(980, int(avail.width() * 0.92))
            h = max(680, int(avail.height() * 0.90))
            self.resize(w, h)
            g = self.frameGeometry()
            g.moveCenter(avail.center())
            self.move(g.topLeft())
        except Exception:
            self.resize(1100, 760)

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

    def _apply_detected_token(self, text: str) -> None:
        if hasattr(self, "_edit") and self._edit is not None:
            self._edit.setText(text)
        if self._use_web:
            if self._stack.currentIndex() != self._web_index:
                self._go_web()
            self.setWindowOpacity(1.0)
            if hasattr(self, "_web_hint") and self._web_hint is not None:
                self._web_hint.setText(
                    "키가 준비되었습니다. 「연결」을 눌러 주세요."
                )
        else:
            if self._stack.currentIndex() != _STEP_PASTE:
                self._go(_STEP_PASTE)
        self.raise_()
        self.activateWindow()

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

    def wants_device_flow(self) -> bool:
        return self._want_device

    def _sync_opacity(self, index: int) -> None:
        """Translucent only on the browser-work screen after the browser opens."""
        over_browser = self._browser_opened and index == _STEP_WORK
        self.setWindowOpacity(
            _CONNECT_GUIDE_OPACITY if over_browser else 1.0
        )

    def _go(self, index: int) -> None:
        if self._use_web:
            # Only start (0) and web (1) pages exist.
            index = 0 if index <= 0 else self._web_index
            self._stack.setCurrentIndex(index)
            if index == 0:
                self._progress.setText("1 / 2  ·  시작")
                self.setWindowOpacity(1.0)
            else:
                self._progress.setText("2 / 2  ·  키 만들기")
                self._fit_web_dialog()
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
        self._stack.setCurrentIndex(self._web_index)
        self._progress.setText("2 / 2  ·  키 만들기")
        self.setWindowOpacity(1.0)
        self._fit_web_dialog()

    def _open_create_page(self) -> None:
        # Classic + repo — required path for 「만들고 올리기」 (create repo).
        self._via_fine = False
        if self._use_web:
            self._start_web(PAT_CREATE_URL)
            return
        QDesktopServices.openUrl(QUrl(PAT_CREATE_URL))
        self._mark_browser_opened()
        self._go(_STEP_WORK)

    def _open_fine_and_paste(self) -> None:
        self._via_fine = True
        if self._use_web:
            self._start_web(PAT_CREATE_URL_FINE)
            return
        QDesktopServices.openUrl(QUrl(PAT_CREATE_URL_FINE))
        self._mark_browser_opened()
        self._go(_STEP_WORK)

    def _start_web(self, url: str) -> None:
        self._browser_opened = True
        if not self._clip_timer.isActive():
            self._clip_timer.start()
        self._go_web()
        if self._web_pane is not None:
            self._web_pane.load_url(url)

    def _page_guide(self, index: int, title: str, body: str) -> QWidget:
        w = QWidget()
        head = QLabel(
            ("새 키로 다시 연결" if self._reauth else title)
            if index == _STEP_START
            else title
        )
        head.setObjectName("wizTitle")
        head.setWordWrap(True)

        lead = QLabel(body)
        lead.setObjectName("wizLead")
        lead.setWordWrap(True)

        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(head)
        lay.addWidget(lead)

        if index == _STEP_START:
            detail = _DetailToggle(
                "키는 채팅·캡처·메일에 붙이지 마세요.\n"
                "만료되면 새 키를 만들어 다시 연결합니다.\n"
                "GitHub 영문: Tokens (classic) · Generate new token · repo."
            )
            lay.addWidget(detail)

            side = QHBoxLayout()
            side.setSpacing(8)
            btn_fine = QPushButton("세분 키 (기존 저장소)")
            btn_fine.setObjectName("btnSecondary")
            btn_fine.setToolTip(
                "이미 GitHub에 있는 저장소만 동기화할 때.\n"
                "만들고 올리기(새 저장소)에는 classic이 필요합니다.\n"
                "누르면 세분 키 페이지를 연 뒤, 키를 복사하면 붙여넣기로 이동합니다."
            )
            btn_fine.clicked.connect(self._open_fine_and_paste)
            btn_list = QPushButton("키 목록")
            btn_list.setObjectName("btnSecondary")
            btn_list.setToolTip("GitHub에 이미 있는 키 목록을 엽니다.")
            btn_list.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl(PAT_LIST_URL))
            )
            side.addWidget(btn_fine)
            side.addWidget(btn_list)
            side.addStretch(1)
            lay.addLayout(side)

            if is_device_flow_allowed():
                btn_dev = QPushButton("개발용 장치 코드")
                btn_dev.setObjectName("btnGhost")
                btn_dev.clicked.connect(self._pick_device)
                lay.addWidget(btn_dev)

        # Primary actions per step
        nav = QHBoxLayout()
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
            # START only
            if self._use_web:
                btn_next = QPushButton("키 만들기 시작 →")
                btn_next.setObjectName("btnPrimary")
                btn_next.setDefault(True)
                btn_next.clicked.connect(
                    lambda: self._open_create_page()
                    if not self._via_fine
                    else self._open_fine_and_paste()
                )
                nav.addWidget(btn_next)
            else:
                btn_next = QPushButton("다음 →")
                btn_next.setObjectName("btnPrimary")
                btn_next.setDefault(True)
                btn_next.clicked.connect(lambda: self._go(index + 1))
                nav.addWidget(btn_next)

        lay.addLayout(nav)
        return w

    def _page_web(self) -> QWidget:
        """Embedded GitHub + live stage guide (WebEngine path)."""
        from app.auth.github_page_stage import GitHubPageStage
        from app.ui.connect_webview import (
            GitHubConnectWebPane,
            checklist_text,
            guide_line_for_stage,
        )

        w = QWidget()
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._web_stage_title = QLabel("준비 중…")
        self._web_stage_title.setObjectName("wizTitle")
        self._web_stage_title.setWordWrap(True)

        self._web_hint = QLabel(
            "아래 화면에서 GitHub 로그인부터 키 만들기까지 진행하세요. "
            "패스키가 막히면 비밀번호·인증 앱 코드 또는 「외부 브라우저로 열기」."
        )
        self._web_hint.setObjectName("wizLead")
        self._web_hint.setWordWrap(True)

        self._web_check = QLabel(checklist_text(set(), GitHubPageStage.UNKNOWN))
        self._web_check.setObjectName("wizBox")
        self._web_check.setWordWrap(True)

        self._web_pane = GitHubConnectWebPane(w)
        self._web_pane.stage_changed.connect(self._on_web_stage)
        self._web_pane.token_found.connect(self._apply_detected_token)
        self._web_pane.load_failed.connect(self._on_web_load_failed)

        self._edit = QLineEdit()
        self._edit.setObjectName("patEdit")
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("키가 여기 채워지거나, 직접 붙여 넣으세요")
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
        tools.addWidget(self._edit, 1)
        tools.addWidget(btn_paste)
        tools.addWidget(self._btn_toggle)

        btn_ext = QPushButton("외부 브라우저로 열기")
        btn_ext.setObjectName("btnSecondary")
        btn_ext.clicked.connect(self._open_external_from_web)

        btn_back = QPushButton("← 이전")
        btn_back.setObjectName("btnGhost")
        btn_back.clicked.connect(lambda: self._go(0))
        btn_cancel = QPushButton("취소")
        btn_cancel.setObjectName("btnGhost")
        btn_cancel.clicked.connect(self.reject)
        btn_connect = QPushButton("연결")
        btn_connect.setObjectName("btnPrimary")
        btn_connect.setDefault(True)
        btn_connect.clicked.connect(self._finish)

        nav = QHBoxLayout()
        nav.addWidget(btn_cancel)
        nav.addWidget(btn_back)
        nav.addWidget(btn_ext)
        nav.addStretch(1)
        nav.addWidget(btn_connect)

        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self._web_stage_title)
        lay.addWidget(self._web_hint)
        lay.addWidget(self._web_check)
        lay.addWidget(self._web_pane, 1)  # take remaining height
        lay.addLayout(tools)
        lay.addLayout(nav)
        return w

    def _on_web_stage(self, stage: object) -> None:
        from app.auth.github_page_stage import GitHubPageStage
        from app.ui.connect_webview import checklist_text, guide_line_for_stage

        st = stage if isinstance(stage, GitHubPageStage) else GitHubPageStage.UNKNOWN
        self._web_stage_title.setText(guide_line_for_stage(st))
        reached = self._web_pane.reached if self._web_pane else set()
        self._web_check.setText(checklist_text(reached, st))

    def _on_web_load_failed(self, _msg: str) -> None:
        if self._web_hint is not None:
            self._web_hint.setText(
                "페이지를 불러오지 못했습니다. "
                "「외부 브라우저로 열기」로 진행한 뒤 키를 복사하세요."
            )

    def _open_external_from_web(self) -> None:
        url = PAT_CREATE_URL_FINE if self._via_fine else PAT_CREATE_URL
        QDesktopServices.openUrl(QUrl(url))
        if self._web_hint is not None:
            self._web_hint.setText(
                "외부 브라우저에서 키를 만든 뒤 복사하세요. "
                "복사되면 아래 칸에 자동으로 들어올 수 있습니다."
            )

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
