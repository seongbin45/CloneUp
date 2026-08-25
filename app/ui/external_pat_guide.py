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

from urllib.parse import quote

from app.auth.github_page_stage import GitHubPageStage, PageSnapshot, detect_github_page_stage
from app.util.browser_address import (
    browser_address_available,
    detect_signin_method,
    extract_visible_pat,
    is_apple_signin_url,
    is_github_flow_family_url,
    looks_like_passkey_os_prompt,
    looks_like_token_issued_banner,
    looks_like_token_note_taken,
    read_browser_page_sample,
    token_create_error_snippets,
)

_GUIDE_OPACITY = 0.90
_ADDR_POLL_MS = 3000
_CLIP_POLL_MS = 500
_TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")
_GITHUB_LOGIN = "https://github.com/login"


def build_pat_create_url(*, note: str | None = None) -> str:
    """classic ``repo`` token form; unique Note avoids 'already been taken'."""
    from datetime import datetime

    n = (note or "").strip() or f"CloneUp-{datetime.now().strftime('%m%d-%H%M')}"
    return (
        "https://github.com/settings/tokens/new"
        f"?scopes=repo&description={quote(n, safe='')}"
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
      - ``token_error``: PAT form flash (e.g. Note has already been taken)
      - ``current``: sign-in in progress (password / passkey / Apple / Google)
      - ``reached``: past login (sticky progress OK)
      - ``away``: browser is off the GitHub-flow family (soft nudge only)
      - ``unknown``: cannot classify (empty sample, etc.)

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

    # PAT Note collision flash — must win over generic token-page "reached"
    if looks_like_token_note_taken(window_title, ui_text, url=u):
        snippets = token_create_error_snippets(window_title, ui_text)
        meta["method"] = "token_note_taken"
        meta["token_error"] = "note_taken"
        meta["error_snippets"] = snippets
        return ("token_error", 2, meta)

    # Visible PAT on /settings/tokens (UIA Name/Value) → ready to connect
    visible = extract_visible_pat(window_title, ui_text)
    if visible:
        meta["method"] = "token_visible"
        meta["visible_pat"] = visible
        return ("reached", 3, meta)
    if looks_like_token_issued_banner(window_title, ui_text):
        meta["method"] = "token_issued_banner"
        return ("reached", 3, meta)

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

    # Apple/passkey already handled above via method; leftover family hosts
    if is_apple_signin_url(u) or looks_like_passkey_os_prompt(window_title, ui_text):
        return ("current", 0, meta)

    # Off-family page (YouTube, news, …) — soft invite back, never force
    if u and not is_github_flow_family_url(
        u, window_title=window_title, ui_text=ui_text
    ):
        meta["method"] = "away"
        return ("away", None, meta)

    return ("unknown", None, meta)


def away_from_flow_guide_copy() -> tuple[str, str, str]:
    """title, lead, verify — soft, non-coercive (user may stay elsewhere)."""
    return (
        "지금은 GitHub 작업 화면이 아니에요",
        "원하시면 마지막 페이지로 돌아가도 됩니다.",
        "검증: GitHub 연계 주소가 아님",
    )


def fallback_return_url(*, reached: int) -> str:
    """When no remembered family URL, suggest a sensible resume target."""
    if reached >= 2:
        return build_pat_create_url()
    if reached >= 1:
        return "https://github.com/"
    return _GITHUB_LOGIN


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
    token_note_taken: bool = False,
) -> str:
    """Pure label text for checklist row — used by UI and unit tests."""
    base = _CHECKLIST[index]
    done = index <= reached
    if google_rejected and index == 0 and not done:
        return f"!  {base} — Google 막힘"
    if token_note_taken and index == 2 and not done:
        return f"!  {base} — Note 이름 중복"
    if done:
        return f"✓  {base}"
    if current is not None and index == current:
        return f"→  {base}"
    return f"○  {base}"


def token_note_error_guide_copy() -> tuple[str, str, str]:
    """title, lead, verify when UIA reads Note-already-taken flash."""
    return (
        "Note 이름이 이미 있어요",
        "Note를 바꾸거나 「다른 이름으로 열기」를 누르세요.",
        "검증: Note has already been taken",
    )


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
        "복사되거나 화면에 보이면 자동으로 연결합니다.",
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
    """Standalone browser-path connect UI (Path B).

    Must not run nested under ConnectGitHubWizard. Main window closes the
    wizard first, then ``exec()`` this dialog alone. 「연결」 accepts with
    ``token()`` — independent of WebView ``_finish``.
    """

    token_accepted = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        anchor: QWidget | None = None,
        *,
        open_login_on_start: bool = False,
    ) -> None:
        super().__init__(None)
        self._anchor = anchor
        self._clip_seen = ""
        self._done = False
        self._token = ""  # set on Connect for token() after exec()
        self._auto_connect_pending = False
        self._reached = -1  # highest checklist index marked done
        self._current: int | None = None  # in-progress step (●)
        self._google_rejected = False
        self._token_note_taken = False  # UIA: Note has already been taken
        self._token_nav_opened = False  # auto-open tokens/new at most once
        self._last_family_url = ""  # last GitHub-flow family URL (soft return)
        self._check_labels: list[QLabel] = []
        self._last_url = ""
        self._open_login_on_start = open_login_on_start

        self.setWindowTitle("CloneUp — 브라우저 안내")
        # Standalone modal — only this connect UI should be up
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
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
            "비밀번호·패스키·Apple·Google 중 편한 방법으로 로그인한 뒤 "
            "키를 만들어 주세요."
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
            "classic 키(repo) 만들기 페이지를 엽니다. "
            "Note 이름이 겹치면 새 이름으로 다시 엽니다."
        )
        self._btn_open_tokens.clicked.connect(self._on_open_token_page_clicked)
        self._btn_open_tokens.hide()

        self._btn_return_flow = QPushButton("마지막으로 열었던 페이지로 돌아가기")
        self._btn_return_flow.setToolTip(
            "직전에 열었던 GitHub·로그인 연계 페이지를 다시 엽니다. "
            "원하지 않으면 누르지 않아도 됩니다."
        )
        self._btn_return_flow.clicked.connect(self._on_return_to_flow_clicked)
        self._btn_return_flow.hide()

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
        root.addWidget(self._btn_return_flow)
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
        if self._open_login_on_start:
            QTimer.singleShot(200, self._reopen_github_login)

        self._place_top_left()

    def _place_top_left(self) -> None:
        """Default position: top-left of the work area (away from browser center)."""
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
            x = avail.left() + margin
            y = avail.top() + margin
            self.move(x, y)
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
            # _on_text schedules auto-connect when the value looks like a PAT

    def _on_text(self, text: str) -> None:
        has = bool((text or "").strip())
        self._btn_connect.setEnabled(has)
        if _looks_like_token(text or ""):
            self._google_rejected = False
            self._clear_token_note_taken()
            self._btn_reopen.hide()
            self._btn_open_tokens.hide()
            self._mark_reached(3)
            self._status.setStyleSheet(
                "font-size:11.5px;color:#1f6f5c;border:none;"
            )
            self._status.setText("키를 인식했어요. 자동으로 연결합니다…")
            self._schedule_auto_connect(source="키 인식")
        elif has:
            self._status.setText("")

    def _schedule_auto_connect(self, *, source: str) -> None:
        """When a PAT is in the field, press Connect without a second click."""
        if self._done or self._auto_connect_pending:
            return
        if not _looks_like_token(self._edit.text() or ""):
            return
        self._auto_connect_pending = True
        self._status.setStyleSheet(
            "font-size:11.5px;color:#1f6f5c;border:none;"
        )
        self._status.setText(f"{source} — 자동으로 연결합니다…")
        # Defer so textChanged / clipboard handlers finish first
        QTimer.singleShot(0, self._run_auto_connect)

    def _run_auto_connect(self) -> None:
        self._auto_connect_pending = False
        if self._done:
            return
        self._on_connect()

    def _refresh_checklist_labels(self) -> None:
        for i, lab in enumerate(self._check_labels):
            text = checklist_row_label(
                i,
                reached=self._reached,
                current=self._current,
                google_rejected=self._google_rejected,
                token_note_taken=self._token_note_taken,
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

    def _sync_open_tokens_button(self) -> None:
        if self._token_note_taken:
            self._btn_open_tokens.setText("다른 이름으로 키 만들기 열기")
        else:
            self._btn_open_tokens.setText("키 만들기 페이지 열기")

    def _show_token_note_taken(self, meta: dict | None = None) -> None:
        self._token_note_taken = True
        self._google_rejected = False
        self._btn_reopen.hide()
        # Login stays done; key-create row shows "!" not sticky ✓
        self._reached = max(self._reached, 1)
        if self._reached >= 2:
            self._reached = 1
        self._current = 2
        self._refresh_checklist_labels()
        title, lead, verify_fallback = token_note_error_guide_copy()
        self._title.setText(title)
        self._lead.setText(lead)
        snippets = list((meta or {}).get("error_snippets") or [])
        if snippets:
            verify = "검증: " + snippets[0][:72]
        else:
            verify = verify_fallback
        self._verify_lab.setText(verify)
        self._verify_lab.setStyleSheet(
            "font-size:11.5px;color:#8a6d12;border:none;"
        )
        self._status.setStyleSheet(
            "font-size:11.5px;color:#8a6d12;border:none;"
        )
        self._status.setText(
            "Note(이름)이 이미 쓰였어요. 이름을 바꾸거나 "
            "「다른 이름으로 키 만들기 열기」를 누르세요."
        )
        self._sync_open_tokens_button()
        self._btn_open_tokens.show()
        self.adjustSize()
        self._place_top_left()

    def _clear_token_note_taken(self) -> None:
        if not self._token_note_taken:
            return
        self._token_note_taken = False
        self._sync_open_tokens_button()

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
        self._place_top_left()

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

    def _open_token_create_page(self, *, unique_note: bool = True) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        # Always use a fresh Note so retries don't hit "already been taken"
        url = build_pat_create_url() if unique_note else build_pat_create_url(note="CloneUp")
        QDesktopServices.openUrl(QUrl(url))
        self._token_nav_opened = True
        self._last_family_url = url

    def _on_open_token_page_clicked(self) -> None:
        self._clear_token_note_taken()
        self._btn_return_flow.hide()
        self._open_token_create_page(unique_note=True)
        self._set_current(2)
        self._apply_progress_copy(1)
        self._status.setStyleSheet(
            "font-size:11.5px;color:#1f6f5c;border:none;"
        )
        self._status.setText(
            "새 Note 이름으로 열었어요. Generate token을 누르세요."
        )
        self._sync_open_tokens_button()

    def _remember_family_url(self, url: str) -> None:
        u = (url or "").strip()
        if not u:
            return
        if not is_github_flow_family_url(u):
            return
        # Prefer https github / oauth URLs; skip javascript: etc.
        low = u.lower()
        if not (low.startswith("http://") or low.startswith("https://")):
            return
        self._last_family_url = u

    def _show_away_from_flow(self) -> None:
        """Soft invite back — never auto-navigate."""
        title, lead, verify = away_from_flow_guide_copy()
        self._title.setText(title)
        self._lead.setText(lead)
        self._verify_lab.setText(verify)
        self._verify_lab.setStyleSheet(
            "font-size:11.5px;color:#6d675c;border:none;"
        )
        self._status.setStyleSheet(
            "font-size:11.5px;color:#6d675c;border:none;"
        )
        self._status.setText(
            "다른 탭을 보셔도 됩니다. 준비가 되면 "
            "「마지막으로 열었던 페이지로 돌아가기」를 눌러 주세요."
        )
        self._btn_return_flow.show()
        # Don't hide token/reopen buttons aggressively — user may still want them
        self.adjustSize()
        self._place_top_left()

    def _on_return_to_flow_clicked(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        target = (self._last_family_url or "").strip()
        if not target:
            target = fallback_return_url(reached=self._reached)
        QDesktopServices.openUrl(QUrl(target))
        self._btn_return_flow.hide()
        self._status.setStyleSheet(
            "font-size:11.5px;color:#1f6f5c;border:none;"
        )
        self._status.setText(
            "마지막으로 열었던 페이지를 열었어요. 이어서 진행해 주세요."
        )

    def _reopen_github_login(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(_GITHUB_LOGIN))
        self._clear_google_rejected_banner()
        self._clear_token_note_taken()
        self._btn_open_tokens.hide()
        self._btn_return_flow.hide()
        self._last_family_url = _GITHUB_LOGIN
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

        # Remember last in-family URL for soft "return" (never auto-navigate away)
        if kind != "away" and url:
            self._remember_family_url(url)

        if kind == "rejected":
            self._btn_return_flow.hide()
            self._show_google_rejected(url, meta)
            return

        if kind == "token_error":
            self._btn_return_flow.hide()
            self._show_token_note_taken(meta)
            return

        if kind == "away":
            # Soft nudge only — keep checklist sticky; do not open URLs
            self._show_away_from_flow()
            return

        if kind == "logged_out":
            # User signed out (or logged-out github.com with Sign in/up) —
            # wipe sticky progress so old ✓ marks disappear
            self._clear_google_rejected_banner()
            self._clear_token_note_taken()
            self._btn_return_flow.hide()
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
            self._place_top_left()
            return

        if kind == "current" and idx is not None:
            self._clear_google_rejected_banner()
            self._clear_token_note_taken()
            self._btn_return_flow.hide()
            self._btn_open_tokens.hide()
            self._set_current(idx)
            self._apply_method_copy(method)
            return

        if kind == "reached" and idx is not None:
            self._clear_google_rejected_banner()
            self._clear_token_note_taken()
            self._btn_return_flow.hide()
            self._btn_reopen.hide()
            self._mark_reached(idx)
            self._apply_progress_copy(idx)

            if idx == 1:
                # Logged in on github.com — guide toward classic token create
                self._set_current(2)
                self._sync_open_tokens_button()
                self._btn_open_tokens.show()
                if should_auto_open_token_page(
                    kind=kind,
                    idx=idx,
                    already_opened=self._token_nav_opened,
                ):
                    self._open_token_create_page(unique_note=True)
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
                self._sync_open_tokens_button()
                self._btn_open_tokens.show()
                self._status.setStyleSheet(
                    "font-size:11.5px;color:#1f6f5c;border:none;"
                )
                self._status.setText(
                    "Generate token을 누른 뒤 나온 키를 복사하세요."
                )
            else:
                # idx == 3 — issued / copy; prefer UIA-visible PAT when present
                visible = str((meta or {}).get("visible_pat") or "").strip()
                if not visible:
                    visible = (
                        extract_visible_pat(
                            sample.window_title, sample.ui_text
                        )
                        or ""
                    )
                if visible and _looks_like_token(visible):
                    self._ingest_token(
                        visible, source="화면에서 키를 읽었어요"
                    )
                else:
                    self._current = None
                    self._refresh_checklist_labels()
                    self._btn_open_tokens.hide()
                    self._status.setStyleSheet(
                        "font-size:11.5px;color:#1f6f5c;border:none;"
                    )
                    self._status.setText(
                        "화면에 키가 보이면 자동으로 들어옵니다. "
                        "안 되면 복사해 붙여 넣으세요."
                    )
            self.adjustSize()
            self._place_top_left()
            return

        self._btn_return_flow.hide()
        self._verify_lab.setText("검증: 주소를 분류하지 못함 — 체크리스트 유지")

    def _ingest_token(self, text: str, *, source: str) -> None:
        """Fill the key field from clipboard or UIA-visible PAT, then auto-Connect."""
        tok = (text or "").strip()
        if not _looks_like_token(tok) or tok == self._clip_seen:
            return
        if self._done:
            return
        self._clip_seen = tok
        self._edit.setText(tok)
        self._clear_google_rejected_banner()
        self._clear_token_note_taken()
        self._btn_open_tokens.hide()
        self._btn_return_flow.hide()
        self._mark_reached(3)
        self._apply_progress_copy(3)
        self.raise_()
        self.activateWindow()
        # setText already triggers _on_text → _schedule_auto_connect;
        # call again in case text was identical and textChanged did not fire
        self._schedule_auto_connect(source=source)

    def _poll_clipboard(self) -> None:
        if self._done:
            return
        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        text = (clip.text() or "").strip()
        self._ingest_token(text, source="클립보드에서 키를 인식했어요")

    def _on_connect(self) -> None:
        """Path B Connect — accept with token; does not touch WebView wizard."""
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
        self._token = raw
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
        # Only treat as cancel when the user dismissed without Connect.
        # Success path sets _done before accept()/close.
        if not self._done:
            self._done = True
            self.cancelled.emit()
        super().closeEvent(event)

    def token(self) -> str:
        return (self._token or self._edit.text() or "").strip()
