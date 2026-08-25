"""Small floating guide after Google SSO is handed off to the OS browser.

User finishes Google + PAT create in Chrome/Edge. This dialog:
- shows a short checklist of expected steps
- every 3s reads the browser *address bar only* (UI Automation, optional)
- watches the clipboard for a PAT
- lets the user paste / connect into Windows keyring via the parent wizard
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.auth.github_page_stage import GitHubPageStage, PageSnapshot, detect_github_page_stage
from app.ui.connect_webview import is_google_oauth_url
from app.util.browser_address import (
    analyze_google_signin_block,
    browser_address_available,
    read_browser_page_sample,
)

_GUIDE_OPACITY = 0.90
_ADDR_POLL_MS = 3000
_CLIP_POLL_MS = 500
_TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")
_GITHUB_LOGIN = "https://github.com/login"

# Friendly checklist (high-school plain language)
_CHECKLIST = (
    "브라우저에서 Google로 로그인",
    "GitHub 화면으로 돌아오기",
    "Generate new token 으로 키 만들기",
    "키 복사하기",
)


def _looks_like_token(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 20 or " " in t or "\n" in t:
        return False
    return any(t.startswith(p) for p in _TOKEN_PREFIXES)


def classify_browser_sample(
    url: str,
    *,
    window_title: str = "",
    ui_text: str = "",
) -> tuple[str, int | None, object | None]:
    """
    Cross-check omnibox URL + accessible UI text → (kind, index, analysis).

    kind:
      - ``rejected``: Google insecure-browser / signin rejected (NOT success)
      - ``current``: this step is in progress (do not mark prior as done alone)
      - ``reached``: user has reached this step (sticky progress OK)
      - ``unknown``: cannot classify
    """
    u = (url or "").strip()
    analysis = analyze_google_signin_block(
        u, window_title=window_title, ui_text=ui_text
    )
    if analysis.blocked:
        return ("rejected", 0, analysis)
    if not u:
        return ("unknown", None, analysis)
    if is_google_oauth_url(u):
        return ("current", 0, analysis)
    st = detect_github_page_stage(PageSnapshot(url=u))
    if st == GitHubPageStage.TOKEN_ISSUED:
        return ("reached", 3, analysis)
    if st in (
        GitHubPageStage.TOKEN_CLASSIC_NEW,
        GitHubPageStage.TOKEN_FINE_NEW,
        GitHubPageStage.TOKEN_CLASSIC_LIST,
        GitHubPageStage.TOKEN_FINE_LIST,
    ):
        return ("reached", 2, analysis)
    if st in (GitHubPageStage.LOGIN, GitHubPageStage.AUTH_2FA):
        return ("reached", 1, analysis)
    try:
        from urllib.parse import urlparse

        host = (urlparse(u).hostname or "").lower()
    except Exception:
        host = ""
    if host == "github.com" or host.endswith(".github.com"):
        return ("reached", 1, analysis)
    return ("unknown", None, analysis)


def classify_browser_url(url: str) -> tuple[str, int | None]:
    """URL-only classify (tests / callers without a full sample)."""
    kind, idx, _a = classify_browser_sample(url)
    return (kind, idx)


def checklist_index_for_url(url: str) -> int | None:
    """Backward-compatible helper — rejected Google does **not** count as step 0 done."""
    kind, idx = classify_browser_url(url)
    if kind == "rejected":
        return None
    return idx


class ExternalBrowserPatGuide(QDialog):
    """Bottom-right translucent helper: checklist + paste + connect."""

    token_accepted = Signal(str)
    cancelled = Signal()

    def __init__(self, anchor: QWidget | None = None) -> None:
        super().__init__(None)
        self._anchor = anchor
        self._clip_seen = ""
        self._done = False
        self._reached = -1  # highest checklist index marked done
        self._current: int | None = None  # in-progress step (●)
        self._google_rejected = False
        self._check_labels: list[QLabel] = []
        self._last_url = ""

        self.setWindowTitle("CloneUp — 브라우저 안내")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowOpacity(_GUIDE_OPACITY)
        self.setMinimumWidth(380)
        self.setMaximumWidth(440)

        self._title = QLabel("브라우저에서 이어서 하세요")
        self._title.setStyleSheet(
            "font-size:15px;font-weight:600;color:#232019;border:none;"
        )
        self._title.setWordWrap(True)

        self._lead = QLabel(
            "앱 안에서는 Google 로그인이 막혀 있어요. "
            "열린 브라우저에서 로그인한 다음, 키를 만들어 복사해 주세요."
        )
        self._lead.setWordWrap(True)
        self._lead.setStyleSheet("font-size:12.5px;color:#4a453b;border:none;")

        self._url_lab = QLabel("주소: (아직 읽지 못함)")
        self._url_lab.setWordWrap(True)
        self._url_lab.setStyleSheet(
            "font-size:11px;color:#6d675c;border:none;"
            "font-family: Consolas, 'IBM Plex Mono', monospace;"
        )
        if not browser_address_available():
            self._url_lab.setText(
                "주소: (uiautomation 없음 — pip install uiautomation)"
            )

        self._verify_lab = QLabel("검증: 주소를 확인하는 중…")
        self._verify_lab.setWordWrap(True)
        self._verify_lab.setStyleSheet(
            "font-size:11.5px;color:#6d675c;border:none;"
        )

        steps_box = QWidget()
        steps_lay = QVBoxLayout(steps_box)
        steps_lay.setContentsMargins(0, 2, 0, 2)
        steps_lay.setSpacing(3)
        hint = QLabel("할 일")
        hint.setStyleSheet(
            "font-size:12px;font-weight:600;color:#3d382f;border:none;"
        )
        steps_lay.addWidget(hint)
        for label in _CHECKLIST:
            row = QLabel(f"○  {label}")
            row.setStyleSheet("font-size:12.5px;color:#4a453b;border:none;")
            row.setWordWrap(True)
            self._check_labels.append(row)
            steps_lay.addWidget(row)

        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("키가 여기 들어오거나, 직접 붙여 넣으세요")
        self._edit.setClearButtonEnabled(True)
        self._edit.setMinimumHeight(36)
        self._edit.textChanged.connect(self._on_text)

        btn_paste = QPushButton("붙여넣기")
        btn_paste.clicked.connect(self._paste_clipboard)
        self._btn_toggle = QPushButton("보기")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.toggled.connect(self._on_toggle_visible)

        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        key_row.addWidget(self._edit, 1)
        key_row.addWidget(btn_paste)
        key_row.addWidget(self._btn_toggle)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size:11.5px;color:#1f6f5c;border:none;")

        self._btn_reopen = QPushButton("GitHub 로그인 다시 열기")
        self._btn_reopen.setToolTip(
            "Google 오류 화면이면 이 버튼으로 GitHub 로그인을 새로 여세요."
        )
        self._btn_reopen.clicked.connect(self._reopen_github_login)
        self._btn_reopen.hide()

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self._on_cancel)
        self._btn_connect = QPushButton("연결")
        self._btn_connect.setEnabled(False)
        self._btn_connect.setDefault(True)
        self._btn_connect.clicked.connect(self._on_connect)

        nav = QHBoxLayout()
        nav.addWidget(btn_cancel)
        nav.addStretch(1)
        nav.addWidget(self._btn_connect)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)
        root.addWidget(self._title)
        root.addWidget(self._lead)
        root.addWidget(self._url_lab)
        root.addWidget(self._verify_lab)
        root.addWidget(steps_box)
        root.addWidget(self._btn_reopen)
        root.addLayout(key_row)
        root.addWidget(self._status)
        root.addLayout(nav)

        self._clip_timer = QTimer(self)
        self._clip_timer.setInterval(_CLIP_POLL_MS)
        self._clip_timer.timeout.connect(self._poll_clipboard)
        self._clip_timer.start()

        self._addr_timer = QTimer(self)
        self._addr_timer.setInterval(_ADDR_POLL_MS)
        self._addr_timer.timeout.connect(self._poll_address)
        self._addr_timer.start()
        # First read soon so the user sees feedback quickly
        QTimer.singleShot(400, self._poll_address)

        self._place_bottom_right()

    def _place_bottom_right(self) -> None:
        margin = 24
        self.adjustSize()
        try:
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

    def _on_toggle_visible(self, on: bool) -> None:
        self._edit.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        )
        self._btn_toggle.setText("숨기기" if on else "보기")

    def _paste_clipboard(self) -> None:
        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        text = (clip.text() or "").strip()
        if text:
            self._edit.setText(text)

    def _on_text(self, text: str) -> None:
        has = bool((text or "").strip())
        self._btn_connect.setEnabled(has)
        if _looks_like_token(text or ""):
            self._google_rejected = False
            self._btn_reopen.hide()
            self._mark_reached(3)
            self._status.setStyleSheet(
                "font-size:11.5px;color:#1f6f5c;border:none;"
            )
            self._status.setText("키를 인식했어요. 「연결」을 누르세요.")
        elif has:
            self._status.setText("")

    def _refresh_checklist_labels(self) -> None:
        for i, lab in enumerate(self._check_labels):
            done = i <= self._reached
            cur = self._current is not None and i == self._current and not done
            if done:
                lab.setText(f"✓  {_CHECKLIST[i]}")
                lab.setStyleSheet(
                    "font-size:12.5px;color:#1f6f5c;font-weight:600;border:none;"
                )
            elif cur:
                lab.setText(f"●  {_CHECKLIST[i]}")
                lab.setStyleSheet(
                    "font-size:12.5px;color:#1f6f5c;font-weight:600;border:none;"
                )
            elif self._google_rejected and i == 0:
                lab.setText(f"✗  {_CHECKLIST[i]} (막힘)")
                lab.setStyleSheet(
                    "font-size:12.5px;color:#8a6d12;font-weight:600;border:none;"
                )
            else:
                lab.setText(f"○  {_CHECKLIST[i]}")
                lab.setStyleSheet(
                    "font-size:12.5px;color:#8b8477;border:none;"
                )

    def _mark_reached(self, index: int) -> None:
        if index < 0:
            return
        self._reached = max(self._reached, index)
        self._current = None
        self._refresh_checklist_labels()

    def _set_current(self, index: int) -> None:
        self._current = index
        self._refresh_checklist_labels()

    def _show_google_rejected(self, url: str, analysis: object | None = None) -> None:
        self._google_rejected = True
        self._current = 0
        # Do NOT mark step 0 as done — cross-check failed
        self._refresh_checklist_labels()
        self._title.setText("Google 로그인이 막혔어요")
        self._lead.setText(
            "브라우저에 로그인 오류가 보입니다. "
            "아래에서 GitHub 로그인을 다시 연 뒤, Google을 한 번 더 시도하세요."
        )
        reasons: list[str] = []
        snippets: list[str] = []
        if analysis is not None:
            reasons = list(getattr(analysis, "reasons", []) or [])
            snippets = list(getattr(analysis, "matched_snippets", []) or [])
        verify = "검증: " + (" · ".join(reasons) if reasons else "Google 거절 감지")
        if snippets:
            verify += " | 문구: " + snippets[0][:50]
        self._verify_lab.setText(verify)
        self._verify_lab.setStyleSheet(
            "font-size:11.5px;color:#8a6d12;border:none;"
        )
        self._status.setStyleSheet(
            "font-size:11.5px;color:#8a6d12;border:none;"
        )
        self._status.setText(
            "같은 오류 화면이면 계속 실패합니다. 「GitHub 로그인 다시 열기」를 누르세요."
        )
        self._btn_reopen.show()
        self.adjustSize()
        self._place_bottom_right()

    def _clear_google_rejected_banner(self) -> None:
        if not self._google_rejected:
            return
        self._google_rejected = False
        self._btn_reopen.hide()
        self._title.setText("브라우저에서 이어서 하세요")
        self._lead.setText(
            "앱 안에서는 Google 로그인이 막혀 있어요. "
            "열린 브라우저에서 로그인한 다음, 키를 만들어 복사해 주세요."
        )
        self._verify_lab.setStyleSheet(
            "font-size:11.5px;color:#6d675c;border:none;"
        )

    def _reopen_github_login(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(_GITHUB_LOGIN))
        self._clear_google_rejected_banner()
        self._set_current(0)
        self._verify_lab.setText(
            "검증: GitHub 로그인을 새로 열었습니다. Google 버튼을 다시 눌러 보세요."
        )
        self._status.setText("")

    def _poll_address(self) -> None:
        if self._done:
            return
        sample = read_browser_page_sample()
        if sample is None or not (sample.url or sample.window_title):
            self._verify_lab.setText(
                "검증: 브라우저 주소/텍스트를 아직 읽지 못함"
            )
            return
        url = sample.url or ""
        if url and url != self._last_url:
            self._last_url = url
            shown = url if len(url) <= 64 else url[:61] + "…"
            self._url_lab.setText(f"주소: {shown}")
        elif not url and sample.window_title:
            self._url_lab.setText(f"창: {sample.window_title[:64]}")

        kind, idx, analysis = classify_browser_sample(
            url,
            window_title=sample.window_title,
            ui_text=sample.ui_text,
        )
        if kind == "rejected":
            self._show_google_rejected(url, analysis)
            return

        if kind == "current" and idx is not None:
            # Google sign-in in progress — not success yet
            self._clear_google_rejected_banner()
            self._set_current(idx)
            extra = ""
            if analysis is not None and getattr(analysis, "reasons", None):
                extra = " · " + analysis.reasons[-1]
            self._verify_lab.setText(
                "검증: Google 로그인 진행 중 — 완료로 치지 않음" + extra
            )
            self._verify_lab.setStyleSheet(
                "font-size:11.5px;color:#6d675c;border:none;"
            )
            return

        if kind == "reached" and idx is not None:
            self._clear_google_rejected_banner()
            # Reaching GitHub means Google step is behind us
            if idx >= 1:
                self._reached = max(self._reached, 0)
            self._mark_reached(idx)
            labels = (
                "Google 로그인 중",
                "GitHub 도착",
                "키 만들기 화면",
                "키 발급/복사 화면",
            )
            self._verify_lab.setText(f"검증: {labels[idx]} 확인됨")
            self._verify_lab.setStyleSheet(
                "font-size:11.5px;color:#1f6f5c;border:none;"
            )
            return

        self._verify_lab.setText("검증: 주소를 분류하지 못함 — 체크리스트 유지")

    def _poll_clipboard(self) -> None:
        if self._done:
            return
        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        text = (clip.text() or "").strip()
        if not _looks_like_token(text) or text == self._clip_seen:
            return
        self._clip_seen = text
        self._edit.setText(text)
        self._clear_google_rejected_banner()
        self._mark_reached(3)
        self.raise_()
        self.activateWindow()

    def _on_connect(self) -> None:
        raw = (self._edit.text() or "").strip()
        if not _looks_like_token(raw):
            self._status.setStyleSheet(
                "font-size:11.5px;color:#8a6d12;border:none;"
            )
            self._status.setText(
                "키 형식이 아니에요. 브라우저에서 키 전체를 복사했는지 확인하세요."
            )
            return
        self._stop_timers()
        self._done = True
        self.token_accepted.emit(raw)
        self.accept()

    def _on_cancel(self) -> None:
        self._stop_timers()
        self._done = True
        self.cancelled.emit()
        self.reject()

    def _stop_timers(self) -> None:
        if self._clip_timer.isActive():
            self._clip_timer.stop()
        if self._addr_timer.isActive():
            self._addr_timer.stop()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_timers()
        if not self._done:
            self._done = True
            self.cancelled.emit()
        super().closeEvent(event)

    def token(self) -> str:
        return (self._edit.text() or "").strip()
