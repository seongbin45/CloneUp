"""Beginner popup for oversized files (plan rev.3 Stage A/B)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.git.large_files import (
    RELEASE_MAX_BYTES,
    LargeFileHit,
)


class LargeFileChoice(str, Enum):
    UNTRACK_WORKTREE = "u_worktree"
    UNTRACK_HIST = "u_hist"
    RELEASES = "releases"
    EXTERNAL = "external"
    FRESH = "fresh"  # N — only when remote empty
    CANCEL = "cancel"


def _format_hits(hits: list[LargeFileHit]) -> str:
    lines: list[str] = []
    for h in hits:
        lines.append(f"· {h.rel}  ({h.size_mib:.1f} MB)")
    return "\n".join(lines)


def show_large_file_dialog(
    parent,
    *,
    blocks: list[LargeFileHit],
    mode: str = "working_tree",
    ahead_count: int | None = None,
    offer_hist: bool = False,
    offer_fresh: bool = False,
) -> LargeFileChoice:
    """
    Returns the user choice. Does not mutate the repo.

    ``mode``: ``working_tree`` | ``history_trap``.
    """
    if not blocks:
        return LargeFileChoice.CANCEL

    over_release = any(h.size > RELEASE_MAX_BYTES for h in blocks)
    dlg = QDialog(parent)
    dlg.setWindowTitle("큰 파일이 있어 올릴 수 없어요")
    dlg.setMinimumWidth(480)
    lay = QVBoxLayout(dlg)

    if mode == "history_trap":
        lead = (
            "이미 저장된 기록에 GitHub가 거절하는 큰 파일이 있습니다.\n"
            "이대로는 같은 오류가 반복됩니다."
        )
    else:
        lead = (
            "GitHub는 파일 하나당 100 MB를 넘는 내용을 "
            "일반 저장소에 받지 않습니다.\n"
            "아래 파일을 어떻게 할지 골라 주세요."
        )
    lab = QLabel(lead)
    lab.setWordWrap(True)
    lay.addWidget(lab)

    body = QTextEdit()
    body.setReadOnly(True)
    body.setPlainText(_format_hits(blocks))
    body.setMaximumHeight(140)
    lay.addWidget(body)

    if offer_hist:
        if ahead_count and ahead_count > 1:
            hist_note = (
                f"아직 GitHub에 안 올린 저장 기록 {ahead_count}개는 "
                "각각 그대로 올라가지 않고, 「큰 파일 제외」기록 하나로 합쳐집니다.\n"
                "이미 GitHub에 있는 기록은 그대로입니다. "
                "폴더 안 파일 내용도 그대로입니다."
            )
        else:
            hist_note = (
                "아직 GitHub에 안 올린 저장 기록은 "
                "각각 그대로 올라가지 않고, 「큰 파일 제외」기록으로 정리됩니다.\n"
                "이미 GitHub에 있는 기록은 그대로입니다. "
                "폴더 안 파일 내용도 그대로입니다."
            )
        note = QLabel(hist_note)
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a7a40;")
        lay.addWidget(note)

    result: dict[str, LargeFileChoice] = {
        "choice": LargeFileChoice.CANCEL
    }

    def _pick(c: LargeFileChoice) -> None:
        result["choice"] = c
        dlg.accept()

    btn_u = QPushButton("이 파일은 저장소에서 빼기")
    if offer_hist:
        btn_u.setText("큰 파일 빼고 다시 정리해 올리기")
        btn_u.clicked.connect(
            lambda: _pick(LargeFileChoice.UNTRACK_HIST)
        )
    else:
        btn_u.clicked.connect(
            lambda: _pick(LargeFileChoice.UNTRACK_WORKTREE)
        )
    lay.addWidget(btn_u)

    if not over_release:
        btn_r = QPushButton(
            "빼고 올린 뒤, 큰 파일은 별도 다운로드로 공유 (권장)"
        )
        btn_r.setToolTip(
            "먼저 큰 파일을 Git 기록에서 뺀 다음, "
            "다운로드용으로 따로 올립니다. 클론에는 들어가지 않습니다."
        )
        btn_r.clicked.connect(lambda: _pick(LargeFileChoice.RELEASES))
        lay.addWidget(btn_r)
    else:
        hint = QLabel(
            "2 GB를 넘는 파일은 GitHub 다운로드 묶음으로도 올릴 수 없습니다. "
            "아래 「밖에 두고 링크만」을 쓰세요."
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)

    btn_e = QPushButton("밖에 두고 링크만 남기기 (안내)")
    btn_e.clicked.connect(lambda: _pick(LargeFileChoice.EXTERNAL))
    lay.addWidget(btn_e)

    if offer_fresh:
        btn_n = QPushButton("처음부터 다시 올리기")
        btn_n.setToolTip(
            "아직 GitHub에 올린 적이 없을 때만 쓸 수 있습니다. "
            "로컬에만 있는 큰 파일 기록을 피하고 새로 올립니다."
        )
        btn_n.clicked.connect(lambda: _pick(LargeFileChoice.FRESH))
        lay.addWidget(btn_n)

    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    box.rejected.connect(lambda: _pick(LargeFileChoice.CANCEL))
    lay.addWidget(box)

    dlg.exec()
    return result["choice"]


def show_external_hosting_guide(parent, hits: list[LargeFileHit]) -> None:
    names = ", ".join(h.rel for h in hits[:5])
    QMessageBox.information(
        parent,
        "밖에 두고 링크만",
        "GitHub 저장소 밖(클라우드 드라이브, 자료 보관소 등)에 파일을 두고,\n"
        "README에 받는 주소만 적어 주세요.\n\n"
        f"대상: {names}\n\n"
        "큰 파일은 저장소에서 뺀 뒤(「빼기」) 다시 올리면 "
        "코드 올리기는 진행됩니다.",
    )


def apply_choice_worktree(
    folder: Path,
    choice: LargeFileChoice,
    blocks: list[LargeFileHit],
    *,
    parent=None,
) -> bool:
    """
    Apply Stage A choices that mutate the repo now.
    Returns True if caller should continue publish/push.
    """
    from app.git.untrack import UntrackError, untrack_worktree

    rels = [h.rel for h in blocks]
    if choice is LargeFileChoice.CANCEL:
        return False
    if choice is LargeFileChoice.EXTERNAL:
        show_external_hosting_guide(parent, blocks)
        # Still need untrack for push to succeed — ask
        reply = QMessageBox.question(
            parent,
            "저장소에서 뺄까요?",
            "링크만 남기려면 큰 파일을 Git 기록에서 빼야 "
            "올리기가 됩니다.\n지금 뺄까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False
        choice = LargeFileChoice.UNTRACK_WORKTREE
    if choice is LargeFileChoice.RELEASES:
        # Pipeline starts with untrack; Releases upload is S4.
        QMessageBox.information(
            parent,
            "별도 다운로드로 공유",
            "먼저 큰 파일을 저장소 기록에서 뺍니다.\n"
            "코드 올리기가 끝난 뒤, 다운로드 묶음으로 올리는 단계는 "
            "다음 버전에서 이어서 안내합니다.\n\n"
            "지금은 파일을 뺀 뒤 올리기를 계속합니다.",
        )
        choice = LargeFileChoice.UNTRACK_WORKTREE
    if choice is LargeFileChoice.UNTRACK_WORKTREE:
        try:
            untrack_worktree(folder, rels, commit=True)
        except UntrackError as e:
            QMessageBox.warning(parent, "빼기 실패", str(e))
            return False
        return True
    if choice is LargeFileChoice.FRESH:
        QMessageBox.information(
            parent,
            "처음부터 다시 올리기",
            "새 폴더로 필요한 파일만 복사한 뒤 "
            "「만들고 올리기」를 다시 진행해 주세요.\n"
            "(이미 GitHub에 올린 기록이 있을 때는 이 방법을 쓰지 않습니다.)",
        )
        return False
    return False
