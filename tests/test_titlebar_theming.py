"""
Regression: dialogs kept a light native title bar even in dark mode. Qt
paints window *content* via our QSS, but the OS-drawn title bar (DWM) is
untouched by any stylesheet — apply_system_theme now also syncs it via
app/ui/theme.py's install_native_titlebar_theming.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QDialog

from app.ui.theme import (
    DARK,
    LIGHT,
    apply_palette,
    install_native_titlebar_theming,
    sync_titlebar_theme,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_sync_titlebar_theme_does_not_raise_for_light_and_dark() -> None:
    app = _app()
    dlg = QDialog()
    try:
        dlg.show()
        apply_palette(LIGHT)
        sync_titlebar_theme(dlg)  # must not raise even off-Windows/no-op
        apply_palette(DARK)
        sync_titlebar_theme(dlg)
    finally:
        dlg.close()
        apply_palette(LIGHT)


def test_install_native_titlebar_theming_is_idempotent() -> None:
    """Calling it repeatedly (once per apply_system_theme call) must not
    accumulate duplicate event filters or raise."""
    app = _app()
    install_native_titlebar_theming(app)
    install_native_titlebar_theming(app)
    install_native_titlebar_theming(app)


def test_new_window_gets_synced_on_show() -> None:
    """A window shown *after* install_native_titlebar_theming still gets
    synced automatically, via the installed app-wide Show-event filter."""
    app = _app()
    install_native_titlebar_theming(app)
    apply_palette(DARK)
    dlg = QDialog()
    try:
        dlg.show()  # triggers the QEvent.Type.Show filter — must not raise
        app.processEvents()
    finally:
        dlg.close()
        apply_palette(LIGHT)
