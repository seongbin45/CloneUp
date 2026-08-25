"""Embedded GitHub WebView for PAT connect + page-stage signals.

Optional: requires PySide6 Qt WebEngine (PySide6-Addons). Callers must
fall back to an external browser when ``webengine_available()`` is False.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.auth.github_page_stage import (
    GitHubPageStage,
    PageSnapshot,
    detect_github_page_stage,
    stage_label_ko,
)

# Browser-like page zoom (QWebEngineView.setZoomFactor)
_ZOOM_MIN = 0.5
_ZOOM_MAX = 3.0
_ZOOM_STEP = 0.1
_ZOOM_DEFAULT = 1.0

# Google blocks sign-in inside embedded WebViews ("may not be secure").
_GOOGLE_OAUTH_HOSTS = frozenset(
    {
        "accounts.google.com",
        "account.google.com",
    }
)


def is_google_oauth_url(url: str) -> bool:
    """True if ``url`` is a Google account / OAuth sign-in page."""
    try:
        host = (QUrl(url).host() or "").lower()
    except Exception:
        host = ""
    if not host:
        u = (url or "").lower()
        return "accounts.google.com" in u
    if host in _GOOGLE_OAUTH_HOSTS:
        return True
    # Rare regional / mirror hosts
    return host.endswith(".google.com") and host.startswith("accounts.")


def looks_like_insecure_browser_block(title: str, html: str) -> bool:
    """Google/GitHub 'This browser or app may not be secure' interstitial."""
    blob = f"{title or ''}\n{html or ''}".lower()
    needles = (
        "may not be secure",
        "couldn't sign you in",
        "couldn’t sign you in",
        "try using a different browser",
        "browser or app may not be secure",
    )
    return any(n in blob for n in needles)

# Prefer a mainstream desktop Chrome UA so GitHub is less likely to treat
# the embed as a bot. Version string is cosmetic.
_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Best-effort token scrape on the "copy now" page (never log the result).
_JS_FIND_TOKEN = r"""
(() => {
  const pick = (s) => (s || "").trim();
  const el = document.querySelector(
    "code.js-access-token, #new-access-token, input#new-oauth-token, span.token-value"
  );
  if (el) {
    const v = pick(el.value || el.textContent);
    if (v) return v;
  }
  for (const i of document.querySelectorAll("input")) {
    const v = pick(i.value);
    if (/^gh[pousr]_/i.test(v) || /^github_pat_/i.test(v)) return v;
  }
  const text = document.body ? (document.body.innerText || "") : "";
  const m = text.match(/\b(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b/);
  return m ? m[1] : "";
})()
"""

# User-facing 4 steps (desin/CloneUp GitHub 연결.dc.html)
UI_STEP_NAMES: tuple[str, ...] = ("로그인", "인증 코드", "키 만들기", "키 복사")

_STAGE_TO_UI: dict[GitHubPageStage, int] = {
    GitHubPageStage.LOGIN: 0,
    GitHubPageStage.AUTH_2FA: 1,
    GitHubPageStage.TOKEN_CLASSIC_NEW: 2,
    GitHubPageStage.TOKEN_FINE_NEW: 2,
    GitHubPageStage.TOKEN_CLASSIC_LIST: 2,
    GitHubPageStage.TOKEN_ISSUED: 3,
}


def webengine_available() -> bool:
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

        return True
    except Exception:
        return False


def ui_index_for_stage(stage: GitHubPageStage) -> int | None:
    """Map detector stage → 0..3, or None if not a connect-flow page."""
    return _STAGE_TO_UI.get(stage)


def guide_line_for_stage(stage: GitHubPageStage) -> str:
    """Title only — current task (no parenthetical alternatives)."""
    i = ui_index_for_stage(stage)
    if i is not None:
        return step_copy(i)["title"]
    return {
        GitHubPageStage.UNKNOWN: "조금 더 진행해 주세요. 안내가 따라갑니다.",
        GitHubPageStage.AUTH_PASSKEY_OS: "패스키 확인이 필요할 수 있습니다",
        GitHubPageStage.SUDO_OR_OTHER: "추가 확인 화면입니다",
    }.get(stage, stage_label_ko(stage))


def step_copy(i: int) -> dict[str, str | bool]:
    """Copy deck for UI step i (0..3), matching the design mock."""
    steps: tuple[dict[str, str | bool], ...] = (
        {
            "stepName": "로그인",
            "title": "GitHub에 로그인해 주세요",
            "lead": (
                "아래는 GitHub의 실제 로그인 화면입니다. "
                "아이디와 비밀번호는 GitHub로 바로 전달되며, "
                "클론업은 입력한 내용을 보지 않습니다."
            ),
            "watchTag": "기다리는 중",
            "watchBody": (
                "로그인이 끝나면 다음 단계로 저절로 넘어갑니다. "
                "버튼을 누르지 않아도 됩니다."
            ),
            "watchWarn": False,
            "ctaNote": "로그인하면 자동으로 진행됩니다",
            "showKey": False,
        },
        {
            "stepName": "인증 코드",
            "title": "인증 코드를 입력해 주세요",
            "lead": (
                "GitHub가 한 번 더 확인을 요청했습니다. "
                "인증 앱의 6자리 숫자나 문자로 받은 코드를 "
                "아래 화면에 넣으세요."
            ),
            "watchTag": "기다리는 중",
            "watchBody": (
                "코드는 GitHub로 바로 갑니다. "
                "클론업은 코드를 저장하거나 읽지 않습니다."
            ),
            "watchWarn": False,
            "ctaNote": "인증되면 자동으로 진행됩니다",
            "showKey": False,
        },
        {
            "stepName": "키 만들기",
            "title": "키를 만들어 주세요",
            "lead": (
                "필요한 항목은 미리 채워 두었습니다. "
                "아래 화면을 내려 Generate token 버튼만 누르시면 됩니다."
            ),
            "watchTag": "확인",
            "watchBody": (
                "여기서 만드는 키는 이 앱이 저장소를 읽고 쓰는 데만 씁니다. "
                "계정 설정을 바꾸는 권한은 들어 있지 않습니다."
            ),
            "watchWarn": False,
            "ctaNote": "키가 만들어지면 자동으로 진행됩니다",
            "showKey": False,
        },
        {
            "stepName": "키 복사",
            "title": "키를 아래 칸에 넣어 주세요",
            "lead": (
                "키가 만들어졌습니다. "
                "아래 화면의 복사 버튼을 누르면 칸이 저절로 채워집니다. "
                "채워지지 않으면 직접 붙여 넣으세요."
            ),
            "watchTag": "주의",
            "watchBody": (
                "이 키는 비밀번호와 같습니다. "
                "다른 곳에 붙여 넣거나 남에게 보여주지 마세요. "
                "클론업은 이 컴퓨터의 자격 증명 저장소에만 넣어 둡니다."
            ),
            "watchWarn": True,
            "ctaNote": "",
            "showKey": True,
        },
    )
    return steps[max(0, min(i, 3))]


def checklist_text(reached: set[GitHubPageStage], current: GitHubPageStage) -> str:
    """One-line summary for tests; UI uses track widgets (one current only)."""
    ui = ui_index_for_stage(current)
    if ui is None:
        # Fall back to highest reached index
        ui = 0
        for st in reached:
            idx = ui_index_for_stage(st)
            if idx is not None:
                ui = max(ui, idx)
    parts: list[str] = []
    for n, label in enumerate(UI_STEP_NAMES):
        if n < ui:
            mark = "✓"
        elif n == ui:
            mark = "●"
        else:
            mark = "○"
        parts.append(f"{mark} {label}")
    return "  →  ".join(parts)


class _ConnectWebPage:
    """QWebEnginePage subclass created at runtime (WebEngine optional)."""


def _make_connect_web_page(profile, parent, on_external):
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

    class ConnectWebPage(QWebEnginePage):
        def __init__(self) -> None:
            super().__init__(profile, parent)
            self._on_external = on_external
            self._handed_off = False

        def acceptNavigationRequest(  # noqa: N802
            self, url: QUrl, nav_type, is_main_frame: bool
        ) -> bool:
            if is_main_frame and is_google_oauth_url(url.toString()):
                # Do not load Google SSO in-process — hand off once.
                if not self._handed_off:
                    self._handed_off = True
                    self._on_external(url.toString())
                return False
            return bool(super().acceptNavigationRequest(url, nav_type, is_main_frame))

        def reset_handoff(self) -> None:
            self._handed_off = False

    return ConnectWebPage()


class GitHubConnectWebPane(QWidget):
    """
    QWebEngineView that emits stage / optional token detections.

    Parent owns layout chrome (labels, connect button).
    """

    stage_changed = Signal(object)  # GitHubPageStage
    url_changed = Signal(str)
    token_found = Signal(str)
    load_failed = Signal(str)
    # Google SSO cannot run inside Qt WebEngine — open system browser.
    external_oauth_needed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWebEngineCore import QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._stage = GitHubPageStage.UNKNOWN
        self._reached: set[GitHubPageStage] = set()
        self._last_token = ""
        self._zoom = _ZOOM_DEFAULT
        self._oauth_hand_off_done = False

        self._view = QWebEngineView(self)
        # Default sizeHint is tiny (~100×30) and will collapse layouts.
        # Prefer expanding; keep a usable floor without forcing the card to overflow.
        self._view.setMinimumSize(640, 320)
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.setMinimumSize(640, 320)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        profile = None
        try:
            profile = self._view.page().profile()
            profile.setHttpUserAgent(_CHROME_UA)
        except Exception:
            try:
                profile = QWebEngineProfile.defaultProfile()
                profile.setHttpUserAgent(_CHROME_UA)
            except Exception:
                profile = None
        try:
            if profile is not None:
                page = _make_connect_web_page(
                    profile, self._view, self._emit_external_oauth
                )
                self._view.setPage(page)
                self._connect_page = page
            else:
                self._connect_page = None
        except Exception:
            self._connect_page = None

        self._view.urlChanged.connect(self._on_url)
        self._view.titleChanged.connect(self._on_title)
        self._view.loadFinished.connect(self._on_loaded)
        # Ctrl+wheel zoom (Chromium focus often eats Widget shortcuts)
        self._view.installEventFilter(self)

        self._find_bar = self._build_find_bar()
        self._find_bar.hide()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._find_bar, 0)
        lay.addWidget(self._view, 1)

        self._install_browser_shortcuts()
        self._apply_zoom()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(960, 560)

    def _build_find_bar(self) -> QWidget:
        bar = QWidget(self)
        bar.setObjectName("webFindBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(6)
        lab = QLabel("찾기")
        lab.setStyleSheet("color:#4a453b;font-size:12px;border:none;")
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("페이지에서 찾기")
        self._find_edit.setClearButtonEnabled(True)
        self._find_edit.returnPressed.connect(self._find_next)
        self._find_edit.textChanged.connect(self._find_on_type)
        btn_prev = QPushButton("이전")
        btn_prev.setObjectName("btnSecondary")
        btn_prev.clicked.connect(self._find_prev)
        btn_next = QPushButton("다음")
        btn_next.setObjectName("btnSecondary")
        btn_next.clicked.connect(self._find_next)
        btn_close = QPushButton("닫기")
        btn_close.setObjectName("btnGhost")
        btn_close.clicked.connect(self._hide_find)
        self._find_status = QLabel("")
        self._find_status.setStyleSheet(
            "color:#6d675c;font-size:11.5px;border:none;"
        )
        row.addWidget(lab)
        row.addWidget(self._find_edit, 1)
        row.addWidget(btn_prev)
        row.addWidget(btn_next)
        row.addWidget(self._find_status)
        row.addWidget(btn_close)
        return bar

    def _install_browser_shortcuts(self) -> None:
        """Ctrl+/- / 0 / F — WindowShortcut so they work while Chromium has focus."""

        def _add(seq: QKeySequence | str, slot) -> None:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)

        # Zoom in: Ctrl++ and Ctrl+= (US keyboard)
        _add(QKeySequence.StandardKey.ZoomIn, self._zoom_in)
        _add("Ctrl+=", self._zoom_in)
        _add(QKeySequence.StandardKey.ZoomOut, self._zoom_out)
        _add("Ctrl+0", self._zoom_reset)
        _add(QKeySequence.StandardKey.Find, self._show_find)
        # Esc closes find only — enabled while the bar is open
        self._esc_find = QShortcut(QKeySequence("Escape"), self)
        self._esc_find.setContext(Qt.ShortcutContext.WindowShortcut)
        self._esc_find.setEnabled(False)
        self._esc_find.activated.connect(self._hide_find)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if obj is self._view and event.type() == QEvent.Type.Wheel:
            from PySide6.QtGui import QWheelEvent

            we = event
            if isinstance(we, QWheelEvent) and (
                we.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                delta = we.angleDelta().y()
                if delta > 0:
                    self._zoom_in()
                elif delta < 0:
                    self._zoom_out()
                return True
        return super().eventFilter(obj, event)

    def _apply_zoom(self) -> None:
        self._zoom = max(_ZOOM_MIN, min(_ZOOM_MAX, self._zoom))
        try:
            self._view.setZoomFactor(self._zoom)
        except Exception:
            pass

    def _zoom_in(self) -> None:
        self._zoom = round(self._zoom + _ZOOM_STEP, 2)
        self._apply_zoom()

    def _zoom_out(self) -> None:
        self._zoom = round(self._zoom - _ZOOM_STEP, 2)
        self._apply_zoom()

    def _zoom_reset(self) -> None:
        self._zoom = _ZOOM_DEFAULT
        self._apply_zoom()

    def _show_find(self) -> None:
        self._find_bar.show()
        self._esc_find.setEnabled(True)
        self._find_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._find_edit.selectAll()

    def _hide_find(self) -> None:
        self._find_bar.hide()
        self._esc_find.setEnabled(False)
        try:
            self._view.page().findText("")
        except Exception:
            pass
        self._find_status.setText("")
        self._view.setFocus(Qt.FocusReason.OtherFocusReason)

    def _find_on_type(self, _text: str) -> None:
        self._find_next()

    def _find_next(self) -> None:
        self._run_find(backward=False)

    def _find_prev(self) -> None:
        self._run_find(backward=True)

    def _run_find(self, *, backward: bool) -> None:
        from PySide6.QtWebEngineCore import QWebEnginePage

        query = (self._find_edit.text() or "").strip()
        if not query:
            self._find_status.setText("")
            try:
                self._view.page().findText("")
            except Exception:
                pass
            return

        def _done(found: bool) -> None:
            self._find_status.setText("찾음" if found else "없음")

        try:
            if backward:
                self._view.page().findText(
                    query, QWebEnginePage.FindFlag.FindBackward, _done
                )
            else:
                self._view.page().findText(query, resultCallback=_done)
        except TypeError:
            try:
                if backward:
                    self._view.page().findText(
                        query, QWebEnginePage.FindFlag.FindBackward
                    )
                else:
                    self._view.page().findText(query)
                self._find_status.setText("")
            except Exception:
                self._find_status.setText("찾기 불가")
        except Exception:
            self._find_status.setText("찾기 불가")

    @property
    def stage(self) -> GitHubPageStage:
        return self._stage

    @property
    def reached(self) -> set[GitHubPageStage]:
        return set(self._reached)

    def load_url(self, url: str) -> None:
        self._oauth_hand_off_done = False
        page = getattr(self, "_connect_page", None)
        if page is not None and hasattr(page, "reset_handoff"):
            page.reset_handoff()
        self._view.setUrl(QUrl(url))

    def open_external_fallback(self, url: str) -> None:
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(url))

    def _emit_external_oauth(self, url: str) -> None:
        if self._oauth_hand_off_done:
            return
        self._oauth_hand_off_done = True
        self.external_oauth_needed.emit(url or "https://accounts.google.com/")

    def _snapshot(self) -> PageSnapshot:
        url = self._view.url().toString()
        title = self._view.title() or ""
        return PageSnapshot(url=url, title=title, html="")

    def _apply_stage(self, stage: GitHubPageStage) -> None:
        if stage != GitHubPageStage.UNKNOWN:
            self._reached.add(stage)
            # Opening classic-new implies past login for checklist UX
            if stage in (
                GitHubPageStage.TOKEN_CLASSIC_NEW,
                GitHubPageStage.TOKEN_FINE_NEW,
                GitHubPageStage.TOKEN_ISSUED,
            ):
                self._reached.add(GitHubPageStage.LOGIN)
        if stage == self._stage:
            return
        self._stage = stage
        self.stage_changed.emit(stage)
        if stage == GitHubPageStage.TOKEN_ISSUED:
            self._try_scrape_token()

    def _refresh_stage(self, html: str = "") -> None:
        snap = self._snapshot()
        if html:
            snap = PageSnapshot(url=snap.url, title=snap.title, html=html)
        self._apply_stage(detect_github_page_stage(snap))

    @Slot(QUrl)
    def _on_url(self, url: QUrl) -> None:
        text = url.toString()
        self.url_changed.emit(text)
        if is_google_oauth_url(text):
            self._emit_external_oauth(text)
            return
        self._refresh_stage()

    @Slot(str)
    def _on_title(self, title: str) -> None:
        if looks_like_insecure_browser_block(title, ""):
            self._emit_external_oauth(self._view.url().toString())
            return
        self._refresh_stage()

    @Slot(bool)
    def _on_loaded(self, ok: bool) -> None:
        if not ok:
            self.load_failed.emit("페이지를 불러오지 못했습니다.")
            return
        self._refresh_stage()
        # HTML helps TOKEN_ISSUED / 2FA when URL is ambiguous
        try:
            self._view.page().toHtml(self._on_html)
        except Exception:
            pass

    def _on_html(self, html: str) -> None:
        html = html or ""
        title = self._view.title() or ""
        if looks_like_insecure_browser_block(title, html) or is_google_oauth_url(
            self._view.url().toString()
        ):
            self._emit_external_oauth(self._view.url().toString())
            return
        self._refresh_stage(html=html)

    def _try_scrape_token(self) -> None:
        def _done(result: object) -> None:
            text = (str(result) if result is not None else "").strip()
            if not text or text == self._last_token:
                return
            if not (
                text.startswith("ghp_")
                or text.startswith("github_pat_")
                or text.startswith("gho_")
            ):
                return
            self._last_token = text
            self.token_found.emit(text)

        try:
            self._view.page().runJavaScript(_JS_FIND_TOKEN, _done)
        except Exception:
            pass
