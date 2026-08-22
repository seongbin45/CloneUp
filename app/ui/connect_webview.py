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

_CHECKLIST_ORDER: tuple[GitHubPageStage, ...] = (
    GitHubPageStage.LOGIN,
    GitHubPageStage.AUTH_2FA,
    GitHubPageStage.TOKEN_CLASSIC_NEW,
    GitHubPageStage.TOKEN_ISSUED,
)

_CHECKLIST_LABEL: dict[GitHubPageStage, str] = {
    GitHubPageStage.LOGIN: "로그인",
    GitHubPageStage.AUTH_2FA: "인증 코드",
    GitHubPageStage.TOKEN_CLASSIC_NEW: "키 만들기",
    GitHubPageStage.TOKEN_ISSUED: "키 복사",
}


def webengine_available() -> bool:
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

        return True
    except Exception:
        return False


def guide_line_for_stage(stage: GitHubPageStage) -> str:
    """One beginner-friendly line for the current page."""
    return {
        GitHubPageStage.LOGIN: "GitHub에 로그인해 주세요. (패스키가 안 되면 비밀번호를 쓰세요.)",
        GitHubPageStage.AUTH_2FA: "인증 앱 또는 이메일로 받은 코드를 입력해 주세요.",
        GitHubPageStage.TOKEN_CLASSIC_NEW: (
            "만료일을 고르고 「repo」가 켜져 있는지 확인한 뒤 "
            "Generate token 을 누르세요."
        ),
        GitHubPageStage.TOKEN_FINE_NEW: (
            "세분 키 화면입니다. 저장소와 Contents 권한을 정한 뒤 키를 만드세요."
        ),
        GitHubPageStage.TOKEN_ISSUED: (
            "초록 키를 복사하세요. 이 화면을 닫으면 다시 볼 수 없습니다."
        ),
        GitHubPageStage.TOKEN_CLASSIC_LIST: (
            "키 목록입니다. Generate new token (classic) 으로 새 키를 만드세요."
        ),
        GitHubPageStage.UNKNOWN: "조금 더 진행해 주세요. 안내가 따라갑니다.",
        GitHubPageStage.AUTH_PASSKEY_OS: (
            "패스키 창이 떴을 수 있습니다. 취소 후 비밀번호로 진행해도 됩니다."
        ),
        GitHubPageStage.SUDO_OR_OTHER: "추가 확인 화면입니다. 안내에 따라 진행해 주세요.",
    }.get(stage, stage_label_ko(stage))


def checklist_text(reached: set[GitHubPageStage], current: GitHubPageStage) -> str:
    """One-line checklist (saves vertical space for the WebView)."""
    parts: list[str] = []
    for st in _CHECKLIST_ORDER:
        mark = "✓" if st in reached else "○"
        label = _CHECKLIST_LABEL[st]
        if st == current:
            parts.append(f"{mark}【{label}】")
        else:
            parts.append(f"{mark} {label}")
    return "  →  ".join(parts)


class GitHubConnectWebPane(QWidget):
    """
    QWebEngineView that emits stage / optional token detections.

    Parent owns layout chrome (labels, connect button).
    """

    stage_changed = Signal(object)  # GitHubPageStage
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
        self._view.setMinimumSize(720, 480)
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.setMinimumSize(720, 480)
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
    def _on_url(self, _url: QUrl) -> None:
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
