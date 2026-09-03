"""System tray host: boot scan + notify toast (no main window required)."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from app.ui.boot_notify import BootNotifyToast
from app.ui.boot_scan import (
    PendingFolder,
    clear_boot_notify_asked,
    mark_boot_notify_asked,
    should_show_boot_toast,
    snooze_until_days,
)
from app.ui.icons import load_app_icon
from app.ui.settings_store import (
    load_boot_notify_enabled,
    load_last_commit_message,
    migrate_boot_notify_later_policy,
    save_boot_notify_enabled,
    save_boot_notify_snooze_until,
)
from app.util.error_popup import format_error_popup_body


def _main_window_visible() -> bool:
    """True if CloneUp's main window is shown (user is interacting with the app)."""
    try:
        for w in QApplication.topLevelWidgets():
            if not isinstance(w, QWidget):
                continue
            if w.isWindow() and w.isVisible() and not w.isMinimized():
                title = (w.windowTitle() or "")
                # Main window title from ui/main_window.ui
                if "클론업" in title and "CloneUp" in title:
                    return True
                # Fallback: large main shell (not toast/tool dialogs)
                if title.startswith("클론업") and w.width() >= 700:
                    return True
    except Exception:
        pass
    return False


_CONNECT_UI_TITLES = frozenset(
    {
        "CloneUp — GitHub 연결",
        "CloneUp - GitHub 연결",
    }
)


def github_connect_ui_busy() -> bool:
    """
    True while login / re-login UI is on screen.

    Suppresses boot toast so it does not fight ConnectGitHubWizard /
    ExternalBrowserPatGuide (Path A/B).
    """
    try:
        for w in QApplication.topLevelWidgets():
            if not isinstance(w, QWidget):
                continue
            if not w.isVisible():
                continue
            name = type(w).__name__
            if name in (
                "ConnectGitHubWizard",
                "PatTokenDialog",
                "ExternalBrowserPatGuide",
            ):
                return True
            if (w.objectName() or "") == "pathBGuide":
                return True
            if (w.windowTitle() or "").strip() in _CONNECT_UI_TITLES:
                return True
    except Exception:
        pass
    return False


def suppress_boot_toast_for_connect() -> None:
    """Close any boot toast and skip pending scan results (call before login UI)."""
    app = QApplication.instance()
    tray = getattr(app, "_cloneup_tray", None) if app is not None else None
    if tray is not None and hasattr(tray, "dismiss_boot_toast"):
        try:
            tray.dismiss_boot_toast()
        except Exception:
            pass


class _BootScanWorker(QThread):
    """Run git status scan off the GUI thread (avoids Windows '응답 없음')."""

    finished_pending = Signal(object)  # list[PendingFolder]
    failed = Signal(str)

    def run(self) -> None:  # noqa: N802
        try:
            pending = should_show_boot_toast()
            self.finished_pending.emit(list(pending or []))
        except Exception as e:
            self.failed.emit(str(e))


class _BootUploadWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal()
    failed = Signal(str, str)  # folder, message (safety or sync)
    need_auth = Signal(str)  # folder hint when token missing

    def __init__(
        self,
        folders: list[str],
        message: str,
        *,
        hide_real_email: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._folders = list(folders)
        self._message = message
        self._hide_real_email = bool(hide_real_email)

    def run(self) -> None:  # noqa: N802
        from pathlib import Path

        from app.auth.session import AuthError, ensure_valid_token
        from app.git.sync_ops import SyncError, commit_and_push

        try:
            self.progress.emit("GitHub 연결 확인")
            token, user = ensure_valid_token()
        except AuthError as e:
            self.need_auth.emit(self._folders[0] if self._folders else "")
            self.failed.emit("", f"auth:{e}")
            return
        except Exception as e:
            self.need_auth.emit(self._folders[0] if self._folders else "")
            self.failed.emit("", f"auth:{e}")
            return

        for raw in self._folders:
            folder = Path(raw)
            self.progress.emit(folder.name)
            try:
                commit_and_push(
                    folder,
                    message=self._message,
                    token=str(token),
                    user=dict(user or {}),
                    allow_secrets=False,
                    hide_real_email=self._hide_real_email,
                )
            except SyncError as e:
                self.failed.emit(str(folder), str(e))
                return
            except Exception as e:
                self.failed.emit(str(folder), str(e))
                return
        self.finished_ok.emit()


class TrayController(QObject):
    """Owns tray icon, optional boot toast, and open-main callback."""

    request_open_main = Signal(str)  # folder path or ""
    request_quit = Signal()

    def __init__(self, app: QApplication, parent=None) -> None:
        super().__init__(parent)
        self._app = app
        self._toast: BootNotifyToast | None = None
        self._worker: _BootUploadWorker | None = None
        self._scan_worker: _BootScanWorker | None = None
        self._suppress_toast_until_idle = False

        icon = load_app_icon()
        if icon.isNull():
            icon = QIcon()
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("클론업")
        menu = QMenu()
        act_open = QAction("클론업 열기", menu)
        act_open.triggered.connect(lambda: self.request_open_main.emit(""))
        act_scan = QAction("지금 안 올린 수정 확인", menu)
        act_scan.triggered.connect(self.run_boot_scan)
        act_quit = QAction("종료", menu)
        act_quit.triggered.connect(self.request_quit.emit)
        menu.addAction(act_open)
        menu.addAction(act_scan)
        menu.addSeparator()
        menu.addAction(act_quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()
        # So main_window can dismiss toast before opening login / reauth UI.
        try:
            self._app._cloneup_tray = self  # noqa: SLF001
        except Exception:
            pass

        try:
            migrate_boot_notify_later_policy()
        except Exception:
            pass

        # Delay after logon so disks / VPN settle.
        QTimer.singleShot(8000, self.run_boot_scan)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.request_open_main.emit("")

    def dismiss_boot_toast(self) -> None:
        """Hide toast immediately (login / reauth about to open)."""
        if self._toast is not None:
            try:
                self._toast.blockSignals(True)
                self._toast.close()
            except Exception:
                pass
            self._toast = None
        # Drop in-flight scan result by clearing worker handle after finish.
        self._suppress_toast_until_idle = True

    def run_boot_scan(self) -> None:
        if not load_boot_notify_enabled():
            return
        # Main window open → user can sync in-app; skip alarm entirely.
        if _main_window_visible():
            self.dismiss_boot_toast()
            return
        if github_connect_ui_busy():
            return
        if self._toast is not None and self._toast.isVisible():
            return
        if self._scan_worker is not None and self._scan_worker.isRunning():
            return
        self._suppress_toast_until_idle = False
        # Git status on many recent folders — must not run on the GUI thread
        # (Windows marks the main window as '응답 없음' while scanning).
        w = _BootScanWorker(parent=self)
        w.finished_pending.connect(self._on_scan_done)
        w.failed.connect(self._on_scan_failed)
        self._scan_worker = w
        w.start()

    def _on_scan_failed(self, _msg: str) -> None:
        self._scan_worker = None

    def _on_scan_done(self, pending: object) -> None:
        self._scan_worker = None
        if getattr(self, "_suppress_toast_until_idle", False):
            self._suppress_toast_until_idle = False
            return
        if _main_window_visible() or github_connect_ui_busy():
            return
        items: list[PendingFolder] = list(pending or [])  # type: ignore[arg-type]
        if not items:
            return
        if self._toast is not None and self._toast.isVisible():
            return
        msg = load_last_commit_message() or "Update"
        if msg.strip() in ("첫 업로드", "Initial commit"):
            msg = "Update"
        # Tray-only session: normal toast (design + bottom-right).
        toast = BootNotifyToast(items, default_message=msg, passive=False)
        toast.upload_requested.connect(self._on_upload)
        toast.later_clicked.connect(self._on_later)
        toast.open_app_requested.connect(self.request_open_main.emit)
        toast.snooze_week_requested.connect(self._on_snooze)
        toast.disable_requested.connect(self._on_disable)
        toast.dismissed.connect(self._clear_toast)
        self._toast = toast
        toast.show_toast()

    def _clear_toast(self) -> None:
        self._toast = None

    def _on_later(self) -> None:
        clear_boot_notify_asked()

    def _on_snooze(self) -> None:
        save_boot_notify_snooze_until(snooze_until_days(7))

    def _on_disable(self) -> None:
        save_boot_notify_enabled(False)
        mark_boot_notify_asked()

    def _on_upload(self, folders: list, message: str) -> None:
        mark_boot_notify_asked()
        if self._worker is not None and self._worker.isRunning():
            return
        from app.ui.settings_store import load_hide_real_email

        if self._toast is not None:
            self._toast.set_waiting("GitHub 연결 확인 · 준비 중")

        w = _BootUploadWorker(
            list(folders),
            message,
            hide_real_email=load_hide_real_email(),
            parent=self,
        )
        w.progress.connect(self._on_progress)
        w.finished_ok.connect(self._on_upload_ok)
        w.failed.connect(self._on_upload_fail)
        w.need_auth.connect(self._on_need_auth)
        self._worker = w
        w.start()

    def _on_progress(self, name: str) -> None:
        if self._toast is not None:
            if name.startswith("GitHub"):
                self._toast.set_waiting(f"{name} 중")
            else:
                self._toast.set_waiting(f"{name} · 커밋하고 GitHub로 보내는 중")

    def _on_need_auth(self, folder: str) -> None:
        if self._toast is not None:
            self._toast.close()
            self._toast = None
        self.request_open_main.emit(folder or "")
        QMessageBox.information(
            None,
            "클론업",
            "GitHub 연결이 필요합니다.\n"
            "앱을 연 뒤 「GitHub: 연결」을 해 주세요.",
        )

    def _on_upload_ok(self) -> None:
        if self._toast is not None:
            self._toast.set_done_quiet()
            self._toast = None
        self._tray.showMessage(
            "클론업",
            "GitHub에 올렸습니다.",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _on_upload_fail(self, folder: str, message: str) -> None:
        if message.startswith("auth:"):
            # Handled via need_auth (or duplicate); avoid double dialogs.
            if self._toast is not None:
                self._toast.close()
                self._toast = None
            return
        if self._toast is not None:
            self._toast.close()
            self._toast = None
        self.request_open_main.emit(folder)
        # Keep technical detail for support, but always lead + 다음 for beginners.
        raw = (message or "").strip()
        if len(raw) > 800:
            raw = raw[:800] + "…"
        QMessageBox.warning(
            None,
            "클론업 — 올리지 못했습니다",
            format_error_popup_body(
                raw,
                lead="선택한 폴더를 GitHub에 올리지 못했어요.",
            ),
        )
