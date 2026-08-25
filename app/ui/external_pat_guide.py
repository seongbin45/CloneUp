"""Small floating guide after SSO is handed off to the OS browser.

User may sign in with password, passkey, Apple, or Google in a real browser.
This dialog:
- shows a method-neutral checklist
- every 3s reads omnibox + accessible UI text (UI Automation, optional)
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
from app.util.browser_address import (
    browser_address_available,
    detect_signin_method,
    is_apple_signin_url,
    looks_like_passkey_os_prompt,
    read_browser_page_sample,
)

_GUIDE_OPACITY = 0.90
_ADDR_POLL_MS = 3000
_CLIP_POLL_MS = 500
_TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")
_GITHUB_LOGIN = "https://github.com/login"
# classic repo — same default as connect wizard (새 저장소 만들기용)
_PAT_CREATE_URL = (
    "https://github.com/settings/tokens/new"
    "?scopes=repo&description=CloneUp"
)

# Method-neutral checklist — do not force Google-only wording
_CHECKLIST = (
    "GitHub 로그인 (비밀번호·패스키·Apple·Google)",
    "로그인 완료 확인",
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
) -> tuple[str, int | None, dict]:
    """
    Cross-check omnibox URL + accessible UI text → (kind, index, meta).

    kind:
      - ``rejected``: Google insecure-browser / signin rejected (NOT success)
      - ``logged_out``: logout URL **or** github.com with Sign in/Sign up UI
        (same URL when logged in vs out — UI text cross-check) — reset progress
      - ``current``: sign-in in progress (password / passkey / Apple / Google)
      - ``reached``: past login (sticky progress OK)
      - ``unknown``: cannot classify

    meta includes ``method`` (google_blocked|google|apple|passkey|…) and
    optional ``analysis`` for Google block details.
    """
    from app.util.browser_address import analyze_google_signin_block

    u = (url or "").strip()
    method = detect_signin_method(
        u, window_title=window_title, ui_text=ui_text
    )
    analysis = analyze_google_signin_block(
        u, window_title=window_title, ui_text=ui_text
    )
    meta: dict = {"method": method, "analysis": analysis}

    if method == "google_blocked" or analysis.blocked:
        return ("rejected", 0, meta)

    # /logout URL, or github.com showing Sign in / Sign up (logged-out home)
    if method in ("github_logout", "github_logged_out"):
        return ("logged_out", 0, meta)

    # Passkey OS sheet or Apple / Google / GitHub login form → still signing in
    if method in ("passkey", "apple", "google", "github_login"):
        return ("current", 0, meta)

    if not u and not window_title:
        return ("unknown", None, meta)

    st = detect_github_page_stage(PageSnapshot(url=u))
    if st == GitHubPageStage.TOKEN_ISSUED:
        return ("reached", 3, meta)
    if st in (
        GitHubPageStage.TOKEN_CLASSIC_NEW,
        GitHubPageStage.TOKEN_FINE_NEW,
        GitHubPageStage.TOKEN_CLASSIC_LIST,
        GitHubPageStage.TOKEN_FINE_LIST,
    ):
        return ("reached", 2, meta)
    if st == GitHubPageStage.AUTH_2FA:
        return ("reached", 1, meta)
    if st == GitHubPageStage.LOGIN:
        return ("current", 0, meta)

    try:
        from urllib.parse import urlparse

        host = (urlparse(u).hostname or "").lower()
        path = (urlparse(u).path or "").lower()
    except Exception:
        host, path = "", ""
    if host == "github.com" or host.endswith(".github.com"):
        if path == "/logout" or path.startswith("/logout"):
            return ("logged_out", 0, meta)
        if path.startswith("/login"):
            return ("current", 0, meta)
        return ("reached", 1, meta)

    # Apple/passkey already handled; leftover non-github hosts
    if is_apple_signin_url(u) or looks_like_passkey_os_prompt(window_title, ui_text):
        return ("current", 0, meta)
    return ("unknown", None, meta)


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


def checklist_row_label(
    index: int,
    *,
    reached: int,
    current: int | None,
    google_rejected: bool,
) -> str:
    """Pure label text for checklist row — used by UI and unit tests."""
    base = _CHECKLIST[index]
    done = index <= reached
    if google_rejected and index == 0 and not done:
        return f"!  {base} — Google 막힘"
    if done:
        return f"✓  {base}"
    if current is not None and index == current:
        return f"→  {base}"
    return f"○  {base}"


def _method_guide_copy(method: str) -> tuple[str, str, str]:
    """title, lead, verify hint for the detected sign-in method."""
    if method == "google_blocked":
        return (
            "Google 로그인이 막혔어요",
            "브라우저에 로그인 오류가 보입니다. GitHub 로그인을 다시 연 뒤 다른 방법(패스키·Apple·비밀번호)을 써도 됩니다.",
            "검증: Google 거절 확인 — 완료로 세지 않음",
        )
    if method == "github_logout":
        return (
            "로그아웃되었어요",
            "GitHub에서 로그아웃했습니다. 다시 로그인한 뒤 키를 만들어 주세요.",
            "검증: /logout 확인 — 진행 상태 초기화",
        )
    if method == "github_logged_out":
        return (
            "로그인이 필요해요",
            "Sign in / Sign up이 보입니다. 아직 로그인되지 않았어요. 로그인한 뒤 키를 만들어 주세요.",
            "검증: Sign in·Sign up UI — 진행 상태 초기화",
        )
    if method == "apple":
        return (
            "Apple로 로그인 중",
            "Apple 로그인 화면입니다. 안내에 따라 계속하세요. 끝나면 GitHub으로 돌아옵니다.",
            "검증: Apple 로그인 화면 — 진행 중",
        )
    if method == "passkey":
        return (
            "패스키 확인 중",
            "Windows 패스키 창입니다. 휴대폰 QR 또는 이 기기에서 확인하세요.",
            "검증: 패스키(OS) 창 — 진행 중",
        )
    if method == "google":
        return (
            "Google로 로그인 중",
            "Google 로그인 화면입니다. 완료되면 GitHub으로 돌아갑니다.",
            "검증: Google 로그인 화면 — 진행 중",
        )
    if method == "github_login":
        return (
            "GitHub에 로그인하세요",
            "비밀번호·패스키·Apple·Google 중 편한 방법을 고르세요.",
            "검증: GitHub 로그인 화면 — 아직 완료 아님",
        )
    return (
        "브라우저에서 이어서 하세요",
        "열린 브라우저에서 로그인한 다음, 키를 만들어 복사해 주세요.",
        "검증: 주소를 확인하는 중…",
    )


def progress_guide_for_reached(idx: int) -> tuple[str, str, str]:
    """
    title, lead, verify for post-login checklist progress (idx 1..3).

    idx 1 = logged in on github.com (not yet on token pages) → nudge to create key.
    idx 2 = token list / new form.
    idx 3 = token issued / copy.
    """
    if idx <= 1:
        return (
            "로그인됐어요. 키를 만들어요",
            "키 만들기 페이지로 안내합니다. Generate token을 누르세요.",
            "검증: 로그인 완료 — 키 만들기로 이동",
        )
    if idx == 2:
        return (
            "키를 만들어 주세요",
            "repo가 체크돼 있어요. Generate token을 누르세요.",
            "검증: 키 만들기 화면 확인됨",
        )
    return (
        "키를 복사해 주세요",
        "복사하면 아래 칸에 들어옵니다. 「연결」을 누르세요.",
        "검증: 키 발급/복사 화면 확인됨",
    )


def should_auto_open_token_page(
    *,
    kind: str,
    idx: int | None,
    already_opened: bool,
) -> bool:
    """Open tokens/new once when login is confirmed on github.com (not yet on PAT pages)."""
    if already_opened:
        return False
    return kind == "reached" and idx == 1


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
        self._token_nav_opened = False  # auto-open tokens/new at most once
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
            "앱 안 WebView에서 Google이 막히면 여기로 옵니다. "
            "비밀번호·패스키·Apple·Google 모두 브라우저에서 쓸 수 있어요."
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

        self._btn_open_tokens = QPushButton("키 만들기 페이지 열기")
        self._btn_open_tokens.setToolTip(
            "로그인 후 classic 키(repo) 만들기 페이지를 엽니다."
        )
        self._btn_open_tokens.clicked.connect(self._on_open_token_page_clicked)
        self._btn_open_tokens.hide()

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
        root.addWidget(self._btn_open_tokens)
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
            text = checklist_row_label(
                i,
                reached=self._reached,
                current=self._current,
                google_rejected=self._google_rejected,
            )
            lab.setText(text)
            if text.startswith("!"):
                lab.setStyleSheet(
                    "font-size:12.5px;color:#8a6d12;font-weight:600;border:none;"
                )
            elif text.startswith("✓") or text.startswith("→"):
                lab.setStyleSheet(
                    "font-size:12.5px;color:#1f6f5c;font-weight:600;border:none;"
                )
            else:
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

    def _show_google_rejected(self, url: str, meta: dict | None = None) -> None:
        self._google_rejected = True
        self._current = None  # avoid progress marker winning over "! 막힘"
        self._refresh_checklist_labels()
        title, lead, verify_fallback = _method_guide_copy("google_blocked")
        self._title.setText(title)
        self._lead.setText(lead)
        analysis = (meta or {}).get("analysis")
        reasons: list[str] = []
        snippets: list[str] = []
        if analysis is not None:
            reasons = list(getattr(analysis, "reasons", []) or [])
            snippets = list(getattr(analysis, "matched_snippets", []) or [])
        verify = "검증: " + (" · ".join(reasons) if reasons else verify_fallback)
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
            "Google이 막혀도 패스키·Apple·비밀번호로 로그인할 수 있어요. "
            "「GitHub 로그인 다시 열기」를 누르세요."
        )
        self._btn_reopen.show()
        self.adjustSize()
        self._place_bottom_right()

    def _apply_method_copy(self, method: str) -> None:
        title, lead, verify = _method_guide_copy(method)
        self._title.setText(title)
        self._lead.setText(lead)
        self._verify_lab.setText(verify)
        self._verify_lab.setStyleSheet(
            "font-size:11.5px;color:#6d675c;border:none;"
        )

    def _apply_progress_copy(self, idx: int) -> None:
        title, lead, verify = progress_guide_for_reached(idx)
        self._title.setText(title)
        self._lead.setText(lead)
        self._verify_lab.setText(verify)
        self._verify_lab.setStyleSheet(
            "font-size:11.5px;color:#1f6f5c;border:none;"
        )

    def _clear_google_rejected_banner(self) -> None:
        if not self._google_rejected:
            return
        self._google_rejected = False
        self._btn_reopen.hide()
        self._status.setText("")
        self._verify_lab.setStyleSheet(
            "font-size:11.5px;color:#6d675c;border:none;"
        )

    def _open_token_create_page(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(_PAT_CREATE_URL))
        self._token_nav_opened = True

    def _on_open_token_page_clicked(self) -> None:
        self._open_token_create_page()
        self._set_current(2)
        self._apply_progress_copy(1)
        self._status.setStyleSheet(
            "font-size:11.5px;color:#1f6f5c;border:none;"
        )
        self._status.setText(
            "브라우저에서 Generate token을 누른 뒤 키를 복사하세요."
        )

    def _reopen_github_login(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(_GITHUB_LOGIN))
        self._clear_google_rejected_banner()
        self._btn_open_tokens.hide()
        self._set_current(0)
        self._apply_method_copy("github_login")
        self._status.setText(
            "비밀번호·패스키·Apple·Google 중 편한 방법을 고르세요."
        )

    def _poll_address(self) -> None:
        if self._done:
            return
        sample = read_browser_page_sample()
        if sample is None or not (
            sample.url or sample.window_title or sample.ui_text
        ):
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

        kind, idx, meta = classify_browser_sample(
            url,
            window_title=sample.window_title,
            ui_text=sample.ui_text,
        )
        method = str((meta or {}).get("method") or "other")

        if kind == "rejected":
            self._show_google_rejected(url, meta)
            return

        if kind == "logged_out":
            # User signed out (or logged-out github.com with Sign in/up) —
            # wipe sticky progress so old ✓ marks disappear
            self._clear_google_rejected_banner()
            self._reached = -1
            self._current = 0
            self._token_nav_opened = False
            self._btn_open_tokens.hide()
            self._refresh_checklist_labels()
            copy_method = (
                method
                if method in ("github_logout", "github_logged_out")
                else "github_logout"
            )
            self._apply_method_copy(copy_method)
            self._btn_reopen.show()
            self._status.setStyleSheet(
                "font-size:11.5px;color:#8a6d12;border:none;"
            )
            self._status.setText(
                "다시 로그인한 뒤 키를 만들어 주세요. "
                "「GitHub 로그인 다시 열기」를 눌러도 됩니다."
            )
            self.adjustSize()
            self._place_bottom_right()
            return

        if kind == "current" and idx is not None:
            self._clear_google_rejected_banner()
            self._btn_open_tokens.hide()
            self._set_current(idx)
            self._apply_method_copy(method)
            return

        if kind == "reached" and idx is not None:
            self._clear_google_rejected_banner()
            self._btn_reopen.hide()
            self._mark_reached(idx)
            self._apply_progress_copy(idx)

            if idx == 1:
                # Logged in on github.com — guide toward classic token create
                self._set_current(2)
                self._btn_open_tokens.show()
                if should_auto_open_token_page(
                    kind=kind,
                    idx=idx,
                    already_opened=self._token_nav_opened,
                ):
                    self._open_token_create_page()
                    self._status.setStyleSheet(
                        "font-size:11.5px;color:#1f6f5c;border:none;"
                    )
                    self._status.setText(
                        "키 만들기 페이지를 열었어요. "
                        "Generate token → 복사 → 아래에 붙여 넣으세요."
                    )
                else:
                    self._status.setStyleSheet(
                        "font-size:11.5px;color:#1f6f5c;border:none;"
                    )
                    self._status.setText(
                        "「키 만들기 페이지 열기」로 다시 열 수 있어요."
                    )
            elif idx == 2:
                self._set_current(2)
                self._btn_open_tokens.show()
                self._status.setStyleSheet(
                    "font-size:11.5px;color:#1f6f5c;border:none;"
                )
                self._status.setText(
                    "Generate token을 누른 뒤 나온 키를 복사하세요."
                )
            else:
                # idx == 3 — issued / ready to paste
                self._current = None
                self._refresh_checklist_labels()
                self._btn_open_tokens.hide()
                self._status.setStyleSheet(
                    "font-size:11.5px;color:#1f6f5c;border:none;"
                )
                self._status.setText(
                    "키를 복사하면 아래 칸에 들어옵니다. 「연결」을 누르세요."
                )
            self.adjustSize()
            self._place_bottom_right()
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
        self._btn_open_tokens.hide()
        self._mark_reached(3)
        self._apply_progress_copy(3)
        self._status.setStyleSheet(
            "font-size:11.5px;color:#1f6f5c;border:none;"
        )
        self._status.setText("키를 인식했어요. 「연결」을 누르세요.")
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
