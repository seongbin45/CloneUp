"""System tray host: boot scan + notify toast (no main window required)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from app.ui.boot_notify import BootNotifyToast
from app.ui.boot_scan import (
    mark_boot_notify_asked,
    should_show_boot_toast,
    snooze_until_days,
)
from app.ui.icons import load_app_icon
from app.ui.settings_store import (
    load_boot_notify_enabled,
    load_last_commit_message,
    save_boot_notify_enabled,
    save_boot_notify_snooze_until,
)


class _BootUploadWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal()
    failed = Signal(str, str)  # folder, message (safety or sync)

    def __init__(
        self,
        folders: list[str],
        message: str,
        token: str,
        user: dict,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._folders = list(folders)
        self._message = message
        self._token = token
        self._user = user

    def run(self) -> None:  # noqa: N802
        from pathlib import Path

        from app.git.sync_ops import SyncError, commit_and_push

        for raw in self._folders:
            folder = Path(raw)
            self.progress.emit(folder.name)
            try:
                commit_and_push(
                    folder,
                    message=self._message,
                    token=self._token,
                    user=self._user,
                    allow_secrets=False,
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

        # Delay after logon so disks / VPN settle.
        QTimer.singleShot(8000, self.run_boot_scan)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.request_open_main.emit("")

    def run_boot_scan(self) -> None:
        if not load_boot_notify_enabled():
            return
        if self._toast is not None and self._toast.isVisible():
            return
        pending = should_show_boot_toast()
        if not pending:
            return
        mark_boot_notify_asked()
        msg = load_last_commit_message() or "Update"
        if msg.strip() in ("첫 업로드", "Initial commit"):
            msg = "Update"
        toast = BootNotifyToast(pending, default_message=msg)
        toast.upload_requested.connect(self._on_upload)
        toast.later_clicked.connect(lambda: None)
        toast.open_app_requested.connect(self.request_open_main.emit)
        toast.snooze_week_requested.connect(self._on_snooze)
        toast.disable_requested.connect(self._on_disable)
        toast.dismissed.connect(self._clear_toast)
        self._toast = toast
        toast.show()
        toast.raise_()

    def _clear_toast(self) -> None:
        self._toast = None

    def _on_snooze(self) -> None:
        save_boot_notify_snooze_until(snooze_until_days(7))

    def _on_disable(self) -> None:
        save_boot_notify_enabled(False)

    def _on_upload(self, folders: list, message: str) -> None:
        from app.auth.session import AuthError, ensure_valid_token

        try:
            token, user = ensure_valid_token()
        except AuthError as e:
            if self._toast is not None:
                self._toast.close()
                self._toast = None
            self.request_open_main.emit(folders[0] if folders else "")
            QMessageBox.information(
                None,
                "클론업",
                "GitHub 연결이 필요합니다.\n"
                "앱을 연 뒤 「GitHub: 연결」을 해 주세요.\n\n"
                f"{e}",
            )
            return
        except Exception:
            if self._toast is not None:
                self._toast.close()
                self._toast = None
            self.request_open_main.emit(folders[0] if folders else "")
            QMessageBox.information(
                None,
                "클론업",
                "GitHub 연결이 필요합니다.\n"
                "앱을 연 뒤 「GitHub: 연결」을 해 주세요.",
            )
            return
        if self._worker is not None and self._worker.isRunning():
            return
        w = _BootUploadWorker(
            list(folders),
            message,
            str(token),
            dict(user or {}),
            parent=self,
        )
        w.progress.connect(self._on_progress)
        w.finished_ok.connect(self._on_upload_ok)
        w.failed.connect(self._on_upload_fail)
        self._worker = w
        w.start()

    def _on_progress(self, name: str) -> None:
        if self._toast is not None:
            self._toast.set_waiting(f"{name} · 커밋하고 GitHub로 보내는 중")

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
        if self._toast is not None:
            self._toast.close()
            self._toast = None
        self.request_open_main.emit(folder)
        # Safety / sync errors: show in app context
        QMessageBox.warning(
            None,
            "클론업 — 올리지 못했습니다",
            message[:800],
        )
