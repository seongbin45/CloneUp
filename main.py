#!/usr/bin/env python3
"""CloneUp GUI entry — main window or tray (--tray)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_INSTANCE_KEY = "CloneUpSingleInstance"


def _want_tray(argv: list[str]) -> bool:
    return any(a in ("--tray", "/tray") for a in argv[1:])


def _want_scan_cache(argv: list[str]) -> bool:
    return any(a in ("--scan-cache", "/scan-cache") for a in argv[1:])


def main() -> int:
    # Headless cache refresh (schtasks / frozen) — no Qt widgets.
    if _want_scan_cache(sys.argv):
        from app.scan_worker import run_scan_worker

        force = any(a in ("--full", "--force-full") for a in sys.argv[1:])
        return run_scan_worker(force_full=force)

    try:
        from PySide6.QtCore import QCoreApplication, Qt
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    except ImportError:
        print(
            "PySide6 가 필요합니다:\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install PySide6\n",
            file=sys.stderr,
        )
        return 2

    # Required before QApplication when Qt WebEngine may be used (connect wizard).
    try:
        QCoreApplication.setAttribute(
            Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
        )
    except Exception:
        pass

    from app import __version__
    from app.ui.icons import load_app_icon
    from app.ui.theme import apply_system_theme

    app = QApplication(sys.argv)
    app.setApplicationName("CloneUp")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)

    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    apply_system_theme(app)
    try:
        app.styleHints().colorSchemeChanged.connect(
            lambda _scheme=None: apply_system_theme(app)
        )
    except Exception:
        pass

    try:
        from app.git.credentials import cleanup_orphan_credential_files

        cleanup_orphan_credential_files(max_age_sec=0)
    except Exception:
        pass

    tray_mode = _want_tray(sys.argv)

    # Pref default True must actually register HKCU Run (Gap A: UI ON, registry unset).
    try:
        from app.util.autostart_win import apply_autostart_preference

        apply_autostart_preference()
    except Exception:
        pass

    # Background project-scan task (plan D2) — best-effort; UI scan still works.
    try:
        from app.ui.settings_store import load_bg_project_scan_enabled
        from app.util.scan_task_win import ensure_scan_task

        ensure_scan_task(enabled=load_bg_project_scan_enabled())
    except Exception:
        pass

    # --- single instance: second launch activates the first ---
    socket = QLocalSocket()
    socket.connectToServer(_INSTANCE_KEY)
    if socket.waitForConnected(200):
        payload = b"tray" if tray_mode else b"show"
        socket.write(payload)
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return 0

    QLocalServer.removeServer(_INSTANCE_KEY)
    server = QLocalServer(app)
    server.listen(_INSTANCE_KEY)

    from app.ui.main_window import load_main_window
    from app.ui.tray_app import TrayController

    win = load_main_window()
    if not app_icon.isNull():
        win.setWindowIcon(app_icon)
    controller = {"tray": None}

    def show_main(folder: str = "") -> None:
        # Opening the main window: dismiss start-notify (no alarm while UI is up).
        try:
            from app.ui.tray_app import suppress_boot_toast_for_connect

            suppress_boot_toast_for_connect()
        except Exception:
            pass
        win.show()
        # Default (non-maximized) size fills the taskbar-safe work area.
        try:
            from app.util.screen_fit import apply_work_area_normal_fill

            apply_work_area_normal_fill(win)
        except Exception:
            pass
        win.raise_()
        win.activateWindow()
        # U-1b: legacy-seeded users — one-shot home offer (after show; env suppresses)
        try:
            from PySide6.QtCore import QTimer

            def _refit_work_area() -> None:
                # Chrome (title/borders) is accurate after the first map.
                try:
                    from app.util.screen_fit import apply_work_area_normal_fill

                    apply_work_area_normal_fill(win)
                except Exception:
                    pass

            def _maybe_home_offer() -> None:
                try:
                    from app.ui.ui_mode import maybe_offer_home_shell

                    maybe_offer_home_shell(win)
                except Exception:
                    pass

            QTimer.singleShot(0, _refit_work_area)
            QTimer.singleShot(600, _maybe_home_offer)
        except Exception:
            pass
        if folder:
            try:
                ctrl = getattr(win, "_cloneup_controller", None)
                edit = getattr(ctrl, "editSyncFolder", None) if ctrl else None
                if edit is not None:
                    edit.setText(folder)
                    if hasattr(ctrl, "on_sync_refresh"):
                        ctrl.on_sync_refresh(quiet=True)
            except Exception:
                pass

    def ensure_tray() -> None:
        if controller["tray"] is None:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                print("시스템 트레이를 쓸 수 없습니다 — 창 모드로 엽니다.")
                show_main()
                return
            tray = TrayController(app)
            tray.request_open_main.connect(show_main)
            tray.request_quit.connect(app.quit)
            controller["tray"] = tray

    def on_ipc() -> None:
        sock = server.nextPendingConnection()
        if sock is None:
            return
        sock.waitForReadyRead(500)
        data = bytes(sock.readAll()).decode("utf-8", errors="ignore")
        sock.disconnectFromServer()
        if data.strip() == "tray":
            ensure_tray()
        else:
            show_main()

    server.newConnection.connect(on_ipc)

    if tray_mode:
        ensure_tray()
        # Keep running with no visible window
    else:
        # Normal start: show window; also attach tray for boot notify if enabled
        show_main()
        try:
            from app.ui.settings_store import load_boot_notify_enabled

            if load_boot_notify_enabled() and QSystemTrayIcon.isSystemTrayAvailable():
                ensure_tray()
        except Exception:
            pass

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
