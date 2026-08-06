"""
CloneUp design tokens.

Light:  desin/CloneUp Window.dc.html
Dark:   desin/dark/CloneUp Window Dark.dc.html

Module-level aliases (BG_WINDOW, PRIMARY, …) always reflect the *active*
palette so dialogs/auth can import them. Call apply_palette() when switching.
Default active palette is LIGHT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ThemeName = Literal["light", "dark"]


@dataclass(frozen=True)
class Palette:
    name: ThemeName
    # Surfaces
    bg_app: str
    bg_window: str
    bg_bar: str
    bg_input: str
    bg_muted: str
    bg_hint: str
    bg_log: str
    # Borders
    border: str
    border_soft: str
    border_input: str
    border_divider: str
    border_outline: str  # secondary outline buttons (pull)
    # Text
    text: str
    text_secondary: str
    text_muted: str
    text_faint: str
    text_disabled: str
    text_on_primary: str
    text_log: str
    text_log_dim: str
    text_log_ok: str
    text_log_err: str
    text_log_warn: str
    # Accent
    primary: str
    primary_hover: str
    primary_soft: str
    success_dot: str
    # Status
    warn_dot: str
    warn_border: str
    warn_text: str
    danger: str
    danger_hover: str
    danger_soft_bg: str
    hover_muted: str
    hover_pressed: str
    # Tabs
    tab_inactive_fg: str


# --- Light (desin/CloneUp Window.dc.html) ---
LIGHT = Palette(
    name="light",
    bg_app="#e8e6e1",
    bg_window="#fbfaf8",
    bg_bar="#f2efe9",
    bg_input="#ffffff",
    bg_muted="#f2efe9",
    bg_hint="#f4f1e8",
    bg_log="#2c2925",  # mock terminal (UI uses light log body by preference)
    border="#c9c5bd",
    border_soft="#ddd8d0",
    border_input="#cdc8bf",
    border_divider="#e6e1d8",
    border_outline="#b7b1a5",
    text="#2f2b24",
    text_secondary="#4a453b",
    text_muted="#6d675c",
    text_faint="#8b8477",
    text_disabled="#b3ac9e",
    text_on_primary="#ffffff",
    text_log="#d6d0c4",
    text_log_dim="#8f887c",
    text_log_ok="#7fc9a8",
    text_log_err="#e0a3a3",
    text_log_warn="#c9ad5c",
    primary="#1f6f5c",
    primary_hover="#185b4b",
    primary_soft="#14503f",
    success_dot="#2f8f6d",
    warn_dot="#c4a94e",
    warn_border="#c4a94e",
    warn_text="#9a6700",
    danger="#cf222e",
    danger_hover="#a40e26",
    danger_soft_bg="#fff5f5",
    hover_muted="#e9e5dd",
    hover_pressed="#e0dbd2",
    tab_inactive_fg="#7c766a",
)

# --- Dark (desin/dark/CloneUp Window Dark.dc.html) ---
DARK = Palette(
    name="dark",
    bg_app="#111009",
    bg_window="#232019",
    bg_bar="#2b2821",
    bg_input="#1b1915",
    bg_muted="#2b2821",
    bg_hint="#2c2921",
    bg_log="#15140f",
    border="#3b372e",
    border_soft="#38342b",
    border_input="#443f35",
    border_divider="#333026",
    border_outline="#4f4a3f",
    text="#efeade",
    text_secondary="#bab3a3",
    text_muted="#a39c8c",
    text_faint="#8b8477",
    text_disabled="#5b564c",
    text_on_primary="#0f231c",  # dark teal button label on bright accent
    text_log="#d6d0c4",
    text_log_dim="#8f887c",
    text_log_ok="#7fc9a8",
    text_log_err="#e0a3a3",
    text_log_warn="#c9ad5c",
    primary="#46a685",
    primary_hover="#57bd99",
    primary_soft="#14503f",
    success_dot="#4fb68f",
    warn_dot="#d3b862",
    warn_border="#d3b862",
    warn_text="#c9ad5c",
    danger="#e07070",
    danger_hover="#f09090",
    danger_soft_bg="#3a2424",
    hover_muted="#343128",
    hover_pressed="#3a362e",
    tab_inactive_fg="#8b8477",
)

_active: Palette = LIGHT


def active_palette() -> Palette:
    return _active


def apply_palette(palette: Palette) -> None:
    """Set module-level color aliases to *palette* (for dialogs/auth imports)."""
    global _active
    global BG_APP, BG_WINDOW, BG_BAR, BG_INPUT, BG_MUTED, BG_HINT, BG_LOG
    global BORDER, BORDER_SOFT, BORDER_INPUT, BORDER_DIVIDER, BORDER_OUTLINE
    global TEXT, TEXT_SECONDARY, TEXT_MUTED, TEXT_FAINT, TEXT_DISABLED
    global TEXT_ON_PRIMARY, TEXT_LOG, TEXT_LOG_DIM, TEXT_LOG_OK, TEXT_LOG_ERR, TEXT_LOG_WARN
    global PRIMARY, PRIMARY_HOVER, PRIMARY_SOFT, SUCCESS_DOT
    global WARN_DOT, WARN_BORDER, WARN_TEXT
    global DANGER, DANGER_HOVER, DANGER_SOFT_BG, HOVER_MUTED, HOVER_PRESSED
    global TAB_ACTIVE_FG, TAB_INACTIVE_FG, TAB_ACTIVE_BG, TAB_RAIL_BG

    _active = palette
    BG_APP = palette.bg_app
    BG_WINDOW = palette.bg_window
    BG_BAR = palette.bg_bar
    BG_INPUT = palette.bg_input
    BG_MUTED = palette.bg_muted
    BG_HINT = palette.bg_hint
    BG_LOG = palette.bg_log
    BORDER = palette.border
    BORDER_SOFT = palette.border_soft
    BORDER_INPUT = palette.border_input
    BORDER_DIVIDER = palette.border_divider
    BORDER_OUTLINE = palette.border_outline
    TEXT = palette.text
    TEXT_SECONDARY = palette.text_secondary
    TEXT_MUTED = palette.text_muted
    TEXT_FAINT = palette.text_faint
    TEXT_DISABLED = palette.text_disabled
    TEXT_ON_PRIMARY = palette.text_on_primary
    TEXT_LOG = palette.text_log
    TEXT_LOG_DIM = palette.text_log_dim
    TEXT_LOG_OK = palette.text_log_ok
    TEXT_LOG_ERR = palette.text_log_err
    TEXT_LOG_WARN = palette.text_log_warn
    PRIMARY = palette.primary
    PRIMARY_HOVER = palette.primary_hover
    PRIMARY_SOFT = palette.primary_soft
    SUCCESS_DOT = palette.success_dot
    WARN_DOT = palette.warn_dot
    WARN_BORDER = palette.warn_border
    WARN_TEXT = palette.warn_text
    DANGER = palette.danger
    DANGER_HOVER = palette.danger_hover
    DANGER_SOFT_BG = palette.danger_soft_bg
    HOVER_MUTED = palette.hover_muted
    HOVER_PRESSED = palette.hover_pressed
    TAB_ACTIVE_FG = palette.primary
    TAB_INACTIVE_FG = palette.tab_inactive_fg
    TAB_ACTIVE_BG = palette.bg_window
    TAB_RAIL_BG = palette.bg_bar


def palette_by_name(name: ThemeName | str) -> Palette:
    key = str(name).strip().lower()
    if key == "dark":
        return DARK
    return LIGHT


def system_color_scheme_is_dark() -> bool:
    """
    True when the OS reports a dark color scheme (Qt 6 StyleHints).

    Unknown / light → False (keep light as safe default).
    Requires a QGuiApplication (or QApplication) instance.
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
    except ImportError:
        return False

    app = QGuiApplication.instance()
    if app is None:
        return False
    try:
        scheme = app.styleHints().colorScheme()
    except Exception:
        return False
    return scheme == Qt.ColorScheme.Dark


def palette_from_system() -> Palette:
    """Pick LIGHT or DARK from the current OS color scheme."""
    return DARK if system_color_scheme_is_dark() else LIGHT


def apply_system_theme(app=None) -> Palette:
    """
    Apply system light/dark palette to module aliases + app stylesheet.

    Call after QApplication is created. Safe to call again on
    styleHints().colorSchemeChanged.
    """
    if app is None:
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
        except ImportError:
            app = None

    palette = palette_from_system()
    apply_palette(palette)
    if app is not None:
        app.setStyleSheet(app_stylesheet(palette))
    return palette


# Initialize module-level aliases (light default until apply_system_theme)
apply_palette(LIGHT)


def app_stylesheet(palette: Palette | None = None) -> str:
    """Global QSS. Uses *palette* or the active palette."""
    p = palette or _active
    # Local names for f-string clarity
    BG_WINDOW = p.bg_window
    BG_BAR = p.bg_bar
    BG_INPUT = p.bg_input
    BG_MUTED = p.bg_muted
    BG_HINT = p.bg_hint
    BG_LOG = p.bg_log
    BORDER = p.border
    BORDER_SOFT = p.border_soft
    BORDER_INPUT = p.border_input
    BORDER_DIVIDER = p.border_divider
    BORDER_OUTLINE = p.border_outline
    TEXT = p.text
    TEXT_SECONDARY = p.text_secondary
    TEXT_MUTED = p.text_muted
    TEXT_FAINT = p.text_faint
    TEXT_DISABLED = p.text_disabled
    TEXT_ON_PRIMARY = p.text_on_primary
    PRIMARY = p.primary
    PRIMARY_HOVER = p.primary_hover
    HOVER_MUTED = p.hover_muted
    HOVER_PRESSED = p.hover_pressed
    WARN_DOT = p.warn_dot
    TAB_ACTIVE_FG = p.primary
    TAB_INACTIVE_FG = p.tab_inactive_fg
    TAB_ACTIVE_BG = p.bg_window
    TAB_RAIL_BG = p.bg_bar

    # Light mode: user preferred light log body over mock dark terminal.
    # Dark mode: use mock log panel (#15140f) from desin/dark.
    if p.name == "dark":
        log_bg = BG_LOG
        log_fg = p.text_log
        log_border = BORDER_SOFT
    else:
        log_bg = BG_INPUT
        log_fg = TEXT
        log_border = BORDER_INPUT

    return f"""
    /* ===== CloneUp global theme ({p.name}) ===== */
    QMainWindow, QWidget {{
        background-color: {BG_WINDOW};
        color: {TEXT};
        font-size: 13px;
    }}
    QLabel {{
        color: {TEXT_SECONDARY};
        background: transparent;
    }}
    QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{
        background-color: {BG_INPUT};
        color: {TEXT};
        border: 1px solid {BORDER_INPUT};
        border-radius: 5px;
        padding: 4px 10px;
        selection-background-color: {PRIMARY};
        selection-color: {TEXT_ON_PRIMARY};
    }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {PRIMARY};
    }}
    QLineEdit:disabled, QComboBox:disabled {{
        color: {TEXT_DISABLED};
        background: {BG_MUTED};
    }}
    /* D4 — placeholders / popup lists readable on dark surfaces */
    QLineEdit::placeholder,
    QComboBox::placeholder,
    QPlainTextEdit::placeholder {{
        color: {TEXT_DISABLED};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_INPUT};
        color: {TEXT};
        border: 1px solid {BORDER_INPUT};
        selection-background-color: {PRIMARY};
        selection-color: {TEXT_ON_PRIMARY};
        outline: 0;
    }}
    QToolTip {{
        background-color: {BG_BAR};
        color: {TEXT};
        border: 1px solid {BORDER_SOFT};
        padding: 4px 8px;
    }}
    QCheckBox, QRadioButton {{
        color: {TEXT_SECONDARY};
        spacing: 8px;
        background: transparent;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 13px;
        height: 13px;
    }}
    QRadioButton::indicator:checked {{
        border: 1px solid {PRIMARY};
        background: {PRIMARY};
        border-radius: 7px;
    }}
    QRadioButton::indicator:unchecked {{
        border: 1px solid {BORDER_INPUT};
        background: {BG_INPUT};
        border-radius: 7px;
    }}
    QCheckBox::indicator:unchecked {{
        border: 1px solid {BORDER_INPUT};
        background: {BG_INPUT};
        border-radius: 3px;
    }}
    QCheckBox::indicator:checked {{
        border: 1px solid {PRIMARY};
        background: {PRIMARY};
        border-radius: 3px;
    }}

    /* Secondary buttons (browse, cancel idle, etc.) */
    QPushButton {{
        background-color: {BG_MUTED};
        color: {TEXT_SECONDARY};
        border: 1px solid {BORDER_INPUT};
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: 500;
        min-height: 28px;
    }}
    QPushButton:hover {{
        background-color: {HOVER_MUTED};
        color: {TEXT_SECONDARY};
    }}
    QPushButton:disabled {{
        color: {TEXT_DISABLED};
        background: {BG_MUTED};
        border-color: {BORDER_SOFT};
    }}
    QPushButton:pressed {{
        background-color: {HOVER_PRESSED};
    }}

    /* Primary actions */
    QPushButton#btnPublish,
    QPushButton#btnClone,
    QPushButton#btnSyncPush {{
        background-color: {PRIMARY};
        color: {TEXT_ON_PRIMARY};
        border: 1px solid {PRIMARY};
        font-weight: 600;
        min-height: 36px;
        padding: 8px 16px;
    }}
    QPushButton#btnPublish:hover,
    QPushButton#btnClone:hover,
    QPushButton#btnSyncPush:hover {{
        background-color: {PRIMARY_HOVER};
        border-color: {PRIMARY_HOVER};
        color: {TEXT_ON_PRIMARY};
    }}
    QPushButton#btnPublish:disabled,
    QPushButton#btnClone:disabled,
    QPushButton#btnSyncPush:disabled {{
        background-color: {BG_MUTED};
        border-color: {BORDER_SOFT};
        color: {TEXT_DISABLED};
    }}

    /* Secondary outline (pull) — desin mock outline button */
    QPushButton#btnSyncPull {{
        background-color: {BG_INPUT};
        color: {TEXT};
        border: 1px solid {BORDER_OUTLINE};
        font-weight: 500;
        min-height: 36px;
    }}
    QPushButton#btnSyncPull:hover {{
        background-color: {BG_MUTED};
        color: {TEXT};
    }}

    /* Tabs */
    QTabWidget::pane {{
        border: 1px solid {BORDER_SOFT};
        border-top: none;
        background: {BG_WINDOW};
        top: -1px;
    }}
    QTabBar {{
        background: {TAB_RAIL_BG};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {TAB_INACTIVE_FG};
        padding: 10px 18px;
        margin-right: 2px;
        border: 1px solid transparent;
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: 500;
    }}
    QTabBar::tab:selected {{
        background: {TAB_ACTIVE_BG};
        color: {TAB_ACTIVE_FG};
        border: 1px solid {BORDER_SOFT};
        border-bottom: 1px solid {TAB_ACTIVE_BG};
    }}
    QTabBar::tab:hover:!selected {{
        color: {TEXT_SECONDARY};
    }}

    /* Log panel header + body */
    QWidget#logPanel {{
        background-color: {BG_WINDOW};
        border-top: 1px solid {BORDER_DIVIDER};
    }}
    QLabel#labelLog {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
        font-weight: 600;
        background: transparent;
        padding: 0;
    }}
    QLabel#labelLogHint {{
        color: {TEXT_FAINT};
        font-size: 11.5px;
        background: transparent;
        padding: 0;
    }}
    QPlainTextEdit#textLog {{
        background-color: {log_bg};
        color: {log_fg};
        border: 1px solid {log_border};
        border-radius: 5px;
        padding: 8px 10px;
        font-family: Consolas, "IBM Plex Mono", monospace;
        font-size: 12px;
        max-height: 130px;
        selection-background-color: {PRIMARY};
        selection-color: {TEXT_ON_PRIMARY};
    }}
    QPlainTextEdit#textLog::placeholder {{
        color: {TEXT_FAINT};
    }}

    QStatusBar {{
        background: {BG_BAR};
        color: {TEXT_FAINT};
        border-top: 1px solid {BORDER_SOFT};
    }}

    /* Top status row (Git + GitHub dots) */
    QWidget#statusBarFrame {{
        background-color: {BG_WINDOW};
        border-bottom: 1px solid {BORDER_DIVIDER};
    }}
    QLabel#labelStatusGit {{
        color: {TEXT_SECONDARY};
        font-size: 12.5px;
        padding: 0;
        background: transparent;
    }}
    QPushButton#btnAuthStatus {{
        background: transparent;
        border: none;
        color: {TEXT_SECONDARY};
        font-size: 12.5px;
        font-weight: 500;
        padding: 2px 4px;
        text-align: left;
        min-height: 0;
    }}
    QPushButton#btnAuthStatus:hover {{
        color: {PRIMARY};
        background: transparent;
        border: none;
    }}
    QPushButton#btnAuthStatus:disabled {{
        color: {TEXT_DISABLED};
        background: transparent;
        border: none;
    }}
    /* Same family as btnAuthStatus — right edge of status row */
    QPushButton#btnLogout {{
        background: transparent;
        border: none;
        color: {TEXT_MUTED};
        font-size: 12.5px;
        font-weight: 500;
        padding: 2px 2px 2px 8px;
        text-align: right;
        min-height: 0;
        max-height: 22px;
    }}
    QPushButton#btnLogout:hover {{
        color: {DANGER};
        background: transparent;
        border: none;
    }}
    QPushButton#btnLogout:disabled {{
        color: {TEXT_DISABLED};
        background: transparent;
        border: none;
    }}

    /* G1/G2 — collapsible tip card (folded = one line) */
    QFrame#tipCard {{
        background-color: {BG_HINT};
        border: 1px solid {BORDER_SOFT};
        border-left: 3px solid {PRIMARY};
        border-radius: 0 6px 6px 0;
    }}
    QPushButton#tipCardHeader {{
        background: transparent;
        border: none;
        color: {TEXT_SECONDARY};
        font-size: 12.5px;
        font-weight: 500;
        text-align: left;
        padding: 0;
        min-height: 0;
    }}
    QPushButton#tipCardHeader:hover {{
        color: {PRIMARY};
        background: transparent;
        border: none;
    }}
    QLabel#tipCardBody {{
        color: {TEXT_MUTED};
        font-size: 12px;
        background: transparent;
        padding: 2px 2px 2px 18px;
        line-height: 1.45;
    }}
    /* placeholders until MainController swaps in TipCard */
    QLabel#labelTabIntroPublish,
    QLabel#labelTabIntroClone,
    QLabel#labelTabIntroSync {{
        color: {TEXT_MUTED};
        font-size: 12.5px;
        background: transparent;
    }}

    /* Form label grid (~92px) */
    QLabel#labelFolder,
    QLabel#labelRecent,
    QLabel#labelRepoName,
    QLabel#labelCommitMessage,
    QLabel#labelCloneUrl,
    QLabel#labelCloneBranch,
    QLabel#labelCloneParent,
    QLabel#labelCloneDirName,
    QLabel#labelSyncFolder,
    QLabel#labelSyncMessage {{
        min-width: 92px;
        max-width: 92px;
        color: {TEXT_SECONDARY};
        font-size: 13px;
        padding-right: 4px;
    }}
    /* Option row: side-by-side checkboxes (left margin on HBox in .ui) */
    QCheckBox#checkAllowSecrets,
    QCheckBox#checkHideEmail,
    QCheckBox#checkSyncAllowSecrets,
    QCheckBox#checkSyncHideEmail {{
        margin-left: 0;
        color: {TEXT_FAINT};
        font-size: 12.5px;
    }}
    QCheckBox#checkHideEmail,
    QCheckBox#checkSyncHideEmail {{
        color: {TEXT_SECONDARY};
    }}
    QCheckBox#checkCloneUseToken {{
        margin-left: 102px;
        color: {TEXT_SECONDARY};
        font-size: 12.5px;
    }}
    QLabel#labelCloneHint {{
        background: {BG_HINT};
        color: {TEXT_MUTED};
        border-left: 3px solid {WARN_DOT};
        border-radius: 0 5px 5px 0;
        padding: 11px 13px;
        font-size: 12.5px;
        margin-left: 102px;
    }}
    QLabel#labelSyncBranch {{
        background: {BG_HINT};
        color: {PRIMARY};
        border: 1px solid {BORDER_SOFT};
        border-left: 4px solid {PRIMARY};
        border-radius: 6px;
        padding: 10px 14px;
        margin-left: 102px;
        font-size: 14px;
        font-weight: 700;
    }}
    QLabel#labelSyncStatus {{
        background: {BG_MUTED};
        color: {TEXT_MUTED};
        border-radius: 5px;
        padding: 8px 13px;
        margin-left: 102px;
        font-size: 12px;
    }}
    """
