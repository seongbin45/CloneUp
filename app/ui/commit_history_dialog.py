"""Commit history popup — desin/CloneUp 커밋 내역.dc.html.

Read-only: list commits, show changed files, export a past tree to a temp folder.

Two sources:
- **local** — ``folder`` with .git (동기화 탭 / 로컬 저장소)
- **remote** — GitHub owner/repo via API (받기 탭 URL; 공개는 로그인 불필요)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.auth.session import AuthError, ensure_valid_token
from app.auth.token_store import load_token
from app.git.history import (
    ChangedFile,
    CommitInfo,
    export_commit_snapshot,
    list_changed_files,
    list_commits,
    relative_time_ko,
    repo_display_name,
)
from app.git.publish import PublishError
from app.git.runner import GitError
from app.git.revert import (
    RevertError,
    RevertResult,
    pick_backup_branch_name,
    preview_revert,
    revert_to_commit,
)
from app.git.sync_ops import SyncError
from app.github.api_client import (
    GitHubAPIError,
    export_remote_commit_snapshot,
    list_remote_changed_files,
    list_repo_commits,
)
from app.ui.settings_store import load_hide_real_email, load_history_revert_enabled
from app.ui.theme import Palette, active_palette
from app.util.log_mask import mask_secrets_in_text

_PAGE = 4  # design “더 보기” page size
_REVERT_ERRORS = (RevertError, GitError, PublishError, SyncError, AuthError, OSError)


def _kind_color(kind: str, p: Palette) -> str:
    k = (kind or "?").upper()
    if k == "A":
        return p.primary
    if k == "D":
        return p.danger
    if k in ("M", "R", "C", "T"):
        return p.warn_text
    return p.text_muted


class _LoadWorker(QThread):
    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        *,
        remote: bool,
        folder: str = "",
        owner: str = "",
        repo: str = "",
        access_token: str | None = None,
        skip: int = 0,
        limit: int = _PAGE,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._remote = remote
        self._folder = folder
        self._owner = owner
        self._repo = repo
        self._token = access_token
        self._skip = skip
        self._limit = limit

    def run(self) -> None:  # noqa: N802
        try:
            if self._remote:
                # GitHub is page-based (1-indexed); skip must be page-aligned
                page = (max(0, self._skip) // max(1, self._limit)) + 1
                rows = list_repo_commits(
                    self._owner,
                    self._repo,
                    access_token=self._token,
                    page=page,
                    per_page=self._limit,
                )
            else:
                rows = list_commits(
                    self._folder, limit=self._limit, skip=self._skip
                )
            self.succeeded.emit(rows)
        except (GitError, GitHubAPIError) as e:
            self.failed.emit(str(e))
        except Exception as e:  # pragma: no cover
            self.failed.emit(str(e))


class _DetailWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        remote: bool,
        folder: str = "",
        owner: str = "",
        repo: str = "",
        access_token: str | None = None,
        commit: CommitInfo,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._remote = remote
        self._folder = folder
        self._owner = owner
        self._repo = repo
        self._token = access_token
        self._commit = commit

    def run(self) -> None:  # noqa: N802
        try:
            if self._remote:
                files = list_remote_changed_files(
                    self._owner,
                    self._repo,
                    self._commit.full_hash,
                    access_token=self._token,
                )
            else:
                files = list_changed_files(self._folder, self._commit.full_hash)
            self._commit.changed = files
            self._commit.file_count = len(files)
            self.succeeded.emit(self._commit)
        except (GitError, GitHubAPIError) as e:
            self.failed.emit(str(e))
        except Exception as e:  # pragma: no cover
            self.failed.emit(str(e))


class _ExportWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        *,
        remote: bool,
        folder: str = "",
        owner: str = "",
        repo: str = "",
        access_token: str | None = None,
        rev: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._remote = remote
        self._folder = folder
        self._owner = owner
        self._repo = repo
        self._token = access_token
        self._rev = rev

    def run(self) -> None:  # noqa: N802
        try:
            if self._remote:
                dest = export_remote_commit_snapshot(
                    self._owner,
                    self._repo,
                    self._rev,
                    access_token=self._token,
                )
            else:
                dest = export_commit_snapshot(self._folder, self._rev)
            self.succeeded.emit(str(dest))
        except (GitError, GitHubAPIError) as e:
            self.failed.emit(str(e))
        except Exception as e:  # pragma: no cover
            self.failed.emit(str(e))


class _RevertPreviewWorker(QThread):
    """Local-only: what would change if we reverted *folder* to *rev* now."""

    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(self, *, folder: str, rev: str, parent=None) -> None:
        super().__init__(parent)
        self._folder = folder
        self._rev = rev

    def run(self) -> None:  # noqa: N802
        try:
            files = preview_revert(self._folder, self._rev)
            self.succeeded.emit(files)
        except _REVERT_ERRORS as e:
            self.failed.emit(mask_secrets_in_text(str(e)))
        except Exception as e:  # pragma: no cover
            self.failed.emit(mask_secrets_in_text(f"예상치 못한 오류: {e}"))


class _RevertWorker(QThread):
    """Backup branch → reset to target tree → new commit → push (local only)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, *, folder: str, rev: str, parent=None) -> None:
        super().__init__(parent)
        self._folder = folder
        self._rev = rev

    def run(self) -> None:  # noqa: N802
        try:
            token, user = ensure_valid_token()
            result = revert_to_commit(
                self._folder,
                self._rev,
                token=token,
                user=user,
                hide_real_email=load_hide_real_email(),
            )
            self.succeeded.emit(result)
        except _REVERT_ERRORS as e:
            self.failed.emit(mask_secrets_in_text(str(e)))
        except Exception as e:  # pragma: no cover
            self.failed.emit(mask_secrets_in_text(f"예상치 못한 오류: {e}"))


class _RevertConfirmDialog(QDialog):
    """되돌리기 확인 — files that will change + backup-branch / auto-push notice."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        target_label: str,
        backup_branch: str,
        files: list[ChangedFile],
    ) -> None:
        super().__init__(parent)
        p = active_palette()
        self.setWindowTitle("이 시점으로 되돌립니다")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet(
            f"QDialog {{ background: {p.bg_window}; color: {p.text}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel("이 시점으로 되돌립니다")
        title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {p.text};")
        sub = QLabel(target_label)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size: 12.5px; color: {p.text_secondary};")
        root.addWidget(title)
        root.addWidget(sub)

        files_lbl = QLabel(f"바뀌는 파일 {len(files)}개")
        files_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {p.text_secondary};"
        )
        root.addWidget(files_lbl)

        note = {"A": "되살아납니다", "D": "지워집니다", "M": "예전 내용으로"}
        files_scroll = QScrollArea()
        files_scroll.setWidgetResizable(True)
        files_scroll.setFrameShape(QFrame.Shape.NoFrame)
        files_scroll.setMaximumHeight(180)
        host = QWidget()
        host_l = QVBoxLayout(host)
        host_l.setContentsMargins(0, 0, 0, 0)
        host_l.setSpacing(6)
        for f in files[:200]:
            row = QFrame()
            row.setStyleSheet(
                f"background: {p.bg_input}; border: 1px solid {p.border_divider}; "
                f"border-radius: 5px;"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(9, 6, 9, 6)
            rl.setSpacing(8)
            badge = QLabel((f.kind or "?")[:1].upper())
            badge.setFixedSize(16, 16)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tone = _kind_color(f.kind, p)
            badge.setStyleSheet(
                f"background: {tone}; color: {p.bg_window}; border-radius: 3px; "
                f"font-size: 9.5px; font-weight: 600; font-family: Consolas, monospace;"
            )
            path = QLabel(f.path)
            path.setStyleSheet(
                f"font-size: 11.5px; color: {p.text}; "
                f"font-family: Consolas, 'Cascadia Mono', monospace;"
            )
            path.setToolTip(f.path)
            hint = QLabel(note.get((f.kind or "?").upper(), ""))
            hint.setStyleSheet(f"font-size: 11px; color: {p.text_muted};")
            rl.addWidget(badge)
            rl.addWidget(path, 1)
            rl.addWidget(hint)
            host_l.addWidget(row)
        host_l.addStretch(1)
        files_scroll.setWidget(host)
        root.addWidget(files_scroll)

        info = QFrame()
        info.setStyleSheet(
            f"background: {p.bg_hint}; border-radius: 6px;"
        )
        info_l = QVBoxLayout(info)
        info_l.setContentsMargins(14, 12, 14, 12)
        info_l.setSpacing(6)
        for line in (
            f"백업 브랜치 {backup_branch} 를 먼저 만듭니다.",
            "지금까지의 커밋은 하나도 지워지지 않습니다. "
            "되돌린 내용이 새 커밋으로 쌓입니다.",
            "끝나면 GitHub에도 자동으로 올라갑니다. "
            "공개 저장소라면 이 시점의 내용이 곧바로 공개됩니다.",
        ):
            lab = QLabel(line)
            lab.setWordWrap(True)
            lab.setStyleSheet(f"font-size: 12px; color: {p.text_secondary};")
            info_l.addWidget(lab)
        root.addWidget(info)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        btn_go = QPushButton("되돌리기")
        btn_go.setDefault(True)
        btn_go.setStyleSheet(
            f"QPushButton {{ background: {p.primary}; color: {p.text_on_primary}; "
            f"border: 1px solid {p.primary}; border-radius: 5px; padding: 7px 18px; "
            f"font-size: 12.5px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {p.primary_hover}; }}"
        )
        btn_go.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_go)
        root.addLayout(btn_row)


class CommitHistoryDialog(QDialog):
    """Modal read-only commit browser (시안: CloneUp 커밋 내역)."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        folder: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        access_token: str | None = None,
        display_url: str | None = None,
    ) -> None:
        super().__init__(parent)
        owner_s = (owner or "").strip()
        repo_s = (repo or "").strip()
        folder_s = (folder or "").strip()
        if owner_s and repo_s:
            self._remote = True
            self._folder = ""
            self._owner = owner_s
            self._repo = repo_s
            self._token = (access_token or "").strip() or None
            self._path_text = (
                (display_url or "").strip()
                or f"https://github.com/{owner_s}/{repo_s}"
            )
            self._project_name = f"{owner_s}/{repo_s}"
            path_label = "주소"
        elif folder_s:
            self._remote = False
            self._folder = str(Path(folder_s).expanduser())
            self._owner = ""
            self._repo = ""
            self._token = None
            self._path_text = self._folder
            self._project_name = repo_display_name(self._folder)
            path_label = "폴더"
        else:
            raise ValueError("folder 또는 owner/repo 가 필요합니다.")

        # Settings > 안전 > "커밋 내역에서 되돌리기 허용" (기본 꺼짐 = 읽기 전용).
        # Remote view never gets revert regardless — there's no local .git to write to.
        self._revert_available = (not self._remote) and load_history_revert_enabled()

        self._commits: list[CommitInfo] = []
        self._selected: CommitInfo | None = None
        self._worker: QThread | None = None
        self._exhausted = False
        p = active_palette()

        self.setWindowTitle("커밋 내역")
        self.setModal(True)
        self.setMinimumSize(880, 560)
        self.resize(980, 640)
        self.setStyleSheet(self._dialog_qss(p))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # title bar
        bar = QFrame()
        bar.setObjectName("histTitleBar")
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(16, 12, 16, 12)
        bar_l.setSpacing(12)
        title = QLabel("커밋 내역")
        title.setObjectName("histTitle")
        proj = QLabel(self._project_name)
        proj.setObjectName("histProject")
        proj.setFont(self._mono_font(proj.font()))
        bar_l.addWidget(title)
        bar_l.addWidget(proj)
        bar_l.addStretch(1)
        root.addWidget(bar)

        # banner — read-only for remote, "지워지지 않습니다" once revert exists
        banner = QFrame()
        banner.setObjectName("histBanner")
        ban_l = QHBoxLayout(banner)
        ban_l.setContentsMargins(14, 12, 14, 12)
        ban_l.setSpacing(10)
        if self._revert_available:
            ban_tag = QLabel("지워지지 않습니다")
            ban_body = QLabel(
                "되돌리기는 예전 내용을 되살린 새 커밋을 쌓는 방식입니다. "
                "지금까지의 기록은 그대로 남고, 되돌린 뒤에 다시 되돌릴 수 있습니다."
            )
        elif self._remote:
            ban_tag = QLabel("읽기 전용")
            ban_body = QLabel(
                "GitHub 저장소의 커밋을 읽기만 합니다. "
                "로그인하지 않아도 공개 저장소는 볼 수 있습니다. "
                "비공개는 GitHub 연결이 필요합니다. 로컬 파일은 바뀌지 않습니다."
            )
        else:
            ban_tag = QLabel("읽기 전용")
            ban_body = QLabel(
                "이 창에서는 무엇을 눌러도 작업 중인 파일이 바뀌지 않습니다. "
                "지난 시점의 내용을 확인하는 용도입니다. "
                "되돌리기가 필요하면 설정 > 안전에서 켤 수 있습니다."
            )
        ban_tag.setObjectName("histBannerTag")
        ban_body.setObjectName("histBannerBody")
        ban_body.setWordWrap(True)
        ban_l.addWidget(ban_tag, 0, Qt.AlignmentFlag.AlignTop)
        ban_l.addWidget(ban_body, 1)
        wrap_ban = QVBoxLayout()
        wrap_ban.setContentsMargins(20, 16, 20, 0)
        wrap_ban.addWidget(banner)
        root.addLayout(wrap_ban)

        # path / URL row
        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(20, 16, 20, 14)
        folder_row.setSpacing(10)
        lab = QLabel(path_label)
        lab.setObjectName("histFormLabel")
        lab.setFixedWidth(56)
        self._path_lbl = QLabel(self._path_text)
        self._path_lbl.setObjectName("histPath")
        self._path_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._path_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._path_lbl.setFont(self._mono_font(self._path_lbl.font()))
        self._btn_refresh = QPushButton("목록 새로고침")
        self._btn_refresh.setObjectName("histSecondary")
        self._btn_refresh.clicked.connect(self._reload_from_start)
        folder_row.addWidget(lab)
        folder_row.addWidget(self._path_lbl, 1)
        folder_row.addWidget(self._btn_refresh)
        root.addLayout(folder_row)

        # split
        split = QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(0)

        left = QFrame()
        left.setObjectName("histLeft")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(0)
        left_head = QHBoxLayout()
        left_head.setContentsMargins(20, 11, 20, 9)
        left_head.addWidget(self._section("커밋 목록"))
        self._loaded_lbl = QLabel("불러오는 중…")
        self._loaded_lbl.setObjectName("histMeta")
        left_head.addStretch(1)
        left_head.addWidget(self._loaded_lbl)
        left_l.addLayout(left_head)

        self._list = QListWidget()
        self._list.setObjectName("histList")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.currentRowChanged.connect(self._on_row_changed)
        left_l.addWidget(self._list, 1)

        more_wrap = QHBoxLayout()
        more_wrap.setContentsMargins(20, 13, 20, 13)
        more_wrap.addStretch(1)
        self._btn_more = QPushButton("더 보기")
        self._btn_more.setObjectName("histSecondary")
        self._btn_more.clicked.connect(self._load_more)
        self._all_lbl = QLabel("전체 표시됨")
        self._all_lbl.setObjectName("histMeta")
        self._all_lbl.hide()
        more_wrap.addWidget(self._btn_more)
        more_wrap.addWidget(self._all_lbl)
        more_wrap.addStretch(1)
        left_l.addLayout(more_wrap)

        right = QFrame()
        right.setObjectName("histRight")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(20, 11, 20, 16)
        right_l.setSpacing(14)
        right_l.addWidget(self._section("선택한 시점의 내용"))

        self._sel_card = QFrame()
        self._sel_card.setObjectName("histCard")
        sc_l = QVBoxLayout(self._sel_card)
        sc_l.setContentsMargins(15, 13, 15, 13)
        sc_l.setSpacing(8)
        self._sel_msg = QLabel("목록에서 커밋을 고르세요.")
        self._sel_msg.setObjectName("histSelMsg")
        self._sel_msg.setWordWrap(True)
        self._sel_time = QLabel("")
        self._sel_time.setObjectName("histMeta")
        self._sel_author = QLabel("")
        self._sel_author.setObjectName("histMeta")
        self._sel_hash = QLabel("")
        self._sel_hash.setObjectName("histHash")
        self._sel_hash.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        sc_l.addWidget(self._sel_msg)
        sc_l.addWidget(self._sel_time)
        sc_l.addWidget(self._sel_author)
        sc_l.addWidget(self._sel_hash)
        right_l.addWidget(self._sel_card)

        right_l.addWidget(self._section("이 커밋에서 바뀐 파일"))
        files_scroll = QScrollArea()
        files_scroll.setWidgetResizable(True)
        files_scroll.setObjectName("histFilesScroll")
        files_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._files_host = QWidget()
        self._files_layout = QVBoxLayout(self._files_host)
        self._files_layout.setContentsMargins(0, 0, 0, 0)
        self._files_layout.setSpacing(7)
        self._files_layout.addStretch(1)
        files_scroll.setWidget(self._files_host)
        right_l.addWidget(files_scroll, 1)

        # 시안 순서: 되돌리기(또는 "지금 이 상태입니다") → 파일 보기 → 안내문
        self._btn_revert: QPushButton | None = None
        if self._revert_available:
            self._btn_revert = QPushButton("이 시점으로 되돌리기")
            self._btn_revert.setObjectName("histPrimary")
            self._btn_revert.setEnabled(False)
            self._btn_revert.clicked.connect(self._on_revert_clicked)
            right_l.addWidget(self._btn_revert)

        self._btn_view = QPushButton("이 시점 파일 보기")
        self._btn_view.setObjectName("histClose")
        self._btn_view.setEnabled(False)
        self._btn_view.clicked.connect(self._export_selected)
        right_l.addWidget(self._btn_view)
        view_hint = QLabel(
            "따로 만든 임시 폴더에 그 시점의 파일을 꺼내 보여줍니다. "
            "지금 작업 중인 폴더는 그대로 있습니다."
        )
        view_hint.setObjectName("histMeta")
        view_hint.setWordWrap(True)
        view_hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        right_l.addWidget(view_hint)

        split.addWidget(left, 155)
        split.addWidget(right, 100)
        root.addLayout(split, 1)

        foot = QFrame()
        foot.setObjectName("histFooter")
        foot_l = QHBoxLayout(foot)
        foot_l.setContentsMargins(20, 12, 20, 12)
        if self._revert_available:
            foot_text = (
                "되돌리기 전에 백업 브랜치를 자동으로 만듭니다. "
                "되돌린 결과는 GitHub에도 함께 올라갑니다."
            )
        elif self._remote:
            foot_text = "되돌리기는 로컬 폴더(동기화 탭)에서만 할 수 있습니다."
        else:
            foot_text = (
                "되돌리기가 필요하면 설정 > 안전 > "
                "「커밋 내역에서 되돌리기 허용」을 켜세요."
            )
        foot_note = QLabel(foot_text)
        foot_note.setObjectName("histMeta")
        foot_note.setWordWrap(True)
        btn_close = QPushButton("닫기")
        btn_close.setObjectName("histClose")
        btn_close.clicked.connect(self.accept)
        foot_l.addWidget(foot_note, 1)
        foot_l.addWidget(btn_close)
        root.addWidget(foot)

        self._reload_from_start()

    @staticmethod
    def _mono_font(base: QFont) -> QFont:
        f = QFont(base)
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setFamilies(["Cascadia Mono", "Consolas", "monospace"])
        return f

    @staticmethod
    def _section(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("histSection")
        return lab

    @staticmethod
    def _dialog_qss(p: Palette) -> str:
        return f"""
        QDialog {{
            background: {p.bg_window};
            color: {p.text};
        }}
        QFrame#histTitleBar, QFrame#histFooter {{
            background: {p.bg_bar};
            border: none;
        }}
        QFrame#histTitleBar {{
            border-bottom: 1px solid {p.border_soft};
        }}
        QFrame#histFooter {{
            border-top: 1px solid {p.border_divider};
        }}
        QLabel#histTitle {{
            font-size: 13px;
            font-weight: 600;
            color: {p.text};
        }}
        QLabel#histProject {{
            font-size: 12.5px;
            color: {p.text_faint};
        }}
        QFrame#histBanner {{
            background: {p.bg_hint};
            border-left: 3px solid {p.primary};
            border-radius: 0 6px 6px 0;
        }}
        QLabel#histBannerTag {{
            font-size: 13px;
            font-weight: 600;
            color: {p.primary};
        }}
        QLabel#histBannerBody {{
            font-size: 12.5px;
            color: {p.text_secondary};
        }}
        QLabel#histFormLabel {{
            font-size: 13px;
            color: {p.text_secondary};
        }}
        QLabel#histPath {{
            background: {p.bg_input};
            border: 1px solid {p.border_input};
            border-radius: 5px;
            padding: 6px 11px;
            font-size: 13px;
            color: {p.text};
            min-height: 20px;
        }}
        QLabel#histSection {{
            font-size: 12px;
            font-weight: 600;
            color: {p.text_secondary};
        }}
        QLabel#histMeta {{
            font-size: 11.5px;
            color: {p.text_muted};
        }}
        QLabel#histSelMsg {{
            font-size: 13.5px;
            font-weight: 600;
            color: {p.text};
        }}
        QLabel#histHash {{
            font-size: 11.5px;
            color: {p.text_muted};
            font-family: Consolas, "Cascadia Mono", monospace;
        }}
        QFrame#histLeft {{
            background: {p.bg_window};
            border-top: 1px solid {p.border_divider};
            border-right: 1px solid {p.border_divider};
        }}
        QFrame#histRight {{
            background: {p.bg_hint};
            border-top: 1px solid {p.border_divider};
        }}
        QFrame#histCard {{
            background: {p.bg_input};
            border: 1px solid {p.border_divider};
            border-radius: 6px;
        }}
        QListWidget#histList {{
            background: {p.bg_window};
            border: none;
            outline: 0;
        }}
        QListWidget#histList::item {{
            border-top: 1px solid {p.border_soft};
            padding: 0;
        }}
        QListWidget#histList::item:selected {{
            background: {p.bg_bar};
        }}
        QScrollArea#histFilesScroll {{
            background: transparent;
            border: none;
        }}
        QPushButton#histSecondary {{
            background: {p.bg_muted};
            color: {p.text_secondary};
            border: 1px solid {p.border_input};
            border-radius: 5px;
            padding: 6px 14px;
            font-size: 12.5px;
            min-height: 20px;
        }}
        QPushButton#histSecondary:hover {{
            background: {p.hover_muted};
        }}
        QPushButton#histSecondary:disabled {{
            color: {p.text_disabled};
        }}
        QPushButton#histPrimary {{
            background: {p.primary};
            color: {p.text_on_primary};
            border: 1px solid {p.primary};
            border-radius: 6px;
            padding: 10px 16px;
            font-size: 13px;
            font-weight: 600;
            min-height: 22px;
        }}
        QPushButton#histPrimary:hover {{
            background: {p.primary_hover};
            border-color: {p.primary_hover};
        }}
        QPushButton#histPrimary:disabled {{
            background: {p.bg_muted};
            color: {p.text_disabled};
            border-color: {p.border_soft};
        }}
        QPushButton#histClose {{
            background: {p.bg_window};
            color: {p.text};
            border: 1px solid {p.border_outline};
            border-radius: 5px;
            padding: 6px 18px;
            font-size: 12.5px;
            min-height: 20px;
        }}
        QPushButton#histClose:hover {{
            background: {p.bg_hint};
        }}
        QPushButton#histClose:disabled {{
            color: {p.text_disabled};
            border-color: {p.border_soft};
        }}
        """

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_worker()
        super().closeEvent(event)

    def _set_busy(self, busy: bool) -> None:
        self._btn_refresh.setEnabled(not busy)
        self._btn_more.setEnabled(not busy and not self._exhausted)
        self._btn_view.setEnabled(not busy and self._selected is not None)
        self._update_revert_button(enabled=not busy and self._can_revert_selected())

    def _stop_worker(self) -> None:
        w = self._worker
        self._worker = None
        if w is not None and w.isRunning():
            w.wait(4000)

    @Slot()
    def _reload_from_start(self) -> None:
        self._commits.clear()
        self._list.clear()
        self._exhausted = False
        self._selected = None
        self._clear_detail()
        self._btn_more.show()
        self._all_lbl.hide()
        self._fetch_page(skip=0)

    @Slot()
    def _load_more(self) -> None:
        if self._exhausted:
            return
        self._fetch_page(skip=len(self._commits))

    def _fetch_page(self, *, skip: int) -> None:
        self._stop_worker()
        self._set_busy(True)
        self._loaded_lbl.setText("불러오는 중…")
        w = _LoadWorker(
            remote=self._remote,
            folder=self._folder,
            owner=self._owner,
            repo=self._repo,
            access_token=self._token,
            skip=skip,
            limit=_PAGE,
            parent=self,
        )
        self._worker = w
        w.succeeded.connect(self._on_page_ok)
        w.failed.connect(self._on_page_fail)
        w.finished.connect(lambda: self._set_busy(False))
        w.start()

    @Slot(list)
    def _on_page_ok(self, rows: list) -> None:
        rows = list(rows or [])
        if len(rows) < _PAGE:
            self._exhausted = True
            self._btn_more.hide()
            self._all_lbl.show()
        if not rows and not self._commits:
            self._loaded_lbl.setText("커밋 없음")
            self._all_lbl.hide()
            self._btn_more.hide()
            return
        start = len(self._commits)
        for c in rows:
            if not isinstance(c, CommitInfo):
                continue
            self._commits.append(c)
            self._append_row(c)
        self._loaded_lbl.setText(f"최신순 · {len(self._commits)}개 표시 중")
        if start == 0 and self._commits:
            self._list.setCurrentRow(0)

    @Slot(str)
    def _on_page_fail(self, msg: str) -> None:
        self._loaded_lbl.setText("불러오기 실패")
        QMessageBox.warning(self, "커밋 내역", msg)

    def _append_row(self, c: CommitInfo) -> None:
        p = active_palette()
        item = QListWidgetItem(self._list)
        item.setData(Qt.ItemDataRole.UserRole, c.full_hash)

        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QFrame()
        bar.setFixedWidth(3)
        bar.setStyleSheet("background: transparent;")
        body = QVBoxLayout()
        body.setContentsMargins(17, 11, 20, 12)
        body.setSpacing(5)
        msg = QLabel(c.message)
        msg.setStyleSheet(
            f"font-size: 13.5px; font-weight: 500; color: {p.text}; background: transparent;"
        )
        msg.setWordWrap(False)
        # Remote list omits per-commit file counts (extra API call); show after detail
        if self._remote and c.file_count <= 0:
            files_bit = "파일 목록은 선택 시"
        else:
            files_bit = f"파일 {c.file_count}개"
        meta = QLabel(
            f"{relative_time_ko(c.unix_time)}  ·  {c.abs_time}  ·  "
            f"{c.author}  ·  {files_bit}"
        )
        meta.setStyleSheet(
            f"font-size: 11.5px; color: {p.text_muted}; background: transparent;"
        )
        body.addWidget(msg)
        body.addWidget(meta)
        lay.addWidget(bar)
        lay.addLayout(body, 1)
        item.setSizeHint(w.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole + 1, bar)
        self._list.setItemWidget(item, w)

    def _clear_detail(self) -> None:
        self._sel_msg.setText("목록에서 커밋을 고르세요.")
        self._sel_time.setText("")
        self._sel_author.setText("")
        self._sel_hash.setText("")
        self._clear_files()
        self._btn_view.setEnabled(False)
        self._update_revert_button(enabled=False)

    def _can_revert_selected(self) -> bool:
        if not self._revert_available or self._selected is None or not self._commits:
            return False
        return self._selected.full_hash != self._commits[0].full_hash

    def _update_revert_button(self, *, enabled: bool) -> None:
        """
        시안: canRevert → green button / isCurrent → "지금 이 상태입니다" (disabled).

        ``enabled`` also folds in "busy" (a worker is running) — that must
        not flip the label to "지금 이 상태입니다", so the label is decided
        from the selection alone, independent of ``enabled``.
        """
        if self._btn_revert is None:
            return
        self._btn_revert.setEnabled(enabled)
        is_current = (
            not self._remote
            and self._selected is not None
            and not self._can_revert_selected()
        )
        self._btn_revert.setText(
            "지금 이 상태입니다" if is_current else "이 시점으로 되돌리기"
        )

    def _clear_files(self) -> None:
        while self._files_layout.count():
            item = self._files_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._files_layout.addStretch(1)

    @Slot(int)
    def _on_row_changed(self, row: int) -> None:
        p = active_palette()
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is None:
                continue
            bar = it.data(Qt.ItemDataRole.UserRole + 1)
            if isinstance(bar, QFrame):
                if i == row:
                    bar.setStyleSheet(f"background: {p.primary};")
                else:
                    bar.setStyleSheet("background: transparent;")

        if row < 0 or row >= len(self._commits):
            self._selected = None
            self._clear_detail()
            return
        c = self._commits[row]
        self._selected = c
        self._sel_msg.setText(c.message)
        self._sel_time.setText(f"{c.abs_time} · {relative_time_ko(c.unix_time)}")
        self._sel_author.setText(c.author)
        self._sel_hash.setText(c.short_hash)
        self._btn_view.setEnabled(True)
        self._update_revert_button(enabled=self._can_revert_selected())
        self._load_detail(c)

    def _load_detail(self, c: CommitInfo) -> None:
        self._stop_worker()
        self._set_busy(True)
        self._clear_files()
        placeholder = QLabel("파일 목록 불러오는 중…")
        placeholder.setObjectName("histMeta")
        # remove stretch then add
        while self._files_layout.count():
            item = self._files_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._files_layout.addWidget(placeholder)
        self._files_layout.addStretch(1)
        w = _DetailWorker(
            remote=self._remote,
            folder=self._folder,
            owner=self._owner,
            repo=self._repo,
            access_token=self._token,
            commit=c,
            parent=self,
        )
        self._worker = w
        w.succeeded.connect(self._on_detail_ok)
        w.failed.connect(self._on_detail_fail)
        w.finished.connect(lambda: self._set_busy(False))
        w.start()

    @Slot(object)
    def _on_detail_ok(self, commit: object) -> None:
        if not isinstance(commit, CommitInfo):
            return
        if self._selected is None or commit.full_hash != self._selected.full_hash:
            return
        self._selected = commit
        self._render_files(commit)

    @Slot(str)
    def _on_detail_fail(self, msg: str) -> None:
        self._clear_files()
        err = QLabel(msg)
        err.setObjectName("histMeta")
        err.setWordWrap(True)
        while self._files_layout.count():
            item = self._files_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._files_layout.addWidget(err)
        self._files_layout.addStretch(1)

    def _render_files(self, c: CommitInfo) -> None:
        p = active_palette()
        while self._files_layout.count():
            item = self._files_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not c.changed:
            empty = QLabel("바뀐 파일이 없거나 목록을 읽을 수 없습니다.")
            empty.setObjectName("histMeta")
            self._files_layout.addWidget(empty)
            self._files_layout.addStretch(1)
            return
        for f in c.changed:
            row = QFrame()
            row.setStyleSheet(
                f"background: {p.bg_input}; border: 1px solid {p.border_divider}; "
                f"border-radius: 5px;"
            )
            hl = QHBoxLayout(row)
            hl.setContentsMargins(10, 7, 10, 7)
            hl.setSpacing(9)
            badge = QLabel((f.kind or "?")[:1].upper())
            badge.setFixedSize(17, 17)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tone = _kind_color(f.kind, p)
            badge.setStyleSheet(
                f"background: {tone}; color: {p.bg_window}; border-radius: 3px; "
                f"font-size: 10px; font-weight: 600; font-family: Consolas, monospace;"
            )
            path = QLabel(f.path)
            path.setStyleSheet(
                f"font-size: 12px; color: {p.text}; "
                f"font-family: Consolas, 'Cascadia Mono', monospace; background: transparent;"
            )
            path.setToolTip(f.path)
            hl.addWidget(badge)
            hl.addWidget(path, 1)
            self._files_layout.addWidget(row)
        self._files_layout.addStretch(1)

    @Slot()
    def _export_selected(self) -> None:
        if self._selected is None:
            return
        self._stop_worker()
        self._set_busy(True)
        w = _ExportWorker(
            remote=self._remote,
            folder=self._folder,
            owner=self._owner,
            repo=self._repo,
            access_token=self._token,
            rev=self._selected.full_hash,
            parent=self,
        )
        self._worker = w
        w.succeeded.connect(self._on_export_ok)
        w.failed.connect(self._on_export_fail)
        w.finished.connect(lambda: self._set_busy(False))
        w.start()

    @Slot(str)
    def _on_export_ok(self, path: str) -> None:
        self._log_open_folder(path)
        QMessageBox.information(
            self,
            "이 시점 파일 보기",
            "임시 폴더에 그 시점의 파일을 꺼내 두었습니다.\n"
            "탐색기에서 열었습니다. 작업 중인 폴더는 그대로입니다.\n\n"
            f"{path}",
        )

    @Slot(str)
    def _on_export_fail(self, msg: str) -> None:
        QMessageBox.warning(self, "이 시점 파일 보기", msg)

    @Slot()
    def _on_revert_clicked(self) -> None:
        if self._selected is None or not self._can_revert_selected():
            return
        if not load_token():
            QMessageBox.information(
                self,
                "이 시점으로 되돌리기",
                "먼저 GitHub에 연결해야 되돌리고 다시 올릴 수 있습니다.\n"
                "메인 창 위쪽의 「GitHub: 연결」에서 로그인한 뒤 다시 시도하세요.",
            )
            return
        self._stop_worker()
        self._set_busy(True)
        w = _RevertPreviewWorker(
            folder=self._folder, rev=self._selected.full_hash, parent=self
        )
        self._worker = w
        w.succeeded.connect(self._on_revert_preview_ok)
        w.failed.connect(self._on_revert_preview_fail)
        w.finished.connect(lambda: self._set_busy(False))
        w.start()

    @Slot(list)
    def _on_revert_preview_ok(self, files: list) -> None:
        if self._selected is None:
            return
        files = [f for f in files if isinstance(f, ChangedFile)]
        if not files:
            QMessageBox.information(
                self, "이 시점으로 되돌리기", "바뀌는 파일이 없습니다."
            )
            return
        try:
            backup_branch = pick_backup_branch_name(Path(self._folder))
        except _REVERT_ERRORS:
            backup_branch = "cloneup-backup-…"  # actual name is chosen at commit time
        dlg = _RevertConfirmDialog(
            self,
            target_label=f"{self._selected.abs_time} · {self._selected.message}",
            backup_branch=backup_branch,
            files=files,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._execute_revert(self._selected.full_hash)

    @Slot(str)
    def _on_revert_preview_fail(self, msg: str) -> None:
        QMessageBox.warning(self, "이 시점으로 되돌리기", msg)

    def _execute_revert(self, rev: str) -> None:
        self._stop_worker()
        self._set_busy(True)
        w = _RevertWorker(folder=self._folder, rev=rev, parent=self)
        self._worker = w
        w.succeeded.connect(self._on_revert_ok)
        w.failed.connect(self._on_revert_fail)
        w.finished.connect(lambda: self._set_busy(False))
        w.start()

    @Slot(object)
    def _on_revert_ok(self, result: object) -> None:
        if not isinstance(result, RevertResult):
            return
        QMessageBox.information(
            self,
            "되돌렸습니다",
            f"{result.target_message!r} 시점의 내용으로 되돌렸고, GitHub에도 올렸습니다.\n\n"
            f"새로 만든 커밋: {result.new_commit[:7]}\n"
            f"백업 브랜치: {result.backup_branch}\n\n"
            "이 되돌리기가 마음에 들지 않으면 목록 맨 위 커밋을 골라 다시 되돌리면 됩니다.",
        )
        self._reload_from_start()

    @Slot(str)
    def _on_revert_fail(self, msg: str) -> None:
        QMessageBox.warning(self, "이 시점으로 되돌리기", msg)

    @staticmethod
    def _log_open_folder(path: str) -> None:
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])  # noqa: S603
        except OSError:
            pass


def show_commit_history(parent: QWidget | None, folder: str) -> None:
    """Open the read-only commit history dialog for a local *folder*."""
    dlg = CommitHistoryDialog(parent, folder=folder)
    dlg.exec()


def show_remote_commit_history(
    parent: QWidget | None,
    owner: str,
    repo: str,
    *,
    access_token: str | None = None,
    display_url: str | None = None,
) -> None:
    """Open commit history for a GitHub repo (public OK without token)."""
    dlg = CommitHistoryDialog(
        parent,
        owner=owner,
        repo=repo,
        access_token=access_token,
        display_url=display_url,
    )
    dlg.exec()
