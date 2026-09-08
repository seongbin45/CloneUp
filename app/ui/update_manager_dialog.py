"""Update-manager status / control dialog (tray · settings entry point)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import active_palette
from app.util.update_manager_health import (
    UpdateManagerHealth,
    manager_exe_path,
    manager_log_path,
    probe_update_manager,
    read_current_run_id,
    read_run_status,
    try_start_manager,
)

# Tier-2 dialog poll (T2-1o / T2-1o′)
_START_WAIT_SEC = 15
_RESULT_POLL_CAP_SEC = 15 * 60
_TERMINAL_PHASES = frozenset(
    {
        "no_install",
        "no_version",
        "no_release",
        "up_to_date",
        "deferred_ui",
        "killed_failed",
        "updated",
        "error",
        "pending_busy",
        "pending_acl_failed",
    }
)
_PHASE_KO = {
    "running": "확인 중…",
    "downloading": "새 버전을 받는 중…",
    "up_to_date": "이미 최신입니다",
    "updated": "업데이트를 적용했습니다",
    "deferred_ui": "메인 창이 열려 있어 적용을 미뤘습니다 (다운로드는 보관됨)",
    "pending_busy": "다른 확인이 진행 중이라 이번 요청은 대기했습니다",
    "pending_acl_failed": "저장 폴더 권한 설정에 실패했습니다",
    "no_install": "CloneUp 설치 폴더를 찾지 못했습니다",
    "no_version": "설치된 버전을 읽지 못했습니다",
    "no_release": "새 릴리즈를 확인하지 못했습니다 (네트워크)",
    "killed_failed": "실행 중인 CloneUp을 끝내지 못해 적용하지 못했습니다",
    "error": "확인 중 오류가 났습니다",
}


def _read_install_version(install_guess: str) -> str:
    if not install_guess:
        return "(알 수 없음)"
    path = Path(install_guess) / "VERSION"
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace").strip() or "(비어 있음)"
    except OSError:
        pass
    return "(없음)"


def _status_ko(health: UpdateManagerHealth) -> tuple[str, str]:
    """Return (headline, color_key) for the summary line."""
    p = active_palette()
    if health.ok:
        # Soft network lines may still appear in the log panel — not a failure.
        if health.log_error_hits and health.process_running:
            return "실행 중 (가끔 네트워크 지연 기록이 있을 수 있음)", p.success_dot
        return "정상으로 보입니다", p.success_dot
    # Soft-only: process up but Run key missing is still usable
    if health.problems == ["run_key_missing"] and health.process_running:
        return "실행 중 (자동시작 등록만 없음)", p.warn_text
    if health.problems == ["log_network"]:
        return "네트워크 확인이 잠깐 실패했던 기록이 있습니다", p.warn_text
    if "exe_missing" in health.problems:
        return "업데이트 관리자 파일이 없습니다", p.danger
    if "process_not_running" in health.problems:
        return "지금 실행되고 있지 않습니다", p.warn_text
    if "log_errors" in health.problems and any(
        "apply failed" in (x or "").lower() for x in health.log_error_hits
    ):
        return "업데이트 적용에 실패한 기록이 있습니다", p.danger
    return "확인이 필요합니다", p.warn_text


def _pid_alive(pid: int | None) -> bool:
    if not pid or int(pid) <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False
    try:
        import ctypes

        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    except Exception:
        return False


class _ProbeWorker(QThread):
    finished_health = Signal(object)
    failed = Signal(str)

    def __init__(self, *, attempt_restart: bool, parent=None) -> None:
        super().__init__(parent)
        self._attempt_restart = bool(attempt_restart)

    def run(self) -> None:  # noqa: N802
        try:
            h = probe_update_manager(attempt_restart=self._attempt_restart)
            self.finished_health.emit(h)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class _OncePollWorker(QThread):
    """Trigger one check and poll status/current.json (T2-1o / T2-1o′)."""

    progress = Signal(str)
    finished_ok = Signal(str, str)  # headline, detail
    finished_bg = Signal(str)  # continue in background copy
    failed = Signal(str)

    def __init__(self, exe: Path, parent=None) -> None:
        super().__init__(parent)
        self._exe = exe

    def run(self) -> None:  # noqa: N802
        try:
            snap = read_current_run_id()
            self.progress.emit("확인 요청을 보내는 중…")
            if not try_start_manager(self._exe, once=True):
                self.failed.emit("확인 요청을 시작하지 못했습니다.")
                return

            # Start-wait: new run_id within 15s
            deadline = time.monotonic() + _START_WAIT_SEC
            new_id: str | None = None
            while time.monotonic() < deadline:
                cur = read_current_run_id()
                if cur and cur != snap:
                    new_id = cur
                    break
                time.sleep(0.4)
            if not new_id:
                self.failed.emit(
                    "확인 요청을 보냈지만 응답이 없습니다.\n"
                    "잠시 후 「새로고침」으로 로그를 확인해 주세요."
                )
                return

            self.progress.emit("업데이트 관리자가 확인 중입니다…")
            poll_deadline = time.monotonic() + _RESULT_POLL_CAP_SEC
            last_phase = ""
            while time.monotonic() < poll_deadline:
                data = read_run_status(new_id) or {}
                phase = str(data.get("phase") or "")
                if phase and phase != last_phase:
                    last_phase = phase
                    self.progress.emit(_PHASE_KO.get(phase, f"상태: {phase}"))
                finished_at = data.get("finished_at")
                if finished_at or phase in _TERMINAL_PHASES:
                    headline = _PHASE_KO.get(phase, phase or "완료")
                    err = str(data.get("error") or "").strip()
                    detail_parts = [
                        f"결과: {phase}",
                        f"로컬: {data.get('local') or '-'}",
                        f"원격: {data.get('remote') or '-'}",
                    ]
                    if err:
                        detail_parts.append(f"오류: {err[:300]}")
                    self.finished_ok.emit(headline, "\n".join(detail_parts))
                    return
                pid = data.get("pid")
                try:
                    pid_i = int(pid) if pid is not None else None
                except (TypeError, ValueError):
                    pid_i = None
                if pid_i and not _pid_alive(pid_i) and phase not in ("running", "downloading"):
                    # Process gone without terminal — treat as lost
                    self.failed.emit(
                        "확인 프로세스가 중간에 종료된 것 같습니다.\n로그를 확인해 주세요."
                    )
                    return
                if pid_i and not _pid_alive(pid_i) and phase in ("running", "downloading"):
                    self.failed.emit(
                        "확인이 끝나기 전에 프로세스가 종료되었습니다.\n로그를 확인해 주세요."
                    )
                    return
                time.sleep(0.8)

            # 15m cap — if still alive downloading, background (not hard fail)
            data = read_run_status(new_id) or {}
            phase = str(data.get("phase") or "")
            pid = data.get("pid")
            try:
                pid_i = int(pid) if pid is not None else None
            except (TypeError, ValueError):
                pid_i = None
            if phase in ("running", "downloading") and _pid_alive(pid_i):
                self.finished_bg.emit(
                    "백그라운드에서 계속 확인 중입니다. 끝나면 알림으로 알려 드립니다."
                )
                return
            self.failed.emit(
                "확인이 오래 걸려 대기 시간을 넘겼습니다.\n"
                "로그 폴더에서 진행 상황을 확인해 주세요."
            )
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class UpdateManagerDialog(QDialog):
    """
    Management UI for the independent update manager.

    Background tray checks stay silent; this dialog is for the explicit
    「업데이트 관리자 확인」 action.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        p = active_palette()
        self.setWindowTitle("클론업 — 업데이트 관리자")
        self.setModal(True)
        # +30px vs first ship (480×420 / 520×480) — more room for log + status.
        self.setMinimumSize(510, 450)
        self.resize(550, 510)
        self._worker: _ProbeWorker | None = None
        self._once_worker: _OncePollWorker | None = None
        self._health: UpdateManagerHealth | None = None

        self.setStyleSheet(
            f"QDialog {{ background: {p.bg_window}; }}"
            f"QLabel {{ color: {p.text}; }}"
            f"QTextEdit {{ background: {p.bg_muted}; color: {p.text}; "
            f"border: 1px solid {p.border_soft}; border-radius: 6px; "
            f"padding: 8px; font-family: Consolas, 'Courier New', monospace; "
            f"font-size: 11.5px; }}"
            f"QPushButton {{ background: {p.bg_input}; color: {p.text}; "
            f"border: 1px solid {p.border}; border-radius: 6px; "
            f"padding: 7px 12px; font-size: 12.5px; }}"
            f"QPushButton:hover {{ background: {p.hover_muted}; }}"
            f"QPushButton#primary {{ background: {p.primary}; color: {p.text_on_primary}; "
            f"border: none; font-weight: 600; }}"
            f"QPushButton#primary:hover {{ background: {p.primary_hover}; }}"
            f"QPushButton:disabled {{ color: {p.text_disabled}; }}"
        )

        title = QLabel("업데이트 관리자")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {p.text};")

        hint = QLabel(
            "백그라운드에서 새 버전을 받아 설치하는 도우미입니다. "
            "검은 터미널 창 없이 조용히 돌아가야 정상입니다."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {p.text_muted}; font-size: 12px;")

        self._summary = QLabel("확인 중…")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {p.text};")

        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._detail.setStyleSheet(f"color: {p.text_secondary}; font-size: 12.5px;")

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("최근 로그 / 진단 요약이 여기 표시됩니다.")

        # Actions
        self._btn_refresh = QPushButton("새로고침")
        self._btn_refresh.clicked.connect(lambda: self.refresh(attempt_restart=False))

        self._btn_start = QPushButton("지금 시작")
        self._btn_start.setObjectName("primary")
        self._btn_start.clicked.connect(self._on_start)

        self._btn_once = QPushButton("업데이트 한 번 확인")
        self._btn_once.clicked.connect(self._on_once)

        self._btn_log = QPushButton("로그 폴더")
        self._btn_log.clicked.connect(self._on_open_log_dir)

        self._btn_copy = QPushButton("상태 복사")
        self._btn_copy.clicked.connect(self._on_copy)

        self._btn_close = QPushButton("닫기")
        self._btn_close.clicked.connect(self.accept)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self._btn_start)
        row1.addWidget(self._btn_once)
        row1.addWidget(self._btn_refresh)
        row1.addStretch(1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self._btn_log)
        row2.addWidget(self._btn_copy)
        row2.addStretch(1)
        row2.addWidget(self._btn_close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self._summary)
        layout.addWidget(self._detail)
        layout.addWidget(self._log, 1)
        layout.addLayout(row1)
        layout.addLayout(row2)

        self.refresh(attempt_restart=False)

    def _set_busy(self, busy: bool) -> None:
        for b in (
            self._btn_refresh,
            self._btn_start,
            self._btn_once,
            self._btn_log,
            self._btn_copy,
        ):
            b.setEnabled(not busy)
        if busy:
            self._summary.setText("확인 중…")

    def refresh(self, *, attempt_restart: bool = False) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        if self._once_worker is not None and self._once_worker.isRunning():
            return
        self._set_busy(True)
        w = _ProbeWorker(attempt_restart=attempt_restart, parent=self)
        w.finished_health.connect(self._on_probed)
        w.failed.connect(self._on_probe_failed)
        self._worker = w
        w.start()

    def _on_probe_failed(self, msg: str) -> None:
        self._worker = None
        self._set_busy(False)
        p = active_palette()
        self._summary.setText("상태를 읽지 못했습니다")
        self._summary.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {p.danger};"
        )
        self._detail.setText(msg[:400])
        self._log.setPlainText(msg)

    def _on_probed(self, health: object) -> None:
        self._worker = None
        self._set_busy(False)
        if not isinstance(health, UpdateManagerHealth):
            self._on_probe_failed("unexpected probe result")
            return
        self._health = health
        self._apply_health(health)

    def _apply_health(self, h: UpdateManagerHealth) -> None:
        headline, color = _status_ko(h)
        self._summary.setText(headline)
        self._summary.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {color};"
        )

        ver = _read_install_version(h.app_install_guess or "")
        auto = h.run_key_value or "(없음)"
        if len(auto) > 90:
            auto = auto[:87] + "…"
        lines = [
            f"설치 버전: {ver}",
            f"실행 파일: {'있음' if h.exe_present else '없음'}"
            + (f"\n  {h.exe_path}" if h.exe_path else ""),
            f"프로세스: {'실행 중' if h.process_running else '중지됨'}",
            f"자동시작: {'등록됨' if h.run_key_present else '없음'}",
            f"  {auto}",
            f"앱 폴더: {h.app_install_guess or '(못 찾음)'}",
        ]
        if h.problems:
            lines.append("문제: " + ", ".join(h.problems))
        if h.restarted:
            lines.append("(방금 다시 시작해 보았습니다)")
        self._detail.setText("\n".join(lines))

        log_bits: list[str] = []
        if h.log_error_hits:
            log_bits.append("최근 오류성 로그:")
            log_bits.extend(f"  · {x}" for x in h.log_error_hits)
            log_bits.append("")
        if h.log_tail.strip():
            log_bits.append("로그 끝부분:")
            log_bits.append(h.log_tail.strip())
        elif not h.log_present:
            log_bits.append("(아직 로그 파일이 없습니다. 「지금 시작」 후 다시 확인하세요.)")
        else:
            log_bits.append("(로그는 있으나 비어 있습니다)")
        self._log.setPlainText("\n".join(log_bits))

        self._btn_start.setEnabled(h.exe_present and not h.process_running)
        self._btn_once.setEnabled(h.exe_present)

    def _on_start(self) -> None:
        exe = manager_exe_path()
        if not exe.is_file():
            QMessageBox.warning(
                self,
                "업데이트 관리자",
                "실행 파일을 찾을 수 없습니다.\nSetup으로 CloneUp을 다시 설치해 주세요.",
            )
            return
        if try_start_manager(exe, once=False):
            self.refresh(attempt_restart=False)
        else:
            QMessageBox.warning(self, "업데이트 관리자", "시작에 실패했습니다.")

    def _on_once(self) -> None:
        exe = manager_exe_path()
        if not exe.is_file():
            QMessageBox.warning(
                self,
                "업데이트 관리자",
                "실행 파일을 찾을 수 없습니다.",
            )
            return
        if self._once_worker is not None and self._once_worker.isRunning():
            return
        self._set_busy(True)
        p = active_palette()
        self._summary.setText("확인 요청을 보내는 중…")
        self._summary.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {p.text};"
        )
        w = _OncePollWorker(exe, parent=self)
        w.progress.connect(self._on_once_progress)
        w.finished_ok.connect(self._on_once_ok)
        w.finished_bg.connect(self._on_once_bg)
        w.failed.connect(self._on_once_failed)
        self._once_worker = w
        w.start()

    def _on_once_progress(self, msg: str) -> None:
        self._summary.setText(msg)

    def _on_once_ok(self, headline: str, detail: str) -> None:
        self._once_worker = None
        self._set_busy(False)
        p = active_palette()
        danger = any(
            x in headline
            for x in ("실패", "오류", "권한", "찾지", "끝내지")
        )
        color = p.danger if danger else p.success_dot
        if "미뤘" in headline or "대기" in headline:
            color = p.warn_text
        self._summary.setText(headline)
        self._summary.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {color};"
        )
        self._detail.setText(detail)
        QMessageBox.information(self, "업데이트 관리자", headline)
        self.refresh(attempt_restart=False)

    def _on_once_bg(self, msg: str) -> None:
        self._once_worker = None
        self._set_busy(False)
        p = active_palette()
        self._summary.setText(msg)
        self._summary.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {p.warn_text};"
        )
        QMessageBox.information(self, "업데이트 관리자", msg)
        self.refresh(attempt_restart=False)

    def _on_once_failed(self, msg: str) -> None:
        self._once_worker = None
        self._set_busy(False)
        p = active_palette()
        self._summary.setText("확인 요청 결과 없음")
        self._summary.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {p.warn_text};"
        )
        QMessageBox.warning(self, "업데이트 관리자", msg)
        self.refresh(attempt_restart=False)

    def _on_open_log_dir(self) -> None:
        path = manager_log_path().parent
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))  # noqa: S606 — Windows explorer
        except OSError as e:
            QMessageBox.warning(self, "업데이트 관리자", f"폴더를 열 수 없습니다.\n{e}")

    def _on_copy(self) -> None:
        text = self._detail.text() + "\n\n" + self._log.toPlainText()
        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(text)
            QMessageBox.information(self, "업데이트 관리자", "상태를 클립보드에 복사했습니다.")


def open_update_manager_dialog(parent: QWidget | None = None) -> UpdateManagerDialog:
    """Show (or raise) the management dialog."""
    dlg = UpdateManagerDialog(parent)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg
