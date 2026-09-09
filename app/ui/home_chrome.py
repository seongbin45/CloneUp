"""Phase A chrome: overflow ⋯ menu, Git-missing banner, accessibility shortcuts.

Home IA (desin/CloneUp 홈.dc.html): settings/help/terms/Git version live in ⋯;
Git problems surface as a yellow banner — not an always-on status label.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.paths import app_root
from app.ui.theme import active_palette


def open_terms_dialog(parent: QWidget | None) -> None:
    """Show 이용약관 (same files Settings → 정보 uses)."""
    root = app_root()
    candidates = (
        root / "legal" / "CloneUp_Terms_ko.txt",
        root / "installer" / "license" / "CloneUp_Terms_ko.txt",
        root.parent / "legal" / "CloneUp_Terms_ko.txt",
    )
    text = ""
    for path in candidates:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                break
        except OSError:
            continue
    if not text.strip():
        QMessageBox.information(
            parent,
            "이용약관",
            "이용약관 파일을 찾지 못했습니다.\n설치 시 약관에 동의하셨습니다.",
        )
        return
    # Reuse settings dialog helper shape — simple scroll message box is enough for A.
    box = QMessageBox(parent)
    box.setWindowTitle("이용약관")
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text[:12000] + ("\n…" if len(text) > 12000 else ""))
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


class GitMissingBanner(QFrame):
    """Yellow strip above the main list/tabs when Git is not installed."""

    install_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gitMissingBanner")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        p = active_palette()
        soft = "#f6efdd" if p.name == "light" else "#3a3420"
        self.setStyleSheet(
            f"QFrame#gitMissingBanner {{"
            f" background: {soft}; border: none;"
            f" border-bottom: 1px solid {p.warn_border}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(3)
        title = QLabel("Git이 설치되어 있지 않습니다")
        title.setObjectName("gitMissingBannerTitle")
        title.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {p.text};"
        )
        body = QLabel(
            "받아오기·올리기가 동작하지 않습니다. 설치한 뒤 CloneUp을 다시 열어 주세요."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size: 12px; color: {p.text_muted};")
        col.addWidget(title)
        col.addWidget(body)
        row.addLayout(col, 1)
        btn = QPushButton("설치 방법 보기")
        btn.setObjectName("gitMissingBannerCta")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton#gitMissingBannerCta {{"
            f" background: {p.bg_window}; border: 1px solid {p.warn_border};"
            f" border-radius: 6px; padding: 7px 12px; font-size: 12.5px;"
            f" color: {p.text}; }}"
            f"QPushButton#gitMissingBannerCta:hover {{ background: {p.hover_muted}; }}"
        )
        btn.clicked.connect(self.install_clicked.emit)
        row.addWidget(btn, 0)
        self.hide()

    def refresh_theme(self) -> None:
        p = active_palette()
        soft = "#f6efdd" if p.name == "light" else "#3a3420"
        self.setStyleSheet(
            f"QFrame#gitMissingBanner {{"
            f" background: {soft}; border: none;"
            f" border-bottom: 1px solid {p.warn_border}; }}"
        )


def make_overflow_button(parent: QWidget | None = None) -> QPushButton:
    """31×31-ish ⋯ control for the status row (Phase A) / sidebar (Phase B)."""
    btn = QPushButton("⋯", parent)
    btn.setObjectName("btnOverflowMenu")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(31, 31)
    btn.setToolTip("설정 · 도움말 · Git")
    p = active_palette()
    btn.setStyleSheet(
        f"QPushButton#btnOverflowMenu {{"
        f" background: transparent; border: none; border-radius: 6px;"
        f" font-size: 14px; color: {p.text_secondary}; }}"
        f"QPushButton#btnOverflowMenu:hover {{ background: {p.hover_muted}; }}"
        f"QPushButton#btnOverflowMenu:pressed {{ background: {p.bg_muted}; }}"
    )
    return btn


def populate_overflow_menu(
    menu: QMenu,
    *,
    git_ok: bool,
    git_version: str,
    logged_in: bool,
    on_settings: Callable[[], None],
    on_help: Callable[[], None],
    on_terms: Callable[[], None],
    on_login: Callable[[], None],
    on_logout: Callable[[], None],
    on_git_setup: Callable[[], None] | None = None,
) -> None:
    """Fill ⋯ menu per home IA (settings / help / terms / Git / auth)."""
    menu.clear()
    act_settings = QAction("설정", menu)
    act_settings.setObjectName("actionOverflowSettings")
    act_settings.triggered.connect(on_settings)
    menu.addAction(act_settings)

    act_help = QAction("도움말 · 시작 안내", menu)
    act_help.setObjectName("actionOverflowHelp")
    act_help.triggered.connect(on_help)
    menu.addAction(act_help)

    act_terms = QAction("이용약관", menu)
    act_terms.setObjectName("actionOverflowTerms")
    act_terms.triggered.connect(on_terms)
    menu.addAction(act_terms)

    menu.addSeparator()

    if git_ok:
        act_git = QAction("Git", menu)
        act_git.setObjectName("actionOverflowGit")
        act_git.setEnabled(False)
        hint = (git_version or "").strip() or "확인됨"
        act_git.setText(f"Git  {hint}")
        menu.addAction(act_git)
    else:
        act_git = QAction("Git  없음 — 설치 방법…", menu)
        act_git.setObjectName("actionOverflowGitMissing")
        if on_git_setup is not None:
            act_git.triggered.connect(on_git_setup)
        menu.addAction(act_git)

    menu.addSeparator()

    if logged_in:
        act_auth = QAction("로그아웃", menu)
        act_auth.setObjectName("actionOverflowLogout")
        act_auth.triggered.connect(on_logout)
    else:
        act_auth = QAction("GitHub 로그인", menu)
        act_auth.setObjectName("actionOverflowLogin")
        act_auth.triggered.connect(on_login)
    menu.addAction(act_auth)


def install_chrome_shortcuts(
    window: QWidget,
    *,
    on_settings: Callable[[], None],
    on_help: Callable[[], None],
) -> list[QShortcut]:
    """Ctrl+, → settings; F1 → help (H-2 accessibility)."""
    sc_settings = QShortcut(QKeySequence("Ctrl+,"), window)
    sc_settings.setObjectName("shortcutSettings")
    sc_settings.activated.connect(on_settings)
    sc_help = QShortcut(QKeySequence(Qt.Key.Key_F1), window)
    sc_help.setObjectName("shortcutHelp")
    sc_help.activated.connect(on_help)
    return [sc_settings, sc_help]


def settings_reachable(window: QWidget, main_window_src: str) -> bool:
    """A-0 verify: settings can be opened via button, overflow, or wired handler."""
    if window.findChild(QPushButton, "btnSettings") is not None:
        return True
    if window.findChild(QPushButton, "btnOverflowMenu") is not None:
        return True
    if "show_settings" in main_window_src and "on_settings_menu" in main_window_src:
        return True
    return False


def help_reachable(window: QWidget, main_window_src: str) -> bool:
    if window.findChild(QPushButton, "btnHelpOnboarding") is not None:
        return True
    if window.findChild(QPushButton, "btnOverflowMenu") is not None:
        return True
    if "show_onboarding" in main_window_src and "on_help_onboarding" in main_window_src:
        return True
    return False
