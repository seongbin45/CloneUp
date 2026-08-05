"""
CloneUp design tokens — from desin/CloneUp Window.dc.html

Warm paper UI + teal accent. Use these constants everywhere (QSS, dialogs)
so colors stay unified.
"""

from __future__ import annotations

# --- Surfaces ---
BG_APP = "#e8e6e1"  # window chrome / outside (if shown)
BG_WINDOW = "#fbfaf8"  # main content
BG_BAR = "#f2efe9"  # title / tab rail
BG_INPUT = "#ffffff"
BG_MUTED = "#f2efe9"
BG_HINT = "#f4f1e8"
BG_LOG = "#2c2925"

# --- Borders ---
BORDER = "#c9c5bd"
BORDER_SOFT = "#ddd8d0"
BORDER_INPUT = "#cdc8bf"
BORDER_DIVIDER = "#e6e1d8"

# --- Text ---
TEXT = "#2f2b24"
TEXT_SECONDARY = "#4a453b"
TEXT_MUTED = "#6d675c"
TEXT_FAINT = "#8b8477"
TEXT_DISABLED = "#b3ac9e"
TEXT_ON_PRIMARY = "#ffffff"
TEXT_LOG = "#d6d0c4"
TEXT_LOG_DIM = "#8f887c"
TEXT_LOG_OK = "#7fc9a8"
TEXT_LOG_ERR = "#e0a3a3"

# --- Accent (teal) ---
PRIMARY = "#1f6f5c"
PRIMARY_HOVER = "#185b4b"
PRIMARY_SOFT = "#14503f"
SUCCESS_DOT = "#2f8f6d"

# --- Status ---
WARN_DOT = "#c4a94e"
WARN_BORDER = "#c4a94e"
WARN_TEXT = "#9a6700"  # amber body (timer, soft warnings)
DANGER = "#cf222e"
DANGER_HOVER = "#a40e26"
DANGER_SOFT_BG = "#fff5f5"
HOVER_MUTED = "#e9e5dd"
HOVER_PRESSED = "#e0dbd2"

# --- Tabs ---
TAB_ACTIVE_FG = PRIMARY
TAB_INACTIVE_FG = "#7c766a"
TAB_ACTIVE_BG = BG_WINDOW
TAB_RAIL_BG = BG_BAR


def app_stylesheet() -> str:
    """Global QSS applied to QApplication — Phase 1 color unification."""
    return f"""
    /* ===== CloneUp global theme (Phase 1) ===== */
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
    QComboBox::drop-down {{
        border: none;
        width: 22px;
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
        border: 1px solid #b7b1a5;
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

    /* Phase 4 — log panel header + light log body */
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
        background-color: {BG_INPUT};
        color: {TEXT};
        border: 1px solid {BORDER_INPUT};
        border-radius: 5px;
        padding: 8px 10px;
        font-family: Consolas, "IBM Plex Mono", monospace;
        font-size: 12px;
        max-height: 130px;
        selection-background-color: {PRIMARY};
        selection-color: {TEXT_ON_PRIMARY};
    }}

    QStatusBar {{
        background: {BG_BAR};
        color: {TEXT_FAINT};
        border-top: 1px solid {BORDER_SOFT};
    }}

    /* Phase 2 — top status row (design: Git + GitHub dots) */
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

    /* Phase 3 — form label grid (~92px, design mock) */
    QLabel#labelFolder,
    QLabel#labelRecent,
    QLabel#labelRepoName,
    QLabel#labelCommitMessage,
    QLabel#labelCloneUrl,
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
    QCheckBox#checkAllowSecrets,
    QCheckBox#checkCloneUseToken,
    QCheckBox#checkSyncAllowSecrets {{
        margin-left: 102px;
        color: {TEXT_FAINT};
        font-size: 12.5px;
    }}
    QCheckBox#checkCloneUseToken {{
        color: {TEXT_SECONDARY};
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
    QLabel#labelSyncStatus {{
        background: {BG_MUTED};
        color: {TEXT_MUTED};
        border-radius: 5px;
        padding: 8px 13px;
        margin-left: 102px;
        font-size: 12px;
    }}
    """
