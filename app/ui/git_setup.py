"""First-run / on-demand Git setup dialog (plan D — DG1 + DG2)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QMessageBox,
    QProgressDialog,
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


def ensure_git_or_offer_setup(
    parent: QWidget | None,
    *,
    log=None,
) -> bool:
    """
    If Git is available, return True.
    Otherwise show a beginner-friendly dialog to install/open download, then re-probe.

    Returns True only when Git is usable after the interaction (or was already OK).
    """
    probe = probe_git()
    if probe.ok:
        return True

    if log:
        log(f"Git 없음: {probe.message}")

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Git 이 필요합니다")
    box.setText(
        "CloneUp 은 컴퓨터에 Git 이 있어야 동작합니다.\n"
        "지금 설치를 도와드릴까요?"
    )
    box.setInformativeText(
        "• 「설치 파일 받기·실행」— 공식 Git 설치 파일을 받아 실행합니다. (권장)\n"
        f"• 「설치 페이지 열기」— 브라우저로 안내합니다.\n"
        f"  ({GIT_DOWNLOAD_URL})\n"
        "• 「winget 으로 설치」— Windows 패키지 관리자로 설치를 시도합니다.\n"
        "• 「다시 확인」— 이미 설치했다면 PATH 반영 후 눌러 주세요.\n"
        "• 「나중에」— 앱은 열리지만 올리기/받기/동기화는 사용할 수 없습니다."
    )

    btn_dl = box.addButton("설치 파일 받기·실행", QMessageBox.ButtonRole.AcceptRole)
    btn_page = box.addButton("설치 페이지 열기", QMessageBox.ButtonRole.ActionRole)
    btn_winget = box.addButton("winget 으로 설치", QMessageBox.ButtonRole.ActionRole)
    btn_retry = box.addButton("다시 확인", QMessageBox.ButtonRole.ActionRole)
    btn_later = box.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
    if not winget_available():
        btn_winget.setEnabled(False)
        btn_winget.setToolTip("이 PC 에서 winget 을 찾지 못했습니다.")

    box.setDefaultButton(btn_dl)
    box.exec()
    clicked = box.clickedButton()

    if clicked is btn_dl:
        return _download_and_install(parent, log=log)

    if clicked is btn_page:
        ok = open_git_download_page()
        if log:
            log(
                "Git 설치 페이지를 열었습니다. 설치가 끝나면 「다시 확인」을 누르세요."
                if ok
                else f"브라우저를 열 수 없습니다. 직접 방문: {GIT_DOWNLOAD_URL}"
            )
        return _offer_recheck(parent, log=log)

    if clicked is btn_winget:
        if log:
            log("winget 으로 Git 설치를 시도합니다. 잠시 기다려 주세요…")
        ok, detail = try_install_git_via_winget()
        if log:
            log(detail[:1500] if detail else ("성공" if ok else "실패"))
        if ok:
            return _finish_after_install_attempt(parent, log=log)
        QMessageBox.warning(
            parent,
            "winget 설치 실패",
            "winget 설치에 실패했습니다.\n"
            "「설치 파일 받기·실행」을 이용해 주세요.\n\n"
            f"{(detail or '')[:800]}",
        )
        return False

    if clicked is btn_retry:
        return _offer_recheck(parent, log=log, direct=True)

    if log:
        log("Git 설치를 나중에 하기로 했습니다. 상태 줄에 Git: 없음 이 표시됩니다.")
    return False


def _download_and_install(parent: QWidget | None, *, log=None) -> bool:
    """DG2: download installer with progress, launch GUI setup."""
    if log:
        log("공식 Git 설치 파일을 다운로드합니다…")

    progress = QProgressDialog(
        "Git 설치 파일을 받는 중…",
        "취소",
        0,
        100,
        parent,
    )
    progress.setWindowTitle("Git 설치")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)

    worker = _DownloadWorker(silent=False, parent=parent)
    result: dict = {"ok": False, "msg": "", "done": False}

    def on_prog(read: int, total: int) -> None:
        if progress.wasCanceled():
            return
        if total > 0:
            progress.setMaximum(100)
            progress.setValue(min(100, int(read * 100 / total)))
            mb_r, mb_t = read / (1024 * 1024), total / (1024 * 1024)
            progress.setLabelText(f"Git 설치 파일 받는 중… {mb_r:.1f} / {mb_t:.1f} MB")
        else:
            progress.setMaximum(0)  # busy
            progress.setLabelText(f"Git 설치 파일 받는 중… {read / (1024 * 1024):.1f} MB")

    def on_done(ok: bool, msg: str) -> None:
        result["ok"] = ok
        result["msg"] = msg
        result["done"] = True
        progress.reset()

    worker.progress.connect(on_prog)
    worker.finished_ok.connect(on_done)
    worker.start()

    # Modal wait loop
    while worker.isRunning():
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()
        if progress.wasCanceled():
            # Cannot cleanly abort urllib mid-flight easily; just wait
            progress.setLabelText("취소 요청… 다운로드가 끝나는 대로 중단합니다.")
        worker.wait(50)

    worker.wait(5000)
    progress.close()

    ok, msg = result["ok"], result["msg"]
    if log:
        log(msg[:1500] if msg else ("설치 프로그램 실행" if ok else "실패"))

    if not ok:
        QMessageBox.warning(
            parent,
            "다운로드/실행 실패",
            "설치 파일을 받거나 실행하지 못했습니다.\n"
            f"「설치 페이지 열기」로 수동 설치해 주세요.\n\n{msg[:800]}",
        )
        return False

    QMessageBox.information(
        parent,
        "Git 설치 프로그램",
        "Git 설치 창이 열렸다면 안내에 따라 설치를 완료하세요.\n\n"
        "설치가 끝나면 아래 「확인」 후 「다시 확인」을 누르거나,\n"
        "CloneUp 을 완전히 종료했다가 다시 실행해 주세요.",
    )
    return _offer_recheck(parent, log=log)


def _finish_after_install_attempt(parent: QWidget | None, *, log=None) -> bool:
    probe2 = probe_git()
    if probe2.ok:
        if log:
            log(f"Git 준비됨: {probe2.message}")
        QMessageBox.information(
            parent,
            "Git 설치",
            f"Git 을 사용할 수 있습니다.\n{probe2.message}",
        )
        return True
    QMessageBox.information(
        parent,
        "Git 설치",
        "설치가 끝난 것 같습니다.\n"
        "그래도 CloneUp 이 Git 을 못 찾으면 앱을 완전히 종료한 뒤 "
        "다시 실행해 주세요. (PATH 반영)",
    )
    return False


def _offer_recheck(parent: QWidget | None, *, log=None, direct: bool = False) -> bool:
    if not direct:
        ans = QMessageBox.question(
            parent,
            "Git 다시 확인",
            "Git 설치를 마쳤다면 「예」를 눌러 다시 확인합니다.\n"
            "아직이면 「아니오」를 누르세요.",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return False
    probe = probe_git()
    if probe.ok:
        if log:
            log(f"Git 확인됨: {probe.message} ({probe.path})")
        QMessageBox.information(
            parent,
            "Git 확인",
            f"Git 을 찾았습니다.\n{probe.message}\n{probe.path or ''}",
        )
        return True
    if log:
        log(f"아직 Git 없음: {probe.message}")
    QMessageBox.warning(
        parent,
        "Git 없음",
        "아직 Git 을 찾지 못했습니다.\n"
        "설치 후 터미널/앱을 다시 열면 PATH 가 반영되는 경우가 많습니다.\n\n"
        f"{probe.message}",
    )
    return False
