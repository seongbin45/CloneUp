"""Phase A chrome: overflow ⋯ menu, Git-missing banner, accessibility shortcuts.

Home IA (desin/CloneUp 홈.dc.html): settings/help/terms/Git version live in ⋯;
Git problems surface as a yellow banner — not an always-on status label.

Home shell (T-1(b)) injects ``home_chrome_colors()`` so banner/⋯ match the
home map; legacy tabs may omit colors and fall back to ``active_palette()``.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from app.paths import app_root
from app.ui.home_tokens import HOME_FONT_GLYPH, home_chrome_colors
from app.ui.theme import active_palette


class PillFrame(QFrame):
    """Fully rounded (capsule) panel — Win QSS ``border-radius: 999px`` is a no-op.

    Paints ``outer`` (usually top-bar ``bg_sidebar``) under a pill fill so the
    square widget corners never show window cream / black. Radius = half height
    (시안 search 216×28 → 14px ends).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fill = QColor("#fbfaf8")
        self._border = QColor("#cdc8bf")
        self._outer = QColor("#f0ede6")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
        )

    def set_pill_chrome(
        self,
        *,
        fill: str,
        border: str,
        outer: str,
    ) -> None:
        self._fill = QColor(fill)
        self._border = QColor(border)
        self._outer = QColor(outer)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Match parent bar so square widget bounds do not flash a wrong color.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._outer)
        painter.fillRect(self.rect(), self._outer)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(rect.width(), rect.height()) / 2.0
        painter.setBrush(self._fill)
        painter.setPen(QPen(self._border, 1.0))
        painter.drawRoundedRect(rect, radius, radius)


class OverflowMenuButton(QPushButton):
    """31×31 ⋯ control — paints three dots (no Unicode tofu on Windows)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fg = QColor("#4a453b")
        self._open = False
        self.setObjectName("btnOverflowMenu")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(31, 31)
        self.setFlat(True)
        self.setText("")  # painted, not text
        self.setToolTip("설정 · 도움말 · Git")

    def set_dot_color(self, color: str) -> None:
        self._fg = QColor(color)
        self.update()

    def set_menu_open(self, open_: bool) -> None:
        self._open = bool(open_)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtWidgets import QStyleOptionButton
        from PySide6.QtWidgets import QStyle

        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Background: hover / open (시안 menuBg = nav_selected, never primary green)
        bg = None
        if self._open:
            bg = self.property("openBg") or "#e0dcd2"
        elif opt.state & QStyle.StateFlag.State_MouseOver:
            bg = self.property("hoverBg") or "#e4e0d7"
        if bg:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(str(bg)))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        # Three horizontal dots centered
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._fg)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        r = 1.6
        gap = 5.0
        for dx in (-gap, 0.0, gap):
            p.drawEllipse(QRectF(cx + dx - r, cy - r, r * 2, r * 2))
        p.end()


class RoundedHoverButton(QAbstractButton):
    """Home ◀/▶ chrome — 시안 24×24 · border-radius 5px hover chip.

    Must NOT subclass ``QPushButton``: app ``QPushButton { background… }`` QSS
    always draws a sharp muted rectangle that no child stylesheet fully kills
    under a parent with its own ``setStyleSheet``.

    Idle fill must match the top bar (``bg_sidebar``). Do **not** use
    ``WA_TranslucentBackground`` + clear-to-transparent on Windows — that
    leaves a hardcoded black rect until hover.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        radius: float = 5.0,
        pill: bool = False,
    ) -> None:
        super().__init__(parent)
        self._radius = float(radius)
        self._pill = bool(pill)
        self._idle_bg = QColor("#f0ede6")  # light sidebar default; set via set_chrome
        self._hover_bg = QColor("#e4e0d7")
        self._press_bg = QColor("#e0dcd2")
        self.setObjectName("roundedHoverBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setStyleSheet(
            "QAbstractButton { background: transparent; border: none; padding: 0; margin: 0; }"
        )

    def set_chrome(
        self,
        *,
        idle: str,
        hover: str,
        press: str | None = None,
    ) -> None:
        """Theme tokens: idle = top-bar/sidebar, hover/press = 시안 chip."""
        self._idle_bg = QColor(idle)
        self._hover_bg = QColor(hover)
        self._press_bg = QColor(press or hover)
        # Keep Qt palette Window in sync so any style base fill matches the bar.
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, self._idle_bg)
        pal.setColor(QPalette.ColorRole.Button, self._idle_bg)
        self.setPalette(pal)
        self.update()

    def set_hover_colors(self, hover: str, press: str | None = None) -> None:
        """Back-compat: only updates hover/press (idle unchanged)."""
        self._hover_bg = QColor(hover)
        self._press_bg = QColor(press or hover)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(24, 24)

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.update()

    def _effective_radius(self, rect: QRectF) -> float:
        short = min(rect.width(), rect.height())
        if self._pill:
            return max(self._radius, short * 0.5)
        return min(self._radius, short * 0.5)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Always paint idle (top-bar) first. Hover only draws a 5px chip on top —
        # if we skip the base fill, the square corners keep palette Window
        # (#fbfaf8) and disagree with the top bar (#f0ede6).
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._idle_bg)
        painter.fillRect(self.rect(), self._idle_bg)

        hovered = self.underMouse() and self.isEnabled()
        pressed = self.isDown() and self.isEnabled()
        if pressed or hovered:
            chip = self._press_bg if pressed else self._hover_bg
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            radius = self._effective_radius(rect)
            painter.setBrush(chip)
            painter.drawRoundedRect(rect, radius, radius)

        icon = self.icon()
        if not icon.isNull():
            size = self.iconSize()
            if size.width() <= 0 or size.height() <= 0:
                size = QSize(24, 24)
            mode = (
                QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
            )
            pix = icon.pixmap(size, mode, QIcon.State.Off)
            x = (self.width() - pix.width()) // 2
            y = (self.height() - pix.height()) // 2
            painter.drawPixmap(x, y, pix)


class RoundedOutlineButton(QAbstractButton):
    """Label chip with painted pill outline — not a QPushButton.

    Same reason as ``RoundedHoverButton``: app ``QPushButton`` QSS paints a
    sharp muted box that child stylesheets cannot reliably clear.
    """

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        radius: float = 10.0,
        pill: bool = True,
    ) -> None:
        super().__init__(parent)
        self._radius = float(radius)
        self._pill = bool(pill)
        self._bg = QColor("#fbfaf8")
        self._bg_hover = QColor("#e9e5dd")
        self._border = QColor("#b7b1a5")
        self._fg = QColor("#4a453b")
        self.setText(text)
        self.setObjectName("roundedOutlineBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setStyleSheet(
            "QAbstractButton { background: transparent; border: none; padding: 0; margin: 0; }"
        )

    def set_chrome(
        self,
        *,
        bg: str,
        bg_hover: str,
        border: str,
        fg: str,
    ) -> None:
        self._bg = QColor(bg)
        self._bg_hover = QColor(bg_hover)
        self._border = QColor(border)
        self._fg = QColor(fg)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self.font())
        w = fm.horizontalAdvance(self.text()) + 32
        h = max(36, int(fm.height()) + 18)
        return QSize(w, h)

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.update()

    def _effective_radius(self, rect: QRectF) -> float:
        short = min(rect.width(), rect.height())
        if self._pill:
            return max(self._radius, short * 0.5)
        return min(self._radius, short * 0.5)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Source
        )
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver
        )
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        hovered = self.underMouse()
        pressed = self.isDown()
        fill = self._bg_hover if (hovered or pressed) else self._bg
        radius = self._effective_radius(rect)
        painter.setPen(QPen(self._border, 1.0))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)
        painter.setPen(self._fg)
        painter.setFont(self.font())
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self.text())


def open_terms_dialog(parent: QWidget | None) -> None:
    """Show 이용약관 (same files Settings → 정보 uses).

    Uses a scrollable, taskbar-safe dialog — a QMessageBox with the full
    terms text grows past ``availableGeometry`` and clips under the taskbar.
    """
    from app.ui.text_document_dialog import show_text_document_dialog

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
                text = path.read_text(encoding="utf-8-sig", errors="replace")
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
    show_text_document_dialog(parent, "이용약관", text)


class GitMissingBanner(QFrame):
    """Warn strip above the main list/tabs when Git is not installed."""

    install_clicked = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        colors: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("gitMissingBanner")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._title: QLabel | None = None
        self._body: QLabel | None = None
        self._btn: QPushButton | None = None
        self._colors = colors
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(3)
        self._title = QLabel("Git이 설치되어 있지 않습니다")
        self._title.setObjectName("gitMissingBannerTitle")
        # 시안 CloneUp 홈.dc.html 원문
        self._body = QLabel(
            "받기와 올리기가 동작하지 않습니다. 설치하고 클론업을 다시 열어 주세요."
        )
        self._body.setWordWrap(True)
        col.addWidget(self._title)
        col.addWidget(self._body)
        row.addLayout(col, 1)
        self._btn = QPushButton("설치 방법 보기")
        self._btn.setObjectName("gitMissingBannerCta")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self.install_clicked.emit)
        row.addWidget(self._btn, 0)
        self.apply_colors(colors)
        self.hide()

    def apply_colors(self, colors: Any | None = None) -> None:
        """Apply home chrome map, or fall back to active_palette (legacy tabs)."""
        if colors is not None:
            self._colors = colors
        c = self._colors
        if c is not None:
            soft = getattr(c, "bg_warn_note", "#f6efdd")
            warn_border = getattr(c, "warn_border", "#c4a94e")
            text = getattr(c, "text", "#232019")
            muted = getattr(c, "text_muted", "#6d675c")
            btn_bg = getattr(c, "bg_window", "#fbfaf8")
            btn_hover = getattr(c, "banner_btn_hover", getattr(c, "nav_hover", "#e4e0d7"))
            secondary = getattr(c, "text_secondary", muted)
        else:
            p = active_palette()
            soft = "#f6efdd" if p.name == "light" else "#2e2a1e"
            warn_border = p.warn_border
            text = p.text
            muted = p.text_muted
            btn_bg = p.bg_window
            btn_hover = p.hover_muted
            secondary = p.text_secondary
        self.setStyleSheet(
            f"QFrame#gitMissingBanner {{"
            f" background: {soft}; border: none;"
            f" border-bottom: 1px solid {warn_border}; }}"
        )
        if self._title is not None:
            self._title.setStyleSheet(
                f"font-size: 13px; font-weight: 600; color: {text};"
            )
        if self._body is not None:
            self._body.setStyleSheet(f"font-size: 12px; color: {muted};")
        if self._btn is not None:
            self._btn.setStyleSheet(
                f"QPushButton#gitMissingBannerCta {{"
                f" background: {btn_bg}; border: 1px solid {warn_border};"
                f" border-radius: 6px; padding: 7px 12px; font-size: 12.5px;"
                f" color: {text}; }}"
                f"QPushButton#gitMissingBannerCta:hover {{ background: {btn_hover}; }}"
            )

    def refresh_theme(self) -> None:
        # Legacy path: re-read active palette unless home injected colors
        if self._colors is None:
            self.apply_colors(None)
        else:
            self.apply_colors(home_chrome_colors())


def make_overflow_button(
    parent: QWidget | None = None,
    *,
    colors: Any | None = None,
) -> OverflowMenuButton:
    """31×31 ⋯ control for the status row (Phase A) / sidebar (Phase B)."""
    btn = OverflowMenuButton(parent)
    apply_overflow_colors(btn, colors)
    return btn


def apply_overflow_colors(
    btn: QPushButton,
    colors: Any | None = None,
    *,
    menu_open: bool = False,
) -> None:
    """Paint colors for overflow button. Open state uses nav_selected (not green)."""
    if colors is not None:
        fg = getattr(colors, "text_secondary", "#4a453b")
        hover = getattr(colors, "nav_hover", "#e4e0d7")
        open_bg = getattr(colors, "nav_selected", "#e0dcd2")
    else:
        p = active_palette()
        fg = p.text_secondary
        hover = p.hover_muted
        open_bg = p.bg_muted
    btn.setProperty("hoverBg", hover)
    btn.setProperty("openBg", open_bg)
    btn.setStyleSheet(
        "QPushButton#btnOverflowMenu {"
        " background: transparent; border: none; border-radius: 6px; padding: 0; }"
    )
    if isinstance(btn, OverflowMenuButton):
        btn.set_dot_color(str(fg))
        btn.set_menu_open(menu_open)
    else:
        btn.update()


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
