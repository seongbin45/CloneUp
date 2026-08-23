"""Embedded GitHub WebView for PAT connect + page-stage signals.

Optional: requires PySide6 Qt WebEngine (PySide6-Addons). Callers must
fall back to an external browser when ``webengine_available()`` is False.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, QUrl, Signal, Slot
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from app.auth.github_page_stage import (
    GitHubPageStage,
    PageSnapshot,
    detect_github_page_stage,
    stage_label_ko,
)

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


class GitHubConnectWebPane(QWidget):
    """
    QWebEngineView that emits stage / optional token detections.

    Parent owns layout chrome (labels, connect button).
    """

    stage_changed = Signal(object)  # GitHubPageStage
    url_changed = Signal(str)
    token_found = Signal(str)
    load_failed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWebEngineCore import QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._stage = GitHubPageStage.UNKNOWN
        self._reached: set[GitHubPageStage] = set()
        self._last_token = ""

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
        try:
            self._view.page().profile().setHttpUserAgent(_CHROME_UA)
        except Exception:
            try:
                QWebEngineProfile.defaultProfile().setHttpUserAgent(_CHROME_UA)
            except Exception:
                pass

        self._view.urlChanged.connect(self._on_url)
        self._view.titleChanged.connect(self._on_title)
        self._view.loadFinished.connect(self._on_loaded)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._view, 1)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(960, 560)

    @property
    def stage(self) -> GitHubPageStage:
        return self._stage

    @property
    def reached(self) -> set[GitHubPageStage]:
        return set(self._reached)

    def load_url(self, url: str) -> None:
        self._view.setUrl(QUrl(url))

    def open_external_fallback(self, url: str) -> None:
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(url))

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
        self.url_changed.emit(url.toString())
        self._refresh_stage()

    @Slot(str)
    def _on_title(self, _title: str) -> None:
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
        self._refresh_stage(html=html or "")

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
