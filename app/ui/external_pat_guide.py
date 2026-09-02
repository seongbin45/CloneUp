"""Path B floating guide — conversational browser connect.

Design: ``desin/CloneUp 브라우저 안내 대화형.dc.html``

User signs in (and confirms passkey/email) in the OS browser, then sets
Expiration and scopes **on the GitHub page**. Hint chips + 「골랐어요」/
「확인했어요」 guide the steps; the app reads Expiration via UIA/OCR and
collects the issued PAT (clipboard / UIA). On the Generate step the guide
auto-finds and clicks 「Generate token」 (spinner status; no 「도와주세요」).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.auth.github_page_stage import GitHubPageStage, PageSnapshot, detect_github_page_stage
from app.auth.pat_urls import (
    classic_pat_create_url,
    make_pat_note,
    note_from_pat_create_url,
)
from app.ui.theme import active_palette
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

# Slight translucency so the browser behind remains faintly visible.
_GUIDE_OPACITY = 0.90


def _ss(color: str, *, size: str = "12.5px", weight: str | None = None, mono: bool = False) -> str:
    """Inline label QSS from a palette color (light/dark)."""
    parts = [f"font-size:{size}", f"color:{color}", "border:none", "background:transparent"]
    if weight:
        parts.append(f"font-weight:{weight}")
    if mono:
        parts.append("font-family: Consolas, 'IBM Plex Mono', monospace")
    return ";".join(parts) + ";"


def _guide_dialog_qss() -> str:
    p = active_palette()
    # Outer dialog is transparent so Windows HWND corners don't look square;
    # the rounded card (#dlgCard) is the visible chrome.
    return f"""
    QDialog#pathBGuide {{
        background: transparent;
        color: {p.text};
    }}
    QFrame#dlgCard {{
        background: {p.bg_window};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 16px;
    }}
    QLineEdit {{
        background: {p.bg_input};
        color: {p.text};
        border: 1px solid {p.border_input};
        border-radius: 8px;
        padding: 6px 10px;
        selection-background-color: {p.primary};
    }}
    QPushButton {{
        background: {p.bg_window};
        color: {p.text};
        border: 1px solid {p.border_outline};
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 12.5px;
        min-height: 28px;
    }}
    QPushButton:hover {{
        background: {p.bg_hint};
    }}
    QPushButton:disabled {{
        color: {p.text_disabled};
        border: 1px solid {p.border_soft};
    }}
    QPushButton:default {{
        background: {p.primary};
        color: {p.text_on_primary};
        border: 1px solid {p.primary};
        font-weight: 600;
    }}
    QPushButton:default:hover {{
        background: {p.primary_hover};
    }}
    """


def _c_ok() -> str:
    return active_palette().primary


def _c_warn() -> str:
    return active_palette().warn_text


def _c_meta() -> str:
    return active_palette().text_muted


def _c_body() -> str:
    return active_palette().text_secondary


def _c_faint() -> str:
    return active_palette().text_faint


def _c_title() -> str:
    return active_palette().text
_ADDR_POLL_MS = 2500
_EXPIRY_POLL_MS = 1100  # ASK_EXPIRY: OCR-only ticks
_CLIP_POLL_MS = 500

_TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")
_GITHUB_LOGIN = "https://github.com/login"


def build_pat_create_url(*, note: str | None = None) -> str:
    """classic ``repo`` token form; Note = CloneUp-YYYYMMDD-HHMMSS by default."""
    return classic_pat_create_url(note=note or make_pat_note())


def build_pat_create_url_with_note(
    *, note: str | None = None, scopes: str = "repo"
) -> tuple[str, str]:
    n = (note or "").strip() or make_pat_note()
    return classic_pat_create_url(note=n, scopes=scopes or "repo"), n


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

    from app.util.browser_address import (
        looks_like_github_logged_in_ui,
        looks_like_github_logged_out_ui,
    )

    # Explicit logout URL
    if method == "github_logout":
        return ("logged_out", 0, meta)

    # Weak "logged out" from a11y — override when dashboard / settings URL proves login
    if method == "github_logged_out":
        u_l = u.lower()
        if looks_like_github_logged_in_ui(window_title, ui_text):
            meta["method"] = "github"
            # fall through — treat as logged-in below
        elif "/settings/" in u_l or "/tokens" in u_l:
            meta["method"] = "github"
        else:
            return ("logged_out", 0, meta)

    # Passkey / 2FA options / login form → still signing in
    if method in (
        "passkey",
        "apple",
        "google",
        "github_login",
        "github_2fa",
        "github_mobile",
        "github_totp",
        "github_recovery",
    ):
        return ("current", 0, meta)

    if not u and not window_title and not (ui_text or "").strip():
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

    # Pass title + accessible text — omnibox alone misses list vs /new and 2FA.
    st = detect_github_page_stage(
        PageSnapshot(url=u, title=window_title or "", html=ui_text or "")
    )
    if st == GitHubPageStage.TOKEN_ISSUED:
        return ("reached", 3, meta)
    if st in (GitHubPageStage.TOKEN_CLASSIC_NEW, GitHubPageStage.TOKEN_FINE_NEW):
        meta["method"] = "token_new"
        meta["page_stage"] = st.value
        return ("reached", 2, meta)
    if st in (GitHubPageStage.TOKEN_CLASSIC_LIST, GitHubPageStage.TOKEN_FINE_LIST):
        # List is NOT the create form — Path B must reopen tokens/new.
        meta["method"] = "token_list"
        meta["page_stage"] = st.value
        return ("reached", 2, meta)
    if st == GitHubPageStage.AUTH_2FA:
        # Not "reached" for dialogue — refine Mobile / TOTP / recovery / email.
        refined = None
        try:
            from app.util.auth_ocr import classify_auth_ocr_text

            refined = classify_auth_ocr_text(
                ui_text or "", window_title=window_title or "", url=u
            )
        except Exception:
            refined = None
        if refined in (
            "github_mobile",
            "github_totp",
            "github_recovery",
            "github_2fa",
        ):
            meta["method"] = refined
        else:
            meta["method"] = "github_2fa"
        return ("current", 0, meta)
    if st == GitHubPageStage.AUTH_PASSKEY_OS:
        # Windows Security sheet *or* GitHub Confirm access + Use passkey
        # (sudo on tokens/new). Still signing in — never "reached".
        meta["method"] = "passkey"
        return ("current", 0, meta)
    if st == GitHubPageStage.SUDO_OR_OTHER:
        meta["method"] = "passkey" if "passkey" in (
            (window_title or "") + "\n" + (ui_text or "")
        ).lower() else "github_login"
        return ("current", 0, meta)
    if st == GitHubPageStage.LOGIN:
        return ("current", 0, meta)

    # Title-only GitHub window (omnibox empty) — after stage body checks miss.
    if not u and "github" in (window_title or "").lower():
        if looks_like_github_logged_out_ui(window_title, ui_text, url=""):
            return ("logged_out", 0, meta)
        meta["method"] = "github_title"
        return ("reached", 1, meta)

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
    """When no remembered family URL, suggest a sensible resume target.

    Prefer ``build_pat_create_url_with_note`` at call sites that need to
    record Note; this helper only returns a URL (Note is embedded in query).
    """
    if reached >= 2:
        url, _note = build_pat_create_url_with_note()
        return url
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
            "Windows 「패스키로 로그인」또는 GitHub 「Confirm access → Use passkey」"
            "에서 확인하세요.",
            "검증: 패스키(OS·Confirm access) — 진행 중",
        )
    if method == "github_mobile":
        return (
            "GitHub Mobile 승인 중",
            "휴대폰 GitHub 앱에서 로그인 요청을 승인해 주세요.",
            "검증: GitHub Mobile 승인 요청 — 진행 중",
        )
    if method == "github_totp":
        return (
            "인증 앱 코드 입력 중",
            "Authenticator 앱(또는 확장)의 6자리 코드를 입력한 뒤 Verify를 누르세요.",
            "검증: Authenticator OTP — 진행 중",
        )
    if method == "github_recovery":
        return (
            "복구 코드 입력 중",
            "미리 받아 둔 2FA recovery code를 입력한 뒤 Verify를 누르세요.",
            "검증: Two-factor recovery — 진행 중",
        )
    if method == "github_2fa":
        return (
            "기기 확인이 필요해요",
            "이메일로 온 인증 코드를 입력하거나, 「Verify with a passkey」로 패스키를 쓰세요. "
            "확인이 끝나면 키 만들기 화면으로 이어집니다.",
            "검증: Verify your device / 이메일·패스키 — 진행 중",
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
    url: str = "",
    title: str = "",
    page_text: str = "",
) -> bool:
    """Open tokens/new once when login is confirmed on github.com main."""
    from app.ui.webview_flow_detect import (
        should_auto_open_token_page as _shared_should_auto_open,
    )

    return _shared_should_auto_open(
        kind=kind,
        idx=idx,
        already_opened=already_opened,
        url=url,
        title=title,
        page_text=page_text,
    )



# --- conversational Path B panel (concatenated after helpers) ---

from app.ui.browser_dialogue_model import (
    DialogueScene,
    SCOPE_OPTIONS,
    advance_from_browser_kind,
    build_history,
    expires_at_for_days,
    expiry_days_value,
    expiry_label_for_days,
    scene_copy,
    scope_query_value,
)
from app.ui.path_b_assist_worker import PathBAddressWorker, PathBAssistWorker
from app.util.browser_address import (
    path_b_log,
    read_token_expiration_uia,
    set_path_b_log_sink,
)


def _dialogue_qss() -> str:
    p = active_palette()
    return _guide_dialog_qss() + f"""
    QLabel#dlgSay {{
        font-size: 16px; font-weight: 600; color: {p.text};
        border: none; background: transparent;
    }}
    QLabel#dlgSub {{
        font-size: 12.5px; color: {p.text_muted};
        border: none; background: transparent;
    }}
    QLabel#dlgHeadTitle {{
        font-size: 12px; font-weight: 600; color: {p.text};
        border: none; background: transparent;
    }}
    QLabel#dlgRightTag {{
        font-size: 11.5px; color: {p.text_muted};
        border: none; background: transparent;
    }}
    QLabel#dlgHistText {{
        font-size: 12px; color: {p.text_muted};
        border: none; background: transparent;
    }}
    QPushButton#dlgHistChange {{
        background: transparent; border: none;
        color: {p.primary}; font-size: 11.5px; padding: 0 2px;
        min-height: 0;
    }}
    QPushButton#dlgHistChange:hover {{ color: {p.primary_hover}; }}
    QPushButton#dlgChip {{
        background: {p.bg_muted};
        border: 1px solid {p.border_outline};
        border-radius: 12px;
        padding: 12px 16px;
        font-size: 14px;
        font-weight: 500;
        color: {p.text};
        min-height: 44px;
        text-align: left;
    }}
    QPushButton#dlgChip:hover {{
        background: {p.hover_muted};
        border: 1px solid {p.primary};
    }}
    QPushButton#dlgChipRec {{
        background: {p.bg_window};
        border: 2px solid {p.primary};
        border-radius: 12px;
        padding: 12px 16px;
        font-size: 14px;
        font-weight: 600;
        color: {p.text};
        min-height: 44px;
        text-align: left;
    }}
    QPushButton#dlgChipRec:hover {{
        background: {p.bg_hint};
    }}
    /* Detected Expiration readout — same green outline as recommended chip */
    QFrame#dlgExpiryRead {{
        background: {p.bg_window};
        border: 2px solid {p.primary};
        border-radius: 12px;
    }}
    QLabel#dlgExpiryReadValue {{
        font-size: 14px;
        font-weight: 600;
        color: {p.text};
        padding: 2px 0;
    }}
    QLabel#dlgExpiryReadHint {{
        font-size: 12px;
        color: {p.text_muted};
    }}
    QLabel#dlgExpiryReadSpin {{
        font-size: 11px;
        font-weight: 600;
        color: {p.primary};
        min-width: 28px;
    }}
    QFrame#dlgWait {{
        background: {p.bg_muted}; border: none; border-radius: 12px;
    }}
    QScrollArea#dlgScroll {{
        background: transparent;
        border: none;
    }}
    QScrollArea#dlgScroll > QWidget > QWidget {{
        background: transparent;
    }}
    QFrame#dlgNudge {{
        background: {_warn_soft()}; border: 1px solid {p.warn_border};
        border-radius: 12px;
    }}
    QLabel#dlgNudgeSpin {{
        font-size: 11px;
        font-weight: 600;
        color: {p.warn_border};
        min-width: 28px;
    }}
    QPushButton#dlgNudgeBtn {{
        background: {p.bg_window}; border: 1px solid {p.warn_border};
        border-radius: 9px; padding: 4px 13px; font-size: 12px;
        color: {p.text}; min-height: 32px;
    }}
    QPushButton#dlgPrimary {{
        background: {p.primary}; color: {p.text_on_primary};
        border: 1px solid {p.primary}; border-radius: 12px;
        font-size: 14.5px; font-weight: 600; min-height: 46px;
    }}
    QPushButton#dlgPrimary:hover {{ background: {p.primary_hover}; }}
    QPushButton#dlgQuit {{
        background: transparent; border: none; color: {p.text_muted};
        font-size: 12px; padding: 0; min-height: 0;
    }}
    QPushButton#dlgQuit:hover {{ color: {p.text}; }}
    QFrame#dlgHeader {{
        background: {p.bg_bar}; border: none;
        border-bottom: 1px solid {p.border_soft};
        border-top-left-radius: 16px;
        border-top-right-radius: 16px;
    }}
    QPushButton#dlgCloseX {{
        background: transparent; color: {p.text_muted}; border: none;
        font-size: 14px; padding: 0 4px; min-width: 22px; min-height: 22px;
    }}
    QPushButton#dlgCloseX:hover {{ color: {p.text}; }}
    QFrame#dlgReceipt {{
        background: {p.bg_muted}; border: none; border-radius: 12px;
    }}
    """


def _warn_soft() -> str:
    return "#2e2a1e" if active_palette().name == "dark" else "#fbf6ee"


class ExternalBrowserPatGuide(QDialog):
    """Conversational Path B guide (checklist removed)."""

    token_accepted = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        anchor: QWidget | None = None,
        *,
        open_login_on_start: bool = False,
        log: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(None)
        self._anchor = anchor
        self._done = False
        self._token = ""
        self._pat_note = ""
        self._expires_at: str | None = None
        self._open_login_on_start = open_login_on_start
        self._ui_log = log
        self._scene = DialogueScene.LOGIN_WAIT
        self._expiry_label: str | None = None  # detected / confirmed (receipt)
        self._expiry_hint: str | None = None  # chip hint only
        self._scope_label: str | None = None
        self._logged_in = False
        self._auth_done = False  # email / passkey / 2FA finished
        self._auth_method = ""  # passkey | github_2fa | apple | google | …
        self._got_token = False
        self._token_nav_opened = False
        self._create_url = ""
        self._last_family_url = ""
        self._google_blocked = False
        self._wait_dot_i = 0
        self._clip_seen = ""
        self._expiry_uia_ok = False
        self._expiry_uia_tries = 0
        self._assist_worker: PathBAssistWorker | None = None
        self._addr_worker: PathBAddressWorker | None = None
        self._addr_poll_busy = False
        self._away_streak = 0
        self._login_rescue_done = False
        self._last_expiry_days_read: str | None = None  # last UIA/OCR days token
        self._expiry_miss_log_at = 0.0  # throttle "미감지" logs
        self._expiry_poll_i = 0  # ASK_EXPIRY: occasional address bounce check
        self._expiry_scanning = False  # spinner while OCR re-reads
        self._expiry_scan_gen = 0  # cancel delayed spinner if result is fast
        self._expiry_read_spin: QLabel | None = None
        self._expiry_read_value: QLabel | None = None
        self._expiry_confirm_btn: QPushButton | None = None
        self._nudge_pending = False  # reserved; auto-assist coalescing
        self._assist_aside = False  # guide dimmed while CDP/UIA clicks

        # Tee Path B UIA helpers into main textLog while this guide is alive.
        set_path_b_log_sink(self._emit_log)
        self._guide_log("[Path B] 브라우저 안내 시작")

        self.setObjectName("pathBGuide")
        self.setWindowTitle("CloneUp — GitHub 연결")
        # Non-modal vs CloneUp main: browser must keep keyboard focus for
        # email codes / passkeys. Stay-on-top keeps the card visible without
        # ApplicationModal focus fights. Frameless + translucent → rounded card.
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(_GUIDE_OPACITY)
        self.setMinimumWidth(360)
        self.setMaximumWidth(440)
        # Height capped in _place_bottom_left to the work area; content scrolls.
        self.setMinimumHeight(220)
        self.setStyleSheet(_dialogue_qss())
        self._drag_offset: QPoint | None = None

        # Rounded card (visible chrome) inside transparent dialog shell.
        card = QFrame()
        card.setObjectName("dlgCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # Header (custom — replaces OS title bar)
        head = QFrame()
        head.setObjectName("dlgHeader")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 11, 10, 11)
        hl.setSpacing(10)
        brand = QLabel("GitHub 연결")
        brand.setObjectName("dlgHeadTitle")
        self._right_tag = QLabel("1 / 3")
        self._right_tag.setObjectName("dlgRightTag")
        btn_x = QPushButton("✕")
        btn_x.setObjectName("dlgCloseX")
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.clicked.connect(self._on_cancel)
        hl.addWidget(brand)
        hl.addStretch(1)
        hl.addWidget(self._right_tag)
        hl.addWidget(btn_x, 0)

        # Scrollable middle: history grows with steps and used to clip the
        # bottom of the StayOnTop card off-screen (no scroll = cut buttons).
        mid = QWidget()
        mid_lay = QVBoxLayout(mid)
        mid_lay.setContentsMargins(16, 15, 16, 12)
        mid_lay.setSpacing(12)

        self._hist_host = QVBoxLayout()
        self._hist_host.setContentsMargins(0, 0, 0, 0)
        self._hist_host.setSpacing(6)

        self._say = QLabel("")
        self._say.setObjectName("dlgSay")
        self._say.setWordWrap(True)
        self._sub = QLabel("")
        self._sub.setObjectName("dlgSub")
        self._sub.setWordWrap(True)

        self._chips_host = QWidget()
        self._chips_host.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        # Vertical stack — horizontal pills were easy to miss / clip at 440px.
        self._chips_lay = QVBoxLayout(self._chips_host)
        # Bottom margin keeps the primary chip/button clear of the card radius.
        self._chips_lay.setContentsMargins(0, 4, 0, 10)
        self._chips_lay.setSpacing(8)
        self._chips_host.hide()

        self._wait = QFrame()
        self._wait.setObjectName("dlgWait")
        wl = QHBoxLayout(self._wait)
        wl.setContentsMargins(12, 12, 14, 12)
        wl.setSpacing(10)
        self._wait_dots = QLabel("●○○")
        self._wait_dots.setStyleSheet(_ss(_c_ok(), size="10px"))
        self._wait_text = QLabel("")
        self._wait_text.setObjectName("dlgSub")
        self._wait_text.setWordWrap(True)
        wl.addWidget(self._wait_dots, 0)
        wl.addWidget(self._wait_text, 1)
        self._wait.hide()

        # PRESS_GENERATE status: spinner + “찾고 있어요” (no 도와주세요 button).
        self._nudge = QFrame()
        self._nudge.setObjectName("dlgNudge")
        nl = QHBoxLayout(self._nudge)
        nl.setContentsMargins(13, 12, 13, 12)
        nl.setSpacing(10)
        self._nudge_spin = QLabel("●○○")
        self._nudge_spin.setObjectName("dlgNudgeSpin")
        self._nudge_spin.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self._nudge_text = QLabel("")
        self._nudge_text.setObjectName("dlgSub")
        self._nudge_text.setWordWrap(True)
        nl.addWidget(self._nudge_spin, 0)
        nl.addWidget(self._nudge_text, 1)
        # Kept for CDP opt-in (CLONEUP_CDP=1); hidden unless enabled.
        self._nudge_btn = QPushButton("")  # unused — auto-assist replaces 도와주세요
        self._nudge_btn.hide()
        self._nudge_cdp_btn = QPushButton("제어용 브라우저 열기")
        self._nudge_cdp_btn.setObjectName("dlgNudgeBtn")
        self._nudge_cdp_btn.setToolTip(
            "CLONEUP_CDP=1 일 때, 디버깅 포트로 Chrome/Edge를 전용 프로필로 엽니다."
        )
        self._nudge_cdp_btn.clicked.connect(self._on_launch_cdp_browser)
        self._nudge_cdp_btn.hide()
        self._nudge.hide()
        self._generate_auto_started = False

        self._done_host = QWidget()
        self._done_lay = QVBoxLayout(self._done_host)
        self._done_lay.setContentsMargins(0, 0, 0, 0)
        self._done_lay.setSpacing(7)
        self._done_host.hide()

        self._btn_reopen = QPushButton("GitHub 로그인 다시 열기")
        self._btn_reopen.clicked.connect(self._reopen_github_login)
        self._btn_reopen.hide()

        # Hidden fallback paste (auto-connect still works)
        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.hide()
        self._edit.textChanged.connect(self._on_edit_text)

        mid_lay.addLayout(self._hist_host)
        mid_lay.addWidget(self._say)
        mid_lay.addWidget(self._sub)
        mid_lay.addWidget(self._chips_host)
        mid_lay.addWidget(self._wait)
        mid_lay.addWidget(self._nudge)
        mid_lay.addWidget(self._done_host)
        mid_lay.addWidget(self._btn_reopen)
        mid_lay.addWidget(self._edit)
        mid_lay.addStretch(0)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("dlgScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setWidget(mid)
        self._scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Footer always visible below the scroll (그만하기 / 안내).
        foot_w = QWidget()
        foot = QHBoxLayout(foot_w)
        foot.setContentsMargins(16, 4, 16, 16)
        foot.setSpacing(8)
        self._btn_quit = QPushButton("그만하기")
        self._btn_quit.setObjectName("dlgQuit")
        self._btn_quit.clicked.connect(self._on_cancel)
        self._foot_note = QLabel("")
        self._foot_note.setObjectName("dlgSub")
        self._foot_note.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        foot.addWidget(self._btn_quit)
        foot.addStretch(1)
        foot.addWidget(self._foot_note)

        card_lay.addWidget(head)
        card_lay.addWidget(self._scroll, 1)
        card_lay.addWidget(foot_w, 0)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(card)

        self._clip_timer = QTimer(self)
        self._clip_timer.setInterval(_CLIP_POLL_MS)
        self._clip_timer.timeout.connect(self._poll_clipboard)
        self._clip_timer.start()

        self._addr_timer = QTimer(self)
        self._addr_timer.setInterval(_ADDR_POLL_MS)
        self._addr_timer.timeout.connect(self._poll_address)
        self._addr_timer.start()

        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(420)
        self._dot_timer.timeout.connect(self._tick_dots)

        self._render()
        self._place_bottom_left()
        QTimer.singleShot(400, self._poll_address)
        if self._open_login_on_start:
            QTimer.singleShot(200, self._reopen_github_login)

    # --- public API ---
    def token(self) -> str:
        return (self._token or self._edit.text() or "").strip()

    def token_note(self) -> str:
        return (self._pat_note or "").strip()

    def token_expires_at(self) -> str | None:
        return self._expires_at

    def _emit_log(self, message: str) -> None:
        """Sink for ``path_b_log`` — main ``textLog`` only (print already done)."""
        if self._ui_log is None:
            return
        try:
            self._ui_log(message)
        except Exception:
            pass

    def _guide_log(self, message: str) -> None:
        """Scene / chip events — print + textLog via Path B sink."""
        path_b_log(message)

    def _set_user_status(self, friendly: str, *, detail: str = "") -> None:
        """Show plain-language copy in the card; keep tech detail in the log."""
        text = (friendly or "").strip()
        if text:
            self._sub.setText(text)
        if detail:
            self._guide_log(detail)

    @staticmethod
    def _friendly_generate_miss(*, detected: str = "", detail: str = "") -> str:
        """User-facing copy when auto Generate click fails."""
        base = (
            "초록 Generate token 버튼을 아직 찾지 못했어요. "
            "키 만들기 페이지가 앞에 보이는지 확인해 주세요."
        )
        if detected:
            return (
                f"{base} "
                f"만료일이 「{detected}」로 보이면 「골랐어요」를 다시 눌러 주세요. "
                "페이지를 조금 아래로 내려도 도움이 됩니다."
            )
        return (
            f"{base} "
            "브라우저에서 Expiration을 다시 고른 뒤 「골랐어요」를 눌러 주세요."
        )

    def _place_bottom_left(self) -> None:
        """Lower-left of the work area; never taller than the screen.

        Long history used to grow the StayOnTop card past the bottom edge
        (buttons clipped). Cap height and scroll the middle instead.
        """
        margin = 24
        try:
            screen = None
            if self._anchor is not None:
                screen = self._anchor.screen()
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is None:
                self.adjustSize()
                return
            avail = screen.availableGeometry()
            max_h = max(280, avail.height() - 2 * margin)
            max_w = min(440, max(360, avail.width() - 2 * margin))
            self.setMaximumHeight(max_h)
            self.setMaximumWidth(max_w)

            self.updateGeometry()
            hint = self.sizeHint()
            want_w = max(360, min(max_w, hint.width() if hint.isValid() else 400))
            # Prefer content height but never exceed the work area.
            want_h = hint.height() if hint.isValid() and hint.height() > 0 else 420
            want_h = max(220, min(want_h, max_h))
            self.resize(want_w, want_h)

            fg = self.frameGeometry()
            x = avail.left() + margin
            y = avail.top() + avail.height() - fg.height() - margin
            y = max(avail.top() + margin, y)
            if y + fg.height() > avail.top() + avail.height() - margin:
                y = avail.top() + avail.height() - fg.height() - margin
                y = max(avail.top() + margin, y)
            self.move(x, y)
        except Exception:
            try:
                self.adjustSize()
            except Exception:
                pass

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    # --- scene render ---
    def _set_scene(self, scene: DialogueScene) -> None:
        if scene == self._scene:
            # Still refresh chips/visibility (e.g. after reopen)
            self._render()
            self._place_bottom_left()
            return
        prev = self._scene
        self._scene = scene
        self._guide_log(f"[Path B] 장면 {prev.name} → {scene.name}")
        if scene != DialogueScene.PRESS_GENERATE:
            self._generate_auto_started = False
        self._render()
        self._sync_poll_interval()
        self._place_bottom_left()
        # Entering Generate step → auto-find/click (no 「도와주세요」).
        if (
            scene == DialogueScene.PRESS_GENERATE
            and prev != DialogueScene.PRESS_GENERATE
        ):
            QTimer.singleShot(350, self._auto_generate_assist)

    def _render(self) -> None:
        sc = scene_copy(
            self._scene,
            expiry_label=self._expiry_label or "90일",
            auth_method=self._auth_method,
        )
        self._right_tag.setText(sc.right_tag)
        self._say.setText(sc.say)
        self._sub.setText(sc.sub)
        self._foot_note.setText(sc.foot_note)
        self._btn_quit.setVisible(sc.show_cancel)

        self._rebuild_history()
        self._rebuild_chips()

        waiting = self._scene in (
            DialogueScene.LOGIN_WAIT,
            DialogueScene.AUTH_WAIT,
        )
        self._wait.setVisible(waiting)
        if waiting:
            self._wait_text.setText(sc.wait_text)
            if not self._dot_timer.isActive():
                self._dot_timer.start()
        elif self._expiry_scanning or (
            self._scene == DialogueScene.PRESS_GENERATE and self._assist_busy()
        ):
            if not self._dot_timer.isActive():
                self._dot_timer.start()
        elif self._scene != DialogueScene.PRESS_GENERATE:
            self._dot_timer.stop()

        nudge = self._scene == DialogueScene.PRESS_GENERATE
        self._nudge.setVisible(nudge)
        if nudge:
            # Yellow status: spinner + “찾고 있어요” (no 도와주세요 button).
            busy = self._assist_busy() or self._generate_auto_started
            if busy or not (self._nudge_text.text() or "").strip():
                self._nudge_text.setText(
                    sc.nudge_text or "Generate token 버튼을 찾고 있어요"
                )
            self._nudge_spin.show()
            if busy and not self._dot_timer.isActive():
                self._dot_timer.start()
        self._nudge_cdp_btn.hide()
        self._nudge_btn.hide()

        done = self._scene == DialogueScene.DONE
        self._done_host.setVisible(done)
        if done:
            self._rebuild_receipt()

        self._btn_reopen.setVisible(
            self._scene == DialogueScene.LOGIN_WAIT and self._google_blocked
        )

    def _rebuild_history(self) -> None:
        while self._hist_host.count():
            item = self._hist_host.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        rows = build_history(
            self._scene,
            expiry_label=self._expiry_label,
            scope_label=self._scope_label,
            logged_in=self._logged_in,
            got_token=self._got_token,
            auth_done=self._auth_done,
        )
        for row in rows:
            bar = QWidget()
            hl = QHBoxLayout(bar)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(9)
            mark = QLabel("✓")
            mark.setStyleSheet(_ss(_c_ok(), size="10px"))
            mark.setFixedWidth(13)
            mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text = QLabel(row.text)
            text.setObjectName("dlgHistText")
            hl.addWidget(mark)
            hl.addWidget(text, 1)
            if row.editable and row.back_to is not None:
                btn = QPushButton("변경")
                btn.setObjectName("dlgHistChange")
                target = row.back_to
                btn.clicked.connect(lambda _=False, t=target: self._on_history_change(t))
                hl.addWidget(btn)
            self._hist_host.addWidget(bar)

    def _rebuild_chips(self) -> None:
        while self._chips_lay.count():
            item = self._chips_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if self._scene == DialogueScene.ASK_EXPIRY:
            self._build_expiry_readout()
            return
        self._expiry_read_spin = None
        self._expiry_read_value = None
        self._expiry_confirm_btn = None
        if self._scene == DialogueScene.ASK_SCOPE:
            opts = SCOPE_OPTIONS
            selected = self._scope_label
            handler = self._on_scope_hint
            confirm_text = "확인했어요"
            confirm_handler = self._on_scope_confirm
        else:
            self._chips_host.hide()
            return
        for label, _val, rec in opts:
            text = f"{label}    · 권장" if rec else label
            is_sel = selected == label
            if is_sel:
                chip_name = "dlgChipRec"
            elif rec and selected is None:
                chip_name = "dlgChipRec"
            else:
                chip_name = "dlgChip"
            btn = QPushButton(text)
            btn.setObjectName(chip_name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(44)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            btn.clicked.connect(lambda _=False, lab=label: handler(lab))
            self._chips_lay.addWidget(btn)
        confirm = QPushButton(confirm_text)
        confirm.setObjectName("dlgPrimary")
        confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm.setMinimumHeight(46)
        confirm.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        confirm.clicked.connect(confirm_handler)
        self._chips_lay.addWidget(confirm)
        self._chips_host.show()
        self._chips_host.raise_()

    def _build_expiry_readout(self) -> None:
        """Green box + optional spinner + single 「골랐어요」."""
        card = QFrame()
        card.setObjectName("dlgExpiryRead")
        card.setMinimumHeight(52)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(10)
        spin = QLabel("●○○")
        spin.setObjectName("dlgExpiryReadSpin")
        spin.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        val = QLabel("")
        val.setWordWrap(True)
        row.addWidget(spin, 0)
        row.addWidget(val, 1)
        self._expiry_read_spin = spin
        self._expiry_read_value = val
        self._chips_lay.addWidget(card)
        confirm = QPushButton("골랐어요")
        confirm.setObjectName("dlgPrimary")
        confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm.setMinimumHeight(46)
        confirm.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        confirm.clicked.connect(self._on_expiry_confirm)
        self._expiry_confirm_btn = confirm
        self._chips_lay.addWidget(confirm)
        self._chips_host.show()
        self._chips_host.raise_()
        self._refresh_expiry_readout()

    def _refresh_expiry_readout(self) -> None:
        """Update green-box text/spinner without rebuilding the whole card."""
        spin = self._expiry_read_spin
        val = self._expiry_read_value
        btn = self._expiry_confirm_btn
        if spin is None or val is None:
            return
        detected = (self._expiry_label or "").strip()
        if self._expiry_scanning:
            spin.show()
            if detected:
                val.setObjectName("dlgExpiryReadHint")
                val.setText(f"{detected}  ·  새 만료일 확인 중…")
            else:
                val.setObjectName("dlgExpiryReadHint")
                val.setText("만료일을 읽는 중…")
            if not self._dot_timer.isActive():
                self._dot_timer.start()
        else:
            spin.hide()
            if detected:
                val.setObjectName("dlgExpiryReadValue")
                val.setText(detected)
            else:
                val.setObjectName("dlgExpiryReadHint")
                val.setText("만료일을 읽는 중…")
            # Stop dots if login/auth wait is not also active.
            if self._scene not in (
                DialogueScene.LOGIN_WAIT,
                DialogueScene.AUTH_WAIT,
            ):
                self._dot_timer.stop()
        # Force style refresh after objectName change
        val.style().unpolish(val)
        val.style().polish(val)
        if btn is not None:
            btn.setEnabled(bool(self._expires_at or self._expiry_label))

    def _show_expiry_spinner_if_pending(self, gen: int) -> None:
        """Show spinner only if OCR is still running (avoids flash on fast hits)."""
        if gen != self._expiry_scan_gen:
            return
        if self._done or not self._addr_poll_busy:
            return
        if self._scene != DialogueScene.ASK_EXPIRY:
            return
        if not self._expiry_scanning:
            self._expiry_scanning = True
            self._refresh_expiry_readout()

    def _rebuild_receipt(self) -> None:
        while self._done_lay.count():
            item = self._done_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        scope_disp = "repo" if (self._scope_label or "").startswith("저장소만") else "repo · workflow"
        rows = (
            ("권한", scope_disp),
            ("만료", self._expiry_label or "—"),
        )
        for k, v in rows:
            card = QFrame()
            card.setObjectName("dlgReceipt")
            rl = QHBoxLayout(card)
            rl.setContentsMargins(14, 11, 14, 11)
            kl = QLabel(k)
            kl.setObjectName("dlgSub")
            vl = QLabel(v)
            vl.setStyleSheet(_ss(_c_title(), size="12px", mono=True))
            rl.addWidget(kl)
            rl.addStretch(1)
            rl.addWidget(vl)
            self._done_lay.addWidget(card)
        go = QPushButton("클론업으로 돌아가기")
        go.setObjectName("dlgPrimary")
        go.setDefault(True)
        go.clicked.connect(self._finish_accept)
        self._done_lay.addWidget(go)

    def _tick_dots(self) -> None:
        self._wait_dot_i = (self._wait_dot_i + 1) % 3
        dots = ["●○○", "○●○", "○○●"][self._wait_dot_i]
        self._wait_dots.setText(dots)
        spin = self._expiry_read_spin
        if spin is not None and self._expiry_scanning and spin.isVisible():
            spin.setText(dots)
        nspin = getattr(self, "_nudge_spin", None)
        if (
            nspin is not None
            and self._scene == DialogueScene.PRESS_GENERATE
            and nspin.isVisible()
        ):
            nspin.setText(dots)

    # --- chip / history handlers ---
    def _on_history_change(self, target: DialogueScene) -> None:
        if target == DialogueScene.ASK_SCOPE:
            # Re-picking scopes reloads URL — clear expiry (it will reset).
            self._expires_at = None
            self._expiry_label = None
            self._expiry_hint = None
            self._last_expiry_days_read = None
            self._expiry_uia_ok = False
            self._expiry_uia_tries = 0
            self._expiry_scanning = False
        if target == DialogueScene.ASK_EXPIRY:
            self._expires_at = None
            self._expiry_hint = None
            self._last_expiry_days_read = None
            self._expiry_uia_ok = False
            self._expiry_uia_tries = 0
            self._expiry_scanning = True
        self._set_scene(target)

    def _on_expiry_confirm(self) -> None:
        """User confirmed the detected Expiration — then Generate."""
        if self._apply_expiry_from_browser(force_advance=True):
            return
        if self._expires_at and self._last_expiry_days_read:
            label = (
                expiry_label_for_days(self._last_expiry_days_read)
                or self._expiry_label
                or self._last_expiry_days_read
            )
            self._expiry_label = label
            self._guide_log(
                f"[Path B] 만료 확인(감지값 사용): {self._last_expiry_days_read} "
                f"→ {label} → {self._expires_at}"
            )
            self._set_scene(DialogueScene.PRESS_GENERATE)
            return
        self._sub.setText(
            "아직 만료일을 못 읽었어요. 브라우저에서 Expiration을 고른 뒤 "
            "다시 「골랐어요」를 눌러 주세요."
        )
        self._guide_log("[Path B] 만료 확인 실패 — 감지값 없음")

    def _store_expiry_detection(
        self,
        got: str,
        detail: str,
        *,
        source: str,
        advance: bool,
    ) -> bool:
        """
        Reflect browser Expiration into guide state and (when advancing) scene.

        Always updates ``_expires_at`` so login can save it. Logs on change.
        Avoids full ``_render`` / ``adjustSize`` on unchanged polls.
        """
        label = expiry_label_for_days(got) or self._expiry_label or (
            f"{got}일" if str(got).isdigit() else str(got)
        )
        expires = expires_at_for_days(got)
        changed = (
            got != self._last_expiry_days_read
            or self._expires_at != expires
            or self._expiry_label != label
        )
        self._last_expiry_days_read = got
        self._expiry_label = label
        self._expires_at = expires
        self._expiry_uia_ok = True
        if changed:
            short = detail
            if len(short) > 160:
                short = short[:160] + "…"
            self._guide_log(
                f"[Path B] 만료 감지({source}): {got} → {label} → {expires}"
                + (f" ({short})" if short else "")
            )
            if self._scene == DialogueScene.ASK_EXPIRY and not advance:
                # Update green box in place (no full rebuild — keeps spinner smooth).
                self._refresh_expiry_readout()
                self.adjustSize()
            else:
                self._sub.setText(
                    f"브라우저에서 읽은 만료일: {label}. "
                    + (
                        "다음으로 넘어갑니다…"
                        if advance
                        else "맞으면 「골랐어요」를 눌러 주세요."
                    )
                )
        if advance:
            self._guide_log(f"[Path B] 만료 확정·저장: {got} → {expires}")
            self._set_scene(DialogueScene.PRESS_GENERATE)
            return True
        return False

    def _apply_expiry_from_browser(self, *, force_advance: bool) -> bool:
        """
        Sync read Expiration (UI thread). Screenshot+OCR first, UIA fallback.
        Prefer background poll for detect; confirm uses this for a fresh snapshot.
        """
        got, detail = None, ""
        try:
            from app.util.expiry_ocr import read_token_expiration_ocr

            got, detail = read_token_expiration_ocr()
            detail = f"ocr:{detail}"
        except Exception as e:
            detail = f"ocr-error:{e}"
        if got is None:
            try:
                uia_got, uia_detail = read_token_expiration_uia()
                detail = f"{detail}|uia:{uia_detail}"
                got = uia_got
            except Exception as e:
                detail = f"{detail}|uia-error:{e}"
        if got is None:
            if force_advance:
                self._guide_log(f"[Path B] 만료 읽기 실패: {detail}")
            return False
        hint_days = (
            expiry_days_value(self._expiry_hint)
            if self._expiry_hint
            else None
        )
        advance = bool(force_advance) or (
            hint_days is not None and got == hint_days
        )
        return self._store_expiry_detection(
            got,
            detail,
            source="confirm" if force_advance else "read",
            advance=advance,
        )

    def _on_scope_hint(self, label: str) -> None:
        """Hint chip — soft URL prefill only; no auto checkbox clicking."""
        self._scope_label = label
        self._guide_log(f"[Path B] 권한 힌트: {label}")
        # Soft help: reopen create URL so GitHub pre-checks scopes in the query.
        self._open_token_create_page()
        self._sub.setText(
            f"페이지를 다시 열었어요 ({label}). "
            "Select scopes 체크를 확인한 뒤 「확인했어요」를 눌러 주세요."
        )
        self._rebuild_chips()

    def _on_scope_confirm(self) -> None:
        """User confirmed scopes — then Expiration (URL reload resets expiry)."""
        if not self._scope_label:
            self._scope_label = "저장소만"
        self._guide_log(f"[Path B] 권한 확인: {self._scope_label}")
        # Ensure create URL matches chosen scopes (reloads form → fresh Expiration).
        self._open_token_create_page()
        # Clear any prior expiry read — page just reloaded.
        self._expires_at = None
        self._expiry_label = None
        self._expiry_hint = None
        self._last_expiry_days_read = None
        self._expiry_uia_ok = False
        self._expiry_scanning = True
        self._set_scene(DialogueScene.ASK_EXPIRY)

    def _open_token_create_page(self) -> None:
        """Open classic tokens/new with Note (+ optional scopes query prefill)."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        scopes = scope_query_value(self._scope_label or "저장소만")
        url, note = build_pat_create_url_with_note(scopes=scopes)
        self._pat_note = note
        self._create_url = url
        self._last_family_url = url
        self._token_nav_opened = True
        QDesktopServices.openUrl(QUrl(url))
        self._guide_log(f"[Path B] 키 만들기 URL 오픈 note={note}")

    def _wanted_expiry_days(self) -> str:
        if self._last_expiry_days_read:
            return self._last_expiry_days_read
        return expiry_days_value(self._expiry_hint or self._expiry_label or "90일")

    def _assist_busy(self) -> bool:
        w = self._assist_worker
        return w is not None and w.isRunning()

    def _set_nudge_busy(self, busy: bool, *, status: str = "") -> None:
        """Update yellow Generate status strip while auto-assist runs."""
        try:
            if busy:
                self._generate_auto_started = True
                self._nudge_spin.show()
                if not self._dot_timer.isActive():
                    self._dot_timer.start()
                self._nudge_text.setText(
                    status or "Generate token 버튼을 찾고 있어요"
                )
            else:
                if status:
                    self._nudge_text.setText(status)
        except Exception:
            pass
        if status and self._scene == DialogueScene.PRESS_GENERATE:
            # Keep main sub quieter; yellow strip carries the live status.
            pass
        elif status:
            self._sub.setText(status)

    def _assist_guide_aside(self, aside: bool) -> None:
        """Dim StayOnTop card so UIA/coordinate clicks hit the browser, not us."""
        if aside == self._assist_aside:
            return
        self._assist_aside = aside
        try:
            if aside:
                self.setWindowOpacity(0.25)
            else:
                self.setWindowOpacity(_GUIDE_OPACITY)
        except Exception:
            pass

    def _start_assist_worker(
        self,
        op: str,
        *,
        days: str | None = None,
        skip_expiry: bool = False,
    ) -> bool:
        """Start background CDP/UIA assist. Returns False if already busy."""
        if self._assist_busy():
            return False
        worker = PathBAssistWorker(
            op,
            days=days,
            skip_expiry=skip_expiry,
            parent=self,
        )
        worker.finished_result.connect(self._on_assist_finished)
        self._assist_worker = worker
        if op in ("nudge", "generate", "expiry"):
            self._assist_guide_aside(True)
        worker.start()
        return True

    def _on_assist_finished(self, op: str, ok: bool, detail: str) -> None:
        """UI-thread slot: apply background assist result."""
        self._assist_guide_aside(False)
        self._set_nudge_busy(False)
        if self._done:
            return

        self._nudge_pending = False

        if op == "wait_ready":
            if ok:
                self._guide_log("[Path B][CDP] 포트 준비됨 — Expiration 재시도")
                self._sub.setText(
                    "제어용 브라우저가 연결됐습니다. "
                    "키 만들기 페이지가 보이면 Expiration을 맞춰 볼게요."
                )
                self._expiry_uia_ok = False
                self._schedule_expiry_invoke_tries()
            else:
                self._guide_log("[Path B][CDP] 포트 미응답 — UIA/수동으로 진행")
                self._sub.setText(
                    "제어용 브라우저 포트가 아직 안 열렸습니다. "
                    "페이지가 뜬 뒤 Expiration을 직접 맞춰 주세요."
                )
            self._render()
            return

        if op == "expiry":
            if ok:
                self._expiry_uia_ok = True
                exp = self._expiry_label or "90일"
                self._sub.setText(
                    f"Expiration을 {exp}으로 맞춰 봤어요. "
                    "Generate token을 눌러 주세요."
                )
            elif self._expiry_uia_tries >= 3:
                exp = self._expiry_label or "90일"
                self._set_user_status(
                    f"만료일을 자동으로 바꾸지 못했어요. "
                    f"브라우저에서 Expiration을 「{exp}」으로 직접 고른 뒤 "
                    "Generate token을 눌러 주세요.",
                    detail=f"[Path B] Expiration 자동 맞춤 포기: {detail}",
                )
            return

        if op == "nudge":
            self._generate_auto_started = False
            if ok:
                self._expiry_uia_ok = True
                self._set_nudge_busy(
                    False,
                    status="Generate를 눌렀어요. 키가 나오면 받아올게요.",
                )
                self._sub.setText(
                    "Generate token을 눌렀어요. 키가 화면에 나오면 받아올게요."
                )
                return
            # Do NOT reopen tokens/new — that wipes the user's Expiration.
            # Send them back to ASK_EXPIRY so they can re-confirm the same value.
            self._guide_log(
                f"[Path B] Generate 실패 → 만료일 단계로 복귀 ({detail})"
            )
            self._expiry_uia_ok = False
            self._expiry_scanning = True
            # Keep _last_expiry_days_read / _expires_at / _expiry_label.
            detected = (self._expiry_label or "").strip()
            self._set_scene(DialogueScene.ASK_EXPIRY)
            self._set_user_status(
                self._friendly_generate_miss(detected=detected, detail=detail),
                detail="",  # already logged above
            )
            return

        if op == "generate" and ok:
            self._generate_auto_started = False
            self._set_user_status(
                "Generate token을 눌렀어요. 키가 화면에 나오면 받아올게요.",
                detail=f"[Path B] Generate 성공: {detail}",
            )

    def _schedule_expiry_invoke_tries(self) -> None:
        """Retry expiry assist a few times while the form loads (async)."""
        self._expiry_uia_tries = 0
        for delay_ms in (1200, 2800, 5000):
            QTimer.singleShot(delay_ms, self._try_apply_expiry_invoke)

    def _try_apply_expiry_invoke(self) -> None:
        """Queue Expiration assist on a worker (CDP then UIA)."""
        if self._done or self._scene != DialogueScene.PRESS_GENERATE:
            return
        if self._expiry_uia_ok:
            return
        if self._assist_busy():
            return
        want = self._wanted_expiry_days()
        # Fast read-only check on UI thread (no Playwright).
        got, _read = read_token_expiration_uia()
        if got is not None and got == want:
            self._expiry_uia_ok = True
            exp = self._expiry_label or "90일"
            self._guide_log(f"[Path B] Expiration 이미 일치(읽기): {got}")
            self._sub.setText(
                f"Expiration이 이미 {exp}입니다. Generate token만 눌러 주세요."
            )
            return
        self._expiry_uia_tries += 1
        if not self._start_assist_worker("expiry", days=want):
            self._expiry_uia_tries = max(0, self._expiry_uia_tries - 1)

    def _on_launch_cdp_browser(self) -> None:
        """Open CloneUp-owned Chrome/Edge with --remote-debugging-port."""
        from app.util.browser_cdp import (
            cdp_enabled,
            launch_cdp_browser,
            probe_cdp_endpoint,
        )

        if not cdp_enabled():
            self._sub.setText(
                "직접 제어는 CLONEUP_CDP=1 과 Playwright가 필요합니다."
            )
            return
        # Quick probe (short timeout) — if already up, skip launch.
        if probe_cdp_endpoint(timeout_s=0.4) is not None:
            self._sub.setText(
                "제어용 브라우저가 이미 연결되어 있습니다. Expiration을 다시 맞춰 볼게요."
            )
            self._schedule_expiry_invoke_tries()
            self._render()
            return
        start = self._create_url or "https://github.com/login"
        ok, detail = launch_cdp_browser(start_url=start)
        if ok:
            self._guide_log(f"[Path B][CDP] 기동: {detail}")
            self._sub.setText(
                "제어용 브라우저를 여는 중… 포트가 준비되면 Expiration을 맞춰 볼게요."
            )
            QTimer.singleShot(300, self._after_cdp_launch_wait)
        else:
            self._set_user_status(
                "제어용 브라우저를 열지 못했어요. "
                "브라우저에서 Expiration을 직접 맞춘 뒤 Generate token을 눌러 주세요.",
                detail=f"[Path B][CDP] 기동 실패: {detail}",
            )
        self._render()

    def _after_cdp_launch_wait(self) -> None:
        """After launch: wait for CDP port on a worker, then retry Expiration."""
        if self._done or self._scene != DialogueScene.PRESS_GENERATE:
            return
        if not self._start_assist_worker("wait_ready"):
            self._sub.setText("다른 자동 맞춤이 끝나길 기다린 뒤 다시 시도해 주세요.")

    def _auto_generate_assist(self) -> None:
        """PRESS_GENERATE entered → find/click Generate automatically.

        Yellow strip shows a spinner + 「Generate token 버튼을 찾고 있어요」.
        No 「도와주세요」 button — less nagging, Toss-like progress.
        """
        if self._done or self._scene != DialogueScene.PRESS_GENERATE:
            return
        if self._assist_busy():
            self._set_nudge_busy(
                True,
                status="Generate token 버튼을 찾고 있어요",
            )
            return
        if self._generate_auto_started and self._got_token:
            return
        self._guide_log("[Path B] Generate 자동 시도")
        want = self._wanted_expiry_days()
        # Skip expiry mutate when user already confirmed on ASK_EXPIRY.
        skip = bool(
            self._expiry_uia_ok
            or self._last_expiry_days_read
            or self._expires_at
        )
        self._nudge_pending = False
        self._generate_auto_started = True
        self._set_nudge_busy(
            True,
            status="Generate token 버튼을 찾고 있어요",
        )
        if not self._start_assist_worker(
            "nudge", days=want, skip_expiry=skip
        ):
            self._generate_auto_started = False
            self._set_nudge_busy(
                False,
                status="잠시 후 다시 Generate를 찾아볼게요…",
            )
            QTimer.singleShot(800, self._auto_generate_assist)

    def _reopen_github_login(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(_GITHUB_LOGIN))
        self._last_family_url = _GITHUB_LOGIN
        self._google_blocked = False
        self._render()

    # --- polling ---
    def _sync_poll_interval(self) -> None:
        """Faster ticks while watching Expiration; normal otherwise."""
        want = (
            _EXPIRY_POLL_MS
            if (
                self._scene == DialogueScene.ASK_EXPIRY
                and self._token_nav_opened
            )
            else _ADDR_POLL_MS
        )
        if self._addr_timer.interval() != want:
            self._addr_timer.setInterval(want)

    def _poll_address(self) -> None:
        """Kick a background sample/OCR — never block the Qt UI thread."""
        if self._done or self._addr_poll_busy:
            return
        w = self._addr_worker
        if w is not None and w.isRunning():
            return
        self._sync_poll_interval()
        self._addr_poll_busy = True
        on_expiry = (
            self._scene == DialogueScene.ASK_EXPIRY and self._token_nav_opened
        )
        if on_expiry:
            self._expiry_poll_i += 1
            # Most ticks: OCR only. Every 3rd: also UIA sample for login bounce.
            sample_address = (self._expiry_poll_i % 3) == 0
            read_expiry = True
            # If a value is already shown, arm a delayed spinner so slow OCR
            # re-reads don't feel like a hard cut when the user changes Expiration.
            if self._expiry_label:
                self._expiry_scan_gen += 1
                gen = self._expiry_scan_gen
                QTimer.singleShot(
                    180, lambda g=gen: self._show_expiry_spinner_if_pending(g)
                )
        else:
            sample_address = True
            read_expiry = False
        worker = PathBAddressWorker(
            read_expiry=read_expiry,
            sample_address=sample_address,
            parent=self,
        )
        worker.sample_ready.connect(self._on_address_sample)
        self._addr_worker = worker
        worker.start()

    def _on_address_sample(self, payload: object) -> None:
        self._addr_poll_busy = False
        self._addr_worker = None
        # Cancel pending spinner; clear scanning after we apply the result.
        self._expiry_scan_gen += 1
        if self._done:
            self._expiry_scanning = False
            return
        try:
            sample = payload
            expiry_days = None
            expiry_detail = ""
            if isinstance(payload, dict):
                sample = payload.get("sample")
                expiry_days = payload.get("expiry_days")
                expiry_detail = str(payload.get("expiry_detail") or "")
            # Peek page kind: token *list* OCR must not fill Expiration chip.
            on_token_list = False
            if sample is not None:
                try:
                    _k, _i, _m = classify_browser_sample(
                        getattr(sample, "url", "") or "",
                        window_title=getattr(sample, "window_title", "") or "",
                        ui_text=getattr(sample, "ui_text", "") or "",
                    )
                    on_token_list = str((_m or {}).get("method") or "") == "token_list"
                except Exception:
                    on_token_list = False
            # Apply Expiration detection before scene classify so ASK_EXPIRY
            # can store/reflect even when the tab sample is briefly away.
            if self._scene == DialogueScene.ASK_EXPIRY and self._token_nav_opened:
                self._expiry_scanning = False
                if on_token_list:
                    # List rows say "no expiration" / "Expires on…" — ignore.
                    self._refresh_expiry_readout()
                elif expiry_days:
                    # Reflect only — user confirms with 「골랐어요」.
                    self._store_expiry_detection(
                        str(expiry_days),
                        expiry_detail,
                        source="poll",
                        advance=False,
                    )
                    self._refresh_expiry_readout()
                elif expiry_detail:
                    self._refresh_expiry_readout()
                    # Cross-check visibility: leave a trail when read fails.
                    import time as _time

                    now = _time.monotonic()
                    if now - self._expiry_miss_log_at >= 8.0:
                        self._expiry_miss_log_at = now
                        self._guide_log(
                            f"[Path B] 만료 미감지(poll): {expiry_detail}"
                        )
                        self._sub.setText(
                            "만료일을 아직 못 읽었어요. "
                            "키 만들기 창이 보이도록 둔 뒤 잠시 기다려 주세요."
                        )
            self._poll_address_inner(sample)
        except Exception as e:
            self._guide_log(f"[Path B] 주소 폴링 오류: {e}")

    def _poll_address_inner(self, sample: object) -> None:
        if sample is None:
            return
        url = getattr(sample, "url", "") or ""
        title = getattr(sample, "window_title", "") or ""
        ui = getattr(sample, "ui_text", "") or ""
        if is_github_flow_family_url(url):
            self._last_family_url = url

        kind, idx, meta = classify_browser_sample(
            url, window_title=title, ui_text=ui
        )
        method = str((meta or {}).get("method") or "")

        # Passkey / Hello sheet can stay open while the user clicks YouTube.
        # Prefer OS HWND over the "away" Chromium tab so AUTH_WAIT does not drop.
        if method != "passkey" and kind in ("away", "unknown", "current"):
            try:
                from app.util.browser_address import find_passkey_os_hwnd

                pk_hwnd, pk_title = find_passkey_os_hwnd()
            except Exception:
                pk_hwnd, pk_title = 0, ""
            if pk_hwnd:
                kind, idx = "current", 0
                method = "passkey"
                meta = dict(meta or {})
                meta["method"] = "passkey"
                meta["os_passkey"] = pk_title or "Windows 보안"
                title = meta["os_passkey"]
                ui = ui or "passkey|os-enum"

        # Wrong-tab recovery: StayOnTop guide often leaves a non-GitHub Chrome
        # window ranked first. Re-open once so the GitHub tab comes forward.
        # Also: /settings/tokens LIST is not the create form — reopen /new.
        on_token_steps = (
            self._scene in (DialogueScene.ASK_SCOPE, DialogueScene.ASK_EXPIRY)
            and self._token_nav_opened
        )
        # During login/auth, soft-away (YouTube) must not reopen login and
        # kill an in-progress passkey / Apple sheet.
        auth_sticky = self._scene in (
            DialogueScene.LOGIN_WAIT,
            DialogueScene.AUTH_WAIT,
        ) and (
            method in (
                "passkey",
                "apple",
                "github_2fa",
                "github_mobile",
                "github_totp",
                "github_recovery",
                "google",
            )
            or bool(self._auth_method)
        )
        if kind in ("away", "unknown") or (
            on_token_steps and method == "token_list"
        ):
            if auth_sticky and kind in ("away", "unknown"):
                # Keep AUTH_WAIT / passkey copy; nudge without resetting.
                self._away_streak = 0
                if self._scene == DialogueScene.AUTH_WAIT:
                    self._sub.setText(
                        "브라우저에서 다른 탭을 보고 계신 것 같아요. "
                        "패스키·인증 창이 있으면 그 창에서 이어서 확인해 주세요."
                    )
                elif self._auth_method:
                    # Had started auth — park on AUTH_WAIT instead of reopening.
                    self._set_scene(DialogueScene.AUTH_WAIT)
                    self._sub.setText(
                        "인증이 아직 끝나지 않았어요. "
                        "패스키·이메일 확인 창으로 돌아가 주세요."
                    )
                return
            if self._scene == DialogueScene.LOGIN_WAIT and kind in (
                "away",
                "unknown",
            ):
                self._away_streak += 1
                if self._away_streak >= 2 and not self._login_rescue_done:
                    self._login_rescue_done = True
                    self._guide_log(
                        f"[Path B] GitHub 창 미검출({kind}) → 로그인 페이지 재오픈 "
                        f"sample={(title or '')[:40]!r}"
                    )
                    self._reopen_github_login()
                    self._sub.setText(
                        "GitHub 로그인 화면을 다시 열었어요. "
                        "브라우저에서 로그인해 주세요."
                    )
                return
            if on_token_steps:
                self._away_streak += 1
                # List page is a clear miss — reopen sooner than vague away.
                need = 1 if method == "token_list" else 2
                if self._away_streak >= need:
                    self._away_streak = 0
                    why = (
                        "키 목록(/settings/tokens)"
                        if method == "token_list"
                        else f"키 만들기 탭 미검출({kind})"
                    )
                    self._guide_log(f"[Path B] {why} → 만들기 페이지 재오픈")
                    self._open_token_create_page()
                    if self._scene == DialogueScene.ASK_SCOPE:
                        self._sub.setText(
                            "지금은 키 목록 화면이에요. "
                            "키 만들기 페이지를 다시 열었어요. "
                            "Select scopes를 확인해 주세요."
                            if method == "token_list"
                            else (
                                "키 만들기 페이지를 다시 열었어요. "
                                "Select scopes를 확인해 주세요."
                            )
                        )
                    else:
                        self._expiry_scanning = True
                        # Clear stale OCR from list rows (e.g. "no expiration").
                        if method == "token_list":
                            self._last_expiry_days_read = None
                            self._expiry_label = None
                            self._expires_at = None
                        self._sub.setText(
                            "지금은 키 목록 화면이에요. "
                            "키 만들기 페이지를 다시 열었어요. "
                            "브라우저에서 Expiration을 골라 주세요."
                            if method == "token_list"
                            else (
                                "키 만들기 페이지를 다시 열었어요. "
                                "브라우저에서 Expiration을 골라 주세요."
                            )
                        )
                        self._refresh_expiry_readout()
                return
        self._away_streak = 0

        if kind == "rejected" or method == "google_blocked":
            if not self._google_blocked:
                self._guide_log("[Path B] Google 로그인 차단 감지")
            self._google_blocked = True
            if self._scene == DialogueScene.LOGIN_WAIT:
                self._render()
            return

        # Visible PAT / issued banner while waiting for generate
        if self._scene == DialogueScene.PRESS_GENERATE:
            visible = (meta or {}).get("visible_pat")
            if visible and _looks_like_token(str(visible)):
                self._ingest_token(str(visible), source="화면에서 키를 읽었어요")
                return
            if kind == "reached" and idx == 3:
                # issued page — clipboard poll will catch copy; keep waiting
                pass

        if kind == "token_error":
            # Note collision — open fresh note URL
            self._open_token_create_page()
            self._sub.setText("Note 이름이 겹쳐 새 이름으로 다시 열었어요.")
            return

        nxt = advance_from_browser_kind(
            self._scene, kind, idx, method=method
        )

        # Update AUTH_WAIT copy even when the scene does not change.
        if method in (
            "passkey",
            "github_2fa",
            "github_mobile",
            "github_totp",
            "github_recovery",
            "apple",
            "google",
        ):
            if method != self._auth_method:
                self._auth_method = method
                label = {
                    "passkey": "패스키(Windows 보안·Use passkey)",
                    "github_2fa": "이메일 인증(Verify your device)",
                    "github_mobile": "GitHub Mobile 승인",
                    "github_totp": "인증 앱(OTP)",
                    "github_recovery": "복구 코드(2FA recovery)",
                    "apple": "Apple",
                    "google": "Google",
                }.get(method, method)
                self._guide_log(f"[Path B] 인증 화면 감지: {label}")
                if self._scene == DialogueScene.AUTH_WAIT:
                    self._render()
                    self.adjustSize()

        if nxt is None:
            return
        prev = self._scene

        if nxt == DialogueScene.LOGIN_WAIT and prev != DialogueScene.LOGIN_WAIT:
            self._logged_in = False
            self._auth_done = False
            self._auth_method = ""
            self._expiry_label = None
            self._expiry_hint = None
            self._scope_label = None
            self._expires_at = None
            self._last_expiry_days_read = None
            self._token_nav_opened = False
            self._got_token = False
            self._expiry_uia_ok = False
            self._expiry_uia_tries = 0
            self._login_rescue_done = False
            self._away_streak = 0
            self._guide_log("[Path B] 로그인 화면으로 돌아감 — 인증·키 단계 초기화")

        if nxt == DialogueScene.AUTH_WAIT:
            self._logged_in = True
            self._auth_done = False
            self._google_blocked = False
            if method in (
                "passkey",
                "github_2fa",
                "github_mobile",
                "github_totp",
                "github_recovery",
                "apple",
                "google",
            ):
                self._auth_method = method
            # Do NOT open tokens/new here — unfinished email/passkey bounces back.
            if self._token_nav_opened or int(prev) >= int(DialogueScene.ASK_SCOPE):
                self._token_nav_opened = False
                self._expiry_label = None
                self._expiry_hint = None
                self._scope_label = None
                self._expires_at = None
                self._last_expiry_days_read = None
                self._guide_log(
                    "[Path B] 이메일·패스키 인증 필요 — 키 만들기 단계 보류 "
                    f"(from={prev.name}, method={method or kind})"
                )
            elif prev == DialogueScene.LOGIN_WAIT:
                self._guide_log(
                    f"[Path B] 인증 단계 진입 (method={method or kind})"
                )
            try:
                self.raise_()
            except Exception:
                pass

        if nxt == DialogueScene.ASK_SCOPE:
            self._logged_in = True
            self._auth_done = True
            self._google_blocked = False
            self._login_rescue_done = False
            # Open tokens/new here (scopes). Expiration comes after confirm.
            if not self._token_nav_opened:
                self._guide_log(
                    "[Path B] 인증 완료 → 키 만들기 페이지 오픈 (권한 먼저)"
                )
                try:
                    self._open_token_create_page()
                except Exception as e:
                    self._guide_log(f"[Path B] 키 만들기 페이지 오픈 실패: {e}")
            try:
                self.raise_()
            except Exception:
                pass

        if nxt == DialogueScene.ASK_EXPIRY:
            self._logged_in = True
            self._auth_done = True
            self._google_blocked = False
            self._expiry_scanning = True  # OCR after scope URL is stable
            try:
                self.raise_()
            except Exception:
                pass

        # Always advance scene even if URL open failed — otherwise LOGIN_WAIT sticks.
        self._set_scene(nxt)

    def _poll_clipboard(self) -> None:
        if self._done:
            return
        if self._scene not in (
            DialogueScene.PRESS_GENERATE,
            DialogueScene.DONE,
        ):
            return
        clip = QGuiApplication.clipboard()
        if clip is None:
            return
        text = (clip.text() or "").strip()
        self._ingest_token(text, source="클립보드에서 키를 인식했어요")

    def _on_edit_text(self, text: str) -> None:
        if _looks_like_token(text):
            self._ingest_token(text, source="키를 인식했어요")

    def _ingest_token(self, text: str, *, source: str) -> None:
        tok = (text or "").strip()
        if not _looks_like_token(tok) or tok == self._clip_seen:
            return
        if self._done:
            return
        self._clip_seen = tok
        self._edit.blockSignals(True)
        self._edit.setText(tok)
        self._edit.blockSignals(False)
        self._token = tok
        self._got_token = True
        self._guide_log(f"[Path B] 키 인식: {source}")
        try:
            self.raise_()
            # activateWindow only when connecting — safe to take focus briefly.
            self.activateWindow()
        except Exception:
            pass
        self._set_scene(DialogueScene.DONE)
        # Brief DONE flash then accept (auto-connect product path)
        QTimer.singleShot(400, self._finish_accept)

    def _finish_accept(self) -> None:
        raw = self.token()
        if not _looks_like_token(raw):
            return
        self._guide_log(
            f"[Path B] 연결 진행 (만료={self._expires_at or '—'}, "
            f"note={self._pat_note or '—'})"
        )
        self._stop_timers()
        self._done = True
        self._token = raw
        self.token_accepted.emit(raw)
        self.accept()

    def _on_cancel(self) -> None:
        self._guide_log("[Path B] 사용자가 취소")
        self._stop_timers()
        self._done = True
        self.cancelled.emit()
        self.reject()

    def _stop_timers(self) -> None:
        for t in (self._clip_timer, self._addr_timer, self._dot_timer):
            if t.isActive():
                t.stop()
        for w in (self._assist_worker, self._addr_worker):
            if w is not None:
                if w.isRunning():
                    # Best-effort: do not block the UI long on close.
                    w.wait(600)
        self._assist_worker = None
        self._addr_worker = None
        self._addr_poll_busy = False
        set_path_b_log_sink(None)

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._done:
            self._guide_log("[Path B] 안내 창 닫힘")
        self._stop_timers()
        if not self._done:
            self._done = True
            self.cancelled.emit()
        super().closeEvent(event)
