"""First-run / on-demand Git setup — full-window simple chooser (plan D DG1+DG2)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QEventLoop, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.git.bootstrap import (
    GIT_DOWNLOAD_URL,
    download_and_run_git_installer,
    open_git_download_page,
    probe_git,
    try_install_git_via_winget,
    winget_available,
)
from app.ui.theme import Palette, active_palette


class _DownloadWorker(QThread):
    """Download + launch installer off the UI thread."""

    progress = Signal(int, int)  # read, total
    finished_ok = Signal(bool, str)

    def __init__(self, *, silent: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.silent = silent

    def run(self) -> None:
        def on_prog(read: int, total: int) -> None:
            self.progress.emit(read, total)

        ok, msg = download_and_run_git_installer(
            silent=self.silent,
            on_progress=on_prog,
        )
        self.finished_ok.emit(ok, msg)


def _dim_for(palette: Palette) -> QColor:
    if palette.name == "dark":
        return QColor(8, 7, 5, 210)
    return QColor(15, 18, 22, 180)


def _card_stylesheet(p: Palette) -> str:
    return f"""
    #gitSetupCard {{
        background: {p.bg_window};
        border-radius: 14px;
        border: 1px solid {p.border};
    }}
    QLabel#gitTitle {{
        font-size: 22px;
        font-weight: 700;
        color: {p.text};
    }}
    QLabel#gitLead {{
        color: {p.text_secondary};
        font-size: 14px;
    }}
    QLabel#gitHint {{
        color: {p.text_muted};
        font-size: 12.5px;
    }}
    QLabel#gitStatus {{
        color: {p.primary};
        font-size: 13px;
        font-weight: 600;
    }}
    QLabel#gitStatusErr {{
        color: {p.danger};
        font-size: 13px;
    }}
    QPushButton#btnPrimary {{
        padding: 16px 20px;
        border-radius: 10px;
        font-size: 16px;
        font-weight: 700;
        color: {p.text_on_primary};
        background: {p.primary};
        border: 1px solid {p.primary};
        min-height: 52px;
        text-align: center;
    }}
    QPushButton#btnPrimary:hover {{
        background: {p.primary_hover};
        border-color: {p.primary_hover};
    }}
    QPushButton#btnPrimary:disabled {{
        color: {p.text_disabled};
        background: {p.bg_muted};
        border-color: {p.border_soft};
    }}
    QPushButton#btnSecondary {{
        padding: 14px 18px;
        border-radius: 10px;
        font-size: 14px;
        font-weight: 600;
        color: {p.text};
        background: {p.bg_input};
        border: 1px solid {p.border_input};
        min-height: 46px;
    }}
    QPushButton#btnSecondary:hover {{
        background: {p.hover_muted};
    }}
    QPushButton#btnSecondary:disabled {{
        color: {p.text_disabled};
        background: {p.bg_muted};
        border-color: {p.border_soft};
    }}
    QPushButton#btnGhost {{
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        color: {p.text_muted};
        background: transparent;
        border: none;
        min-height: 36px;
    }}
    QPushButton#btnGhost:hover {{
        color: {p.text};
        background: {p.hover_muted};
    }}
    QProgressBar {{
        border: 1px solid {p.border_soft};
        border-radius: 6px;
        background: {p.bg_muted};
        text-align: center;
        color: {p.text_secondary};
        min-height: 18px;
    }}
    QProgressBar::chunk {{
        background: {p.primary};
        border-radius: 5px;
    }}
    """


class GitSetupOverlay(QWidget):
    """
    Full-window dim overlay + centered card.

    Beginner flow:
      1) 큰 버튼 「Git 설치하기」 (권장)
      2) 「이미 설치했어요」 → 다시 확인
      3) 「나중에」
    Advanced (「다른 방법」): 브라우저 / winget.
    """

    def __init__(self, parent: QWidget, *, log=None) -> None:
        main = parent
        while main is not None and not isinstance(main, QMainWindow):
            main = main.parentWidget()
        if main is None:
            main = parent

        super().__init__(main)
        self._main = main
        self._log = log
        self._palette = active_palette()
        self._dim = _dim_for(self._palette)
        self._git_ok = False
        self._loop: QEventLoop | None = None
        self._worker: _DownloadWorker | None = None
        self._page = "home"  # home | download | waiting | more | success

        self.setObjectName("gitSetupOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        card = QFrame()
        card.setObjectName("gitSetupCard")
        card.setFixedWidth(480)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        card.setStyleSheet(_card_stylesheet(self._palette))
        self._card = card

        self._title = QLabel("Git이 필요합니다", card)
        self._title.setObjectName("gitTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)

        self._lead = QLabel(
            "올리기 · 받기 · 동기화에는 Git이 필요합니다.\n"
            "아래 중 하나만 고르면 됩니다.",
            card,
        )
        self._lead.setObjectName("gitLead")
        self._lead.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lead.setWordWrap(True)

        self._hint = QLabel("권장: 「Git 설치하기」를 누르세요.", card)
        self._hint.setObjectName("gitHint")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setWordWrap(True)

        self._status = QLabel("", card)
        self._status.setObjectName("gitStatus")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.hide()

        self._progress = QProgressBar(card)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.hide()

        # --- primary actions ---
        self._btn_install = QPushButton("Git 설치하기", card)
        self._btn_install.setObjectName("btnPrimary")
        self._btn_install.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_install.setToolTip("공식 설치 파일을 받아 실행합니다 (권장)")
        self._btn_install.clicked.connect(self._on_install)

        self._btn_installed = QPushButton("이미 설치했어요", card)
        self._btn_installed.setObjectName("btnSecondary")
        self._btn_installed.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_installed.setToolTip("설치를 마쳤다면 눌러 다시 찾습니다")
        self._btn_installed.clicked.connect(self._on_recheck)

        self._btn_retry = QPushButton("설치 끝 · 다시 확인", card)
        self._btn_retry.setObjectName("btnPrimary")
        self._btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_retry.clicked.connect(self._on_recheck)
        self._btn_retry.hide()

        # more methods
        self._btn_browser = QPushButton("브라우저에서 설치 페이지 열기", card)
        self._btn_browser.setObjectName("btnSecondary")
        self._btn_browser.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_browser.clicked.connect(self._on_browser)
        self._btn_browser.hide()

        self._btn_winget = QPushButton("winget으로 설치 (고급)", card)
        self._btn_winget.setObjectName("btnSecondary")
        self._btn_winget.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_winget.clicked.connect(self._on_winget)
        self._btn_winget.hide()
        if not winget_available():
            self._btn_winget.setEnabled(False)
            self._btn_winget.setToolTip("이 PC에서 winget을 찾지 못했습니다.")

        self._btn_back = QPushButton("← 뒤로", card)
        self._btn_back.setObjectName("btnGhost")
        self._btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_back.clicked.connect(self._show_home)
        self._btn_back.hide()

        # footer
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        self._btn_more = QPushButton("다른 방법", card)
        self._btn_more.setObjectName("btnGhost")
        self._btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_more.clicked.connect(self._show_more)
        self._btn_later = QPushButton("나중에", card)
        self._btn_later.setObjectName("btnGhost")
        self._btn_later.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_later.clicked.connect(self._on_later)
        foot.addWidget(self._btn_more, 0, Qt.AlignmentFlag.AlignLeft)
        foot.addStretch(1)
        foot.addWidget(self._btn_later, 0, Qt.AlignmentFlag.AlignRight)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 28, 28, 22)
        lay.setSpacing(12)
        lay.addWidget(self._title)
        lay.addWidget(self._lead)
        lay.addWidget(self._hint)
        lay.addWidget(self._status)
        lay.addWidget(self._progress)
        lay.addSpacing(6)
        lay.addWidget(self._btn_install)
        lay.addWidget(self._btn_installed)
        lay.addWidget(self._btn_retry)
        lay.addWidget(self._btn_browser)
        lay.addWidget(self._btn_winget)
        lay.addWidget(self._btn_back)
        lay.addSpacing(4)
        lay.addLayout(foot)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        row.addStretch(1)
        root.addLayout(row)
        root.addStretch(1)

        if self._main is not None:
            self._main.installEventFilter(self)
        self._sync_geometry()

    # --- geometry / paint ---

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        if obj is self._main and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.WindowStateChange,
            QEvent.Type.Show,
        ):
            self._sync_geometry()
        return super().eventFilter(obj, event)

    def _sync_geometry(self) -> None:
        if self._main is None:
            return
        self.setGeometry(0, 0, self._main.width(), self._main.height())
        self.raise_()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._dim)

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        self._sync_geometry()
        self.raise_()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    # --- public API ---

    def run_modal(self) -> bool:
        """Show overlay and block until user finishes. Returns True if Git is OK."""
        self._show_home()
        self.show()
        self.raise_()
        self._sync_geometry()
        loop = QEventLoop(self)
        self._loop = loop
        loop.exec()
        self._loop = None
        self.hide()
        if self._main is not None:
            self._main.removeEventFilter(self)
        return self._git_ok

    def _finish(self, ok: bool) -> None:
        self._git_ok = ok
        if self._worker is not None and self._worker.isRunning():
            # Let download finish in background; user already chose later/success
            pass
        if self._loop is not None and self._loop.isRunning():
            self._loop.quit()

    def _log_msg(self, msg: str) -> None:
        if self._log:
            self._log(msg)

    # --- pages ---

    def _set_busy(self, busy: bool) -> None:
        for b in (
            self._btn_install,
            self._btn_installed,
            self._btn_retry,
            self._btn_browser,
            self._btn_winget,
            self._btn_more,
            self._btn_later,
            self._btn_back,
        ):
            b.setEnabled(not busy)

    def _show_home(self) -> None:
        self._page = "home"
        self._title.setText("Git이 필요합니다")
        self._lead.setText(
            "올리기 · 받기 · 동기화에는 Git이 필요합니다.\n"
            "아래 중 하나만 고르면 됩니다."
        )
        self._hint.setText("권장: 「Git 설치하기」를 누르세요.")
        self._hint.show()
        self._status.hide()
        self._status.setObjectName("gitStatus")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._progress.hide()
        self._btn_install.show()
        self._btn_installed.show()
        self._btn_retry.hide()
        self._btn_browser.hide()
        self._btn_winget.hide()
        self._btn_back.hide()
        self._btn_more.show()
        self._btn_later.show()
        self._set_busy(False)

    def _show_download(self) -> None:
        self._page = "download"
        self._title.setText("Git 설치 준비 중")
        self._lead.setText(
            "공식 설치 파일을 받는 중입니다.\n"
            "끝나면 설치 창이 열립니다."
        )
        self._hint.setText("창을 닫지 마세요.")
        self._hint.show()
        self._status.setObjectName("gitStatus")
        self._status.setText("다운로드 시작…")
        self._status.show()
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.show()
        self._btn_install.hide()
        self._btn_installed.hide()
        self._btn_retry.hide()
        self._btn_browser.hide()
        self._btn_winget.hide()
        self._btn_back.hide()
        self._btn_more.hide()
        self._btn_later.setEnabled(True)
        self._btn_later.show()
        self._set_busy(True)
        self._btn_later.setEnabled(True)

    def _show_waiting(self) -> None:
        self._page = "waiting"
        self._title.setText("설치를 마쳐 주세요")
        self._lead.setText(
            "Git 설치 창이 열렸다면 안내에 따라 설치를 끝낸 뒤,\n"
            "아래 버튼을 누르세요."
        )
        self._hint.setText("설치 창이 안 보이면 작업 표시줄을 확인해 보세요.")
        self._hint.show()
        self._status.hide()
        self._progress.hide()
        self._btn_install.hide()
        self._btn_installed.hide()
        self._btn_retry.show()
        self._btn_browser.hide()
        self._btn_winget.hide()
        self._btn_back.hide()
        self._btn_more.show()
        self._btn_later.show()
        self._set_busy(False)

    def _show_more(self) -> None:
        self._page = "more"
        self._title.setText("다른 설치 방법")
        self._lead.setText(
            "보통은 「Git 설치하기」만으로 충분합니다.\n"
            "막힐 때만 아래를 쓰세요."
        )
        self._hint.setText(f"수동 페이지: {GIT_DOWNLOAD_URL}")
        self._hint.show()
        self._status.hide()
        self._progress.hide()
        self._btn_install.hide()
        self._btn_installed.hide()
        self._btn_retry.hide()
        self._btn_browser.show()
        self._btn_winget.show()
        self._btn_back.show()
        self._btn_more.hide()
        self._btn_later.show()
        self._set_busy(False)

    def _show_success(self, detail: str) -> None:
        self._page = "success"
        self._title.setText("Git 준비 완료")
        self._lead.setText("이제 올리기 · 받기 · 동기화를 쓸 수 있습니다.")
        self._hint.hide()
        self._status.setObjectName("gitStatus")
        self._status.setText(detail)
        self._status.show()
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._progress.hide()
        self._btn_install.hide()
        self._btn_installed.hide()
        self._btn_retry.hide()
        self._btn_browser.hide()
        self._btn_winget.hide()
        self._btn_back.hide()
        self._btn_more.hide()
        self._btn_later.setText("시작하기")
        self._btn_later.show()
        self._set_busy(False)
        # Auto-close shortly for snappy UX
        from PySide6.QtCore import QTimer

        QTimer.singleShot(900, lambda: self._finish(True))

    def _show_error(self, msg: str) -> None:
        self._status.setObjectName("gitStatusErr")
        self._status.setText(msg)
        self._status.show()
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    # --- actions ---

    def _on_install(self) -> None:
        self._log_msg("공식 Git 설치 파일을 다운로드합니다…")
        self._show_download()

        worker = _DownloadWorker(silent=False, parent=self)
        self._worker = worker

        def on_prog(read: int, total: int) -> None:
            if total > 0:
                self._progress.setRange(0, 100)
                pct = min(100, int(read * 100 / total))
                self._progress.setValue(pct)
                mb_r, mb_t = read / (1024 * 1024), total / (1024 * 1024)
                self._status.setText(f"받는 중… {mb_r:.1f} / {mb_t:.1f} MB")
            else:
                self._progress.setRange(0, 0)
                self._status.setText(f"받는 중… {read / (1024 * 1024):.1f} MB")

        def on_done(ok: bool, msg: str) -> None:
            self._worker = None
            self._log_msg(msg[:1500] if msg else ("설치 프로그램 실행" if ok else "실패"))
            if not ok:
                self._show_home()
                self._show_error(
                    "설치 파일을 받거나 실행하지 못했습니다.\n"
                    "「다른 방법」→ 브라우저로 설치해 보세요."
                )
                return
            self._show_waiting()

        worker.progress.connect(on_prog)
        worker.finished_ok.connect(on_done)
        worker.start()

    def _on_recheck(self) -> None:
        probe = probe_git()
        if probe.ok:
            detail = f"{probe.message}"
            if probe.path:
                detail = f"{probe.message}\n{probe.path}"
            self._log_msg(f"Git 확인됨: {probe.message} ({probe.path or ''})")
            self._show_success(detail)
            return
        self._log_msg(f"아직 Git 없음: {probe.message}")
        if self._page == "waiting":
            self._show_error(
                "아직 Git을 찾지 못했습니다.\n"
                "설치를 끝낸 뒤 다시 누르거나, CloneUp을 종료 후 다시 실행해 주세요."
            )
            self._btn_retry.show()
            self._set_busy(False)
        else:
            self._show_error(
                "아직 Git을 찾지 못했습니다.\n"
                "설치가 끝났다면 PC를 다시 시작하거나 앱을 다시 실행해 보세요."
            )

    def _on_browser(self) -> None:
        ok = open_git_download_page()
        self._log_msg(
            "Git 설치 페이지를 열었습니다. 설치가 끝나면 「이미 설치했어요」를 누르세요."
            if ok
            else f"브라우저를 열 수 없습니다. 직접 방문: {GIT_DOWNLOAD_URL}"
        )
        self._show_waiting()
        self._title.setText("브라우저에서 설치")
        self._lead.setText(
            "열린 페이지에서 Git을 설치한 뒤,\n"
            "「설치 끝 · 다시 확인」을 누르세요."
        )
        if not ok:
            self._show_error(f"브라우저를 열 수 없습니다.\n{GIT_DOWNLOAD_URL}")

    def _on_winget(self) -> None:
        self._log_msg("winget으로 Git 설치를 시도합니다. 잠시 기다려 주세요…")
        self._title.setText("winget 설치 중")
        self._lead.setText("잠시만 기다려 주세요…")
        self._hint.hide()
        self._status.setObjectName("gitStatus")
        self._status.setText("winget 실행 중…")
        self._status.show()
        self._progress.setRange(0, 0)
        self._progress.show()
        self._btn_browser.hide()
        self._btn_winget.hide()
        self._btn_back.hide()
        self._set_busy(True)
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()
        ok, detail = try_install_git_via_winget()
        self._log_msg(detail[:1500] if detail else ("성공" if ok else "실패"))
        self._progress.hide()
        if ok:
            probe = probe_git()
            if probe.ok:
                self._show_success(probe.message)
                return
            self._show_waiting()
            self._show_error(
                "설치는 된 것 같지만 아직 찾지 못했습니다.\n"
                "앱을 종료한 뒤 다시 실행해 주세요."
            )
            return
        self._show_more()
        self._show_error(
            "winget 설치에 실패했습니다.\n"
            "「Git 설치하기」 또는 브라우저 설치를 이용해 주세요."
        )

    def _on_later(self) -> None:
        if self._page == "success":
            self._finish(True)
            return
        self._log_msg(
            "Git 설치를 나중에 하기로 했습니다. 상태 줄에 Git: 없음 이 표시됩니다."
        )
        self._finish(False)


def ensure_git_or_offer_setup(
    parent: QWidget | None,
    *,
    log=None,
) -> bool:
    """
    If Git is available, return True.
    Otherwise show a full-window beginner chooser, then re-probe.

    Returns True only when Git is usable after the interaction (or was already OK).
    """
    probe = probe_git()
    if probe.ok:
        return True

    if log:
        log(f"Git 없음: {probe.message}")

    if parent is None:
        return False

    overlay = GitSetupOverlay(parent, log=log)
    return overlay.run_modal()
