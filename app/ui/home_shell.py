"""Finder-style home shell (Phase B) — folder first, actions second.

Replaces the tab-first main chrome when ``CLONEUP_LEGACY_TABS`` is unset.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.auth.token_store import is_logged_in
from app.git.project_scan import (
    ProjectEntry,
    SubPathHit,
    format_clock,
    format_relative_mtime,
    group_by_time_bucket,
    list_recent_child_paths,
    scan_projects,
)
from app.ui.home_chrome import (
    GitMissingBanner,
    make_overflow_button,
    populate_overflow_menu,
)
from app.ui.settings_store import add_scan_root, load_last_github_login
from app.ui.theme import active_palette

if TYPE_CHECKING:
    from app.ui.main_window import MainController

# Sidebar filter keys
FILTER_ALL = "all"
FILTER_GIT = "git"
FILTER_NO_GIT = "no_git"
FILTER_RECENT = "recent"
FILTER_DIRTY = "dirty"


class _ScanWorker(QThread):
    finished_ok = Signal(object)  # list[ProjectEntry]
    failed = Signal(str)

    def __init__(self, *, probe_dirty: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._probe_dirty = probe_dirty

    def run(self) -> None:  # noqa: N802
        try:
            entries = scan_projects(probe_dirty=self._probe_dirty)
            self.finished_ok.emit(entries)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class HomeShellWidget(QWidget):
    """Three-pane home: sidebar filters · project list · detail/CTA."""

    open_workspace = Signal(str)  # folder path → show legacy tabs with prefills
    request_back = Signal()

    def __init__(self, controller: MainController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctrl = controller
        self._entries: list[ProjectEntry] = []
        self._filter = FILTER_ALL
        self._query = ""
        self._view_timeline = False  # False = list grid; True = time buckets
        self._sort_time = True  # list mode: sort by mtime vs name
        self._selected: ProjectEntry | None = None
        self._expanded: set[str] = set()
        self._subs_cache: dict[str, list[SubPathHit]] = {}
        self._worker: _ScanWorker | None = None
        self.setObjectName("homeShell")

        p = active_palette()
        self.setStyleSheet(
            f"QWidget#homeShell {{ background: {p.bg_window}; }}"
            f"QLabel {{ color: {p.text}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- top bar ---
        top = QFrame()
        top.setObjectName("homeTopBar")
        top.setStyleSheet(
            f"QFrame#homeTopBar {{ background: {p.bg_bar}; "
            f"border-bottom: 1px solid {p.border_soft}; }}"
        )
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(14, 10, 14, 10)
        top_l.setSpacing(10)
        self._heading = QLabel("모든 프로젝트")
        self._heading.setStyleSheet(
            f"font-size: 13.5px; font-weight: 600; color: {p.text};"
        )
        top_l.addWidget(self._heading)
        top_l.addStretch(1)

        self._btn_list_mode = QPushButton("목록")
        self._btn_time_mode = QPushButton("시간순")
        for b, active in ((self._btn_list_mode, True), (self._btn_time_mode, False)):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFlat(True)
            b.setCheckable(True)
            b.setChecked(active)
        self._btn_list_mode.clicked.connect(lambda: self._set_view_mode(timeline=False))
        self._btn_time_mode.clicked.connect(lambda: self._set_view_mode(timeline=True))
        mode_wrap = QFrame()
        mode_l = QHBoxLayout(mode_wrap)
        mode_l.setContentsMargins(2, 2, 2, 2)
        mode_l.setSpacing(2)
        mode_wrap.setStyleSheet(
            f"background: {p.hover_muted}; border-radius: 7px;"
        )
        mode_l.addWidget(self._btn_list_mode)
        mode_l.addWidget(self._btn_time_mode)
        top_l.addWidget(mode_wrap)

        self._search = QLineEdit()
        self._search.setPlaceholderText("폴더 이름으로 찾기")
        self._search.setFixedWidth(216)
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_query)
        top_l.addWidget(self._search)
        root.addWidget(top)

        # Git banner
        self._git_banner = GitMissingBanner(self)
        self._git_banner.install_clicked.connect(self._ctrl._on_git_banner_install)
        root.addWidget(self._git_banner)

        # --- body ---
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Sidebar
        side = QFrame()
        side.setObjectName("homeSidebar")
        side.setFixedWidth(206)
        side.setStyleSheet(
            f"QFrame#homeSidebar {{ background: {p.bg_bar}; "
            f"border-right: 1px solid {p.border_soft}; }}"
        )
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.setSpacing(0)

        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_host = QWidget()
        self._nav_layout = QVBoxLayout(nav_host)
        self._nav_layout.setContentsMargins(0, 14, 0, 8)
        self._nav_layout.setSpacing(16)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._build_nav(p)
        self._nav_layout.addStretch(1)
        nav_scroll.setWidget(nav_host)
        side_l.addWidget(nav_scroll, 1)

        # Footer: account + ⋯
        foot = QFrame()
        foot.setStyleSheet(f"border-top: 1px solid {p.border_soft};")
        foot_l = QHBoxLayout(foot)
        foot_l.setContentsMargins(8, 8, 8, 8)
        foot_l.setSpacing(6)
        self._account_btn = QPushButton()
        self._account_btn.setObjectName("homeAccountBtn")
        self._account_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._account_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._account_btn.setMinimumHeight(35)
        self._account_btn.clicked.connect(self._on_account_clicked)
        foot_l.addWidget(self._account_btn, 1)
        self._overflow = make_overflow_button(foot)
        self._overflow.clicked.connect(self._show_overflow)
        foot_l.addWidget(self._overflow, 0)
        side_l.addWidget(foot, 0)
        body.addWidget(side)

        # Center list
        center = QFrame()
        center.setObjectName("homeCenter")
        center_l = QVBoxLayout(center)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(
            f"background: {p.bg_muted}; border-bottom: 1px solid {p.border_soft};"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(12)
        # Approximate 1fr 118 108 92 with stretches
        self._h_name = QLabel("이름")
        self._h_time = QLabel("마지막 작업")
        self._h_dirty = QLabel("안 올린 변경")
        self._h_branch = QLabel("브랜치")
        for lab in (self._h_name, self._h_time, self._h_dirty, self._h_branch):
            lab.setStyleSheet(
                f"font-size: 11.5px; font-weight: 600; color: {p.text_muted};"
            )
        self._h_name.setCursor(Qt.CursorShape.PointingHandCursor)
        self._h_time.setCursor(Qt.CursorShape.PointingHandCursor)
        self._h_name.mousePressEvent = (  # type: ignore[method-assign]
            lambda _e: self._set_list_sort(time_sort=False)
        )
        self._h_time.mousePressEvent = (  # type: ignore[method-assign]
            lambda _e: self._set_list_sort(time_sort=True)
        )
        h.addWidget(self._h_name, 1)
        self._h_time.setFixedWidth(118)
        self._h_dirty.setFixedWidth(108)
        self._h_branch.setFixedWidth(92)
        h.addWidget(self._h_time, 0)
        h.addWidget(self._h_dirty, 0)
        h.addWidget(self._h_branch, 0)
        self._list_header = header
        center_l.addWidget(header)

        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch(1)
        self._list_scroll.setWidget(self._list_host)
        center_l.addWidget(self._list_scroll, 1)

        self._status = QLabel("폴더를 찾는 중…")
        self._status.setStyleSheet(
            f"padding: 8px 16px; font-size: 11.5px; color: {p.text_muted};"
        )
        center_l.addWidget(self._status)
        body.addWidget(center, 1)

        # Right detail
        right = QFrame()
        right.setObjectName("homeDetail")
        right.setFixedWidth(286)
        right.setStyleSheet(
            f"QFrame#homeDetail {{ background: {p.bg_muted}; "
            f"border-left: 1px solid {p.border_soft}; }}"
        )
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 16, 16, 16)
        rl.setSpacing(10)
        self._detail_title = QLabel("폴더를 선택하세요")
        self._detail_title.setWordWrap(True)
        self._detail_title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {p.text};"
        )
        self._detail_path = QLabel("")
        self._detail_path.setWordWrap(True)
        self._detail_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._detail_path.setStyleSheet(
            f"font-size: 11.5px; color: {p.text_muted};"
        )
        self._detail_meta = QLabel("")
        self._detail_meta.setWordWrap(True)
        self._detail_meta.setStyleSheet(
            f"font-size: 12.5px; color: {p.text_secondary};"
        )
        rl.addWidget(self._detail_title)
        rl.addWidget(self._detail_path)
        rl.addWidget(self._detail_meta)
        rl.addSpacing(8)
        self._btn_primary = QPushButton("작업 열기")
        self._btn_primary.setObjectName("homePrimaryCta")
        self._btn_primary.setMinimumHeight(40)
        self._btn_primary.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_primary.clicked.connect(self._on_primary)
        self._btn_history = QPushButton("작업 내역 보기")
        self._btn_history.setMinimumHeight(36)
        self._btn_history.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_history.clicked.connect(self._on_history)
        self._style_cta(self._btn_primary, primary=True)
        self._style_cta(self._btn_history, primary=False)
        rl.addWidget(self._btn_primary)
        rl.addWidget(self._btn_history)
        rl.addStretch(1)
        self._btn_primary.setEnabled(False)
        self._btn_history.setEnabled(False)
        body.addWidget(right)

        root.addLayout(body, 1)

        self._overflow_menu = QMenu(self)
        self._refresh_account()
        self._sync_git_banner()
        self._update_header_emphasis()
        self._select_filter(FILTER_ALL, refresh=False)
        self.refresh_projects()

    def _style_cta(self, btn: QPushButton, *, primary: bool) -> None:
        p = active_palette()
        if primary:
            btn.setStyleSheet(
                f"QPushButton {{ background: {p.primary}; color: {p.text_on_primary};"
                f" border: none; border-radius: 6px; font-weight: 600; font-size: 13.5px; }}"
                f"QPushButton:hover {{ background: {p.primary_hover}; }}"
                f"QPushButton:disabled {{ background: {p.bg_hint}; color: {p.text_disabled}; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background: {p.bg_window}; color: {p.text_secondary};"
                f" border: 1px solid {p.border}; border-radius: 6px; font-size: 13px; }}"
                f"QPushButton:hover {{ background: {p.hover_muted}; }}"
                f"QPushButton:disabled {{ color: {p.text_disabled}; }}"
            )

    def _build_nav(self, p) -> None:  # noqa: ANN001
        groups = [
            (
                "내 작업",
                [
                    (FILTER_ALL, "모든 프로젝트", "▣"),
                    (FILTER_DIRTY, "안 올린 변경", "△"),
                    (FILTER_RECENT, "최근", "◷"),
                ],
            ),
            (
                "아직 연결 안 됨",
                [
                    (FILTER_NO_GIT, "Git 없는 폴더", "□"),
                    (FILTER_GIT, "Git 있는 폴더", "●"),
                ],
            ),
        ]
        for title, items in groups:
            box = QVBoxLayout()
            box.setSpacing(2)
            lab = QLabel(title)
            lab.setStyleSheet(
                f"padding: 0 16px 6px; font-size: 11px; font-weight: 600; "
                f"color: {p.text_muted};"
            )
            box.addWidget(lab)
            for key, label, icon in items:
                btn = QPushButton(f"  {icon}  {label}")
                btn.setObjectName(f"homeNav_{key}")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFlat(True)
                btn.setStyleSheet(self._nav_style(False))
                btn.clicked.connect(
                    lambda _=False, k=key: self._select_filter(k, refresh=True)
                )
                self._nav_buttons[key] = btn
                box.addWidget(btn)
            self._nav_layout.addLayout(box)

        add = QPushButton("+  찾을 위치 추가")
        add.setObjectName("homeAddScanRoot")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.setFlat(True)
        add.setStyleSheet(
            f"QPushButton {{ text-align: left; padding: 7px 18px; border: none;"
            f" color: {p.text_muted}; font-size: 12.5px; }}"
            f"QPushButton:hover {{ background: {p.hover_muted}; border-radius: 6px; }}"
        )
        add.clicked.connect(self._add_scan_root)
        self._nav_layout.addWidget(add)

    def _nav_style(self, active: bool) -> str:
        p = active_palette()
        if active:
            return (
                f"QPushButton {{ text-align: left; padding: 7px 10px; margin: 0 8px;"
                f" border: none; border-radius: 6px; background: {p.hover_muted};"
                f" color: {p.text}; font-weight: 600; font-size: 12.5px; }}"
            )
        return (
            f"QPushButton {{ text-align: left; padding: 7px 10px; margin: 0 8px;"
            f" border: none; border-radius: 6px; background: transparent;"
            f" color: {p.text_secondary}; font-size: 12.5px; }}"
            f"QPushButton:hover {{ background: {p.hover_muted}; }}"
        )

    def _select_filter(self, key: str, *, refresh: bool) -> None:
        self._filter = key
        titles = {
            FILTER_ALL: "모든 프로젝트",
            FILTER_GIT: "Git 있는 폴더",
            FILTER_NO_GIT: "Git 없는 폴더",
            FILTER_RECENT: "최근",
            FILTER_DIRTY: "안 올린 변경",
        }
        self._heading.setText(titles.get(key, "모든 프로젝트"))
        for k, btn in self._nav_buttons.items():
            btn.setStyleSheet(self._nav_style(k == key))
        if refresh:
            self._rebuild_list()

    def _set_view_mode(self, *, timeline: bool) -> None:
        self._view_timeline = timeline
        self._btn_list_mode.setChecked(not timeline)
        self._btn_time_mode.setChecked(timeline)
        # Column header only applies to list grid
        if hasattr(self, "_list_header") and self._list_header is not None:
            self._list_header.setVisible(not timeline)
        self._rebuild_list()

    def _set_list_sort(self, *, time_sort: bool) -> None:
        """Clicking column headers sorts the list view (does not switch to timeline)."""
        self._view_timeline = False
        self._sort_time = time_sort
        self._btn_list_mode.setChecked(True)
        self._btn_time_mode.setChecked(False)
        if hasattr(self, "_list_header") and self._list_header is not None:
            self._list_header.setVisible(True)
        self._update_header_emphasis()
        self._rebuild_list()

    def _update_header_emphasis(self) -> None:
        p = active_palette()
        active = f"font-size: 11.5px; font-weight: 600; color: {p.text};"
        idle = f"font-size: 11.5px; font-weight: 600; color: {p.text_muted};"
        self._h_name.setStyleSheet(active if not self._sort_time else idle)
        self._h_time.setStyleSheet(active if self._sort_time else idle)

    def _on_query(self, text: str) -> None:
        self._query = (text or "").strip().lower()
        self._rebuild_list()

    def refresh_projects(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._subs_cache.clear()
        self._status.setText("폴더를 찾는 중…")
        w = _ScanWorker(probe_dirty=True, parent=self)
        w.finished_ok.connect(self._on_scan_done)
        w.failed.connect(self._on_scan_fail)
        self._worker = w
        w.start()

    def _on_scan_done(self, entries: object) -> None:
        self._worker = None
        if isinstance(entries, list):
            self._entries = [e for e in entries if isinstance(e, ProjectEntry)]
        else:
            self._entries = []
        self._status.setText(f"{len(self._entries)}개 폴더")
        self._rebuild_list()

    def _on_scan_fail(self, msg: str) -> None:
        self._worker = None
        self._status.setText(f"목록을 읽지 못했습니다: {msg[:80]}")

    def _filtered(self) -> list[ProjectEntry]:
        from app.ui.settings_store import load_recent_folders

        items = list(self._entries)
        q = self._query
        if q:
            items = [e for e in items if q in e.name.lower()]
        if self._filter == FILTER_GIT:
            items = [e for e in items if e.has_git]
        elif self._filter == FILTER_NO_GIT:
            items = [e for e in items if not e.has_git]
        elif self._filter == FILTER_DIRTY:
            items = [e for e in items if e.dirty]
        elif self._filter == FILTER_RECENT:
            recent = {str(Path(x).resolve()).lower() for x in load_recent_folders()}
            items = [
                e
                for e in items
                if str(Path(e.path).resolve()).lower() in recent
            ]
        if self._view_timeline or self._sort_time:
            items.sort(key=lambda e: e.last_mtime, reverse=True)
        else:
            items.sort(key=lambda e: e.name.lower())
        return items

    def _rebuild_list(self) -> None:
        # Clear rows (keep trailing stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        rows = self._filtered()
        p = active_palette()
        if not rows:
            empty = QLabel(
                "찾는 폴더가 없어요\n\n"
                "이름을 다르게 적어 보시거나,\n왼쪽 아래 찾을 위치로 폴더를 알려 주세요."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"padding: 40px 24px; font-size: 12.5px; color: {p.text_muted};"
            )
            self._list_layout.insertWidget(0, empty)
            return
        if self._view_timeline:
            self._rebuild_timeline(rows)
        else:
            for entry in rows:
                self._list_layout.insertWidget(
                    self._list_layout.count() - 1, self._make_project_block(entry)
                )

    def _rebuild_timeline(self, rows: list[ProjectEntry]) -> None:
        p = active_palette()
        for label, items in group_by_time_bucket(rows):
            title = QLabel(label)
            title.setStyleSheet(
                f"padding: 13px 16px 7px; font-size: 11.5px; font-weight: 600; "
                f"color: {p.text_muted};"
            )
            self._list_layout.insertWidget(self._list_layout.count() - 1, title)
            for entry in items:
                self._list_layout.insertWidget(
                    self._list_layout.count() - 1, self._make_timeline_row(entry)
                )

    def _make_timeline_row(self, entry: ProjectEntry) -> QWidget:
        p = active_palette()
        row = QFrame()
        row.setObjectName("homeTimelineRow")
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        selected = (
            self._selected is not None and self._selected.path == entry.path
        )
        bg = p.hover_muted if selected else "transparent"
        row.setStyleSheet(
            f"QFrame#homeTimelineRow {{ background: {bg}; "
            f"border-bottom: 1px solid {p.border_soft}; }}"
            f"QFrame#homeTimelineRow:hover {{ background: {p.bg_hint}; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)
        clock = QLabel(format_clock(entry.last_mtime))
        clock.setFixedWidth(52)
        clock.setStyleSheet(
            f"font-size: 11.5px; color: {p.text_muted}; font-family: Consolas, monospace;"
        )
        lay.addWidget(clock, 0)
        name = QLabel(entry.name)
        name.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {p.text};"
        )
        lay.addWidget(name, 0)
        what = QLabel(
            "변경 있음"
            if entry.dirty
            else ("Git 없음" if not entry.has_git else format_relative_mtime(entry.last_mtime))
        )
        what.setStyleSheet(f"font-size: 12px; color: {p.text_muted};")
        lay.addWidget(what, 1)
        if entry.dirty:
            flag = QLabel("안 올림")
            flag.setStyleSheet(
                f"padding: 2px 8px; border-radius: 999px; font-size: 10.5px; "
                f"font-weight: 600; background: #f6efdd; color: #8a6d12;"
            )
            lay.addWidget(flag, 0)
        row.mousePressEvent = (  # type: ignore[method-assign]
            lambda _ev, e=entry: self._select_entry(e)
        )
        return row

    def _dirty_label(self, entry: ProjectEntry) -> tuple[str, str]:
        p = active_palette()
        if not entry.has_git:
            return "Git 없음", p.text_muted
        if entry.dirty and entry.dirty_count > 0:
            return f"파일 {entry.dirty_count}개", p.warn_text
        if entry.dirty:
            return "변경 있음", p.warn_text
        if entry.dirty is False:
            return "없음", p.text_muted
        return "—", p.text_muted

    def _make_project_block(self, entry: ProjectEntry) -> QWidget:
        """Parent row + optional expanded sub-rows (same 4-col widths)."""
        p = active_palette()
        block = QFrame()
        block.setObjectName("homeProjectBlock")
        block.setStyleSheet(
            f"QFrame#homeProjectBlock {{ border-bottom: 1px solid {p.border_soft}; }}"
        )
        v = QVBoxLayout(block)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._make_parent_row(entry))
        if entry.path in self._expanded:
            v.addWidget(self._make_expand_panel(entry))
        return block

    def _make_parent_row(self, entry: ProjectEntry) -> QWidget:
        p = active_palette()
        row = QFrame()
        row.setObjectName("homeProjectRow")
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        selected = (
            self._selected is not None and self._selected.path == entry.path
        )
        bg = p.hover_muted if selected else "transparent"
        row.setStyleSheet(
            f"QFrame#homeProjectRow {{ background: {bg}; }}"
            f"QFrame#homeProjectRow:hover {{ background: {p.bg_hint}; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        name_wrap = QHBoxLayout()
        name_wrap.setContentsMargins(0, 0, 0, 0)
        name_wrap.setSpacing(8)
        twist = QPushButton("▼" if entry.path in self._expanded else "▶")
        twist.setObjectName("homeTwist")
        twist.setFixedSize(16, 20)
        twist.setCursor(Qt.CursorShape.PointingHandCursor)
        twist.setFlat(True)
        twist.setStyleSheet(
            f"QPushButton {{ border: none; color: {p.text_muted}; font-size: 10px; }}"
        )
        twist.clicked.connect(lambda _=False, e=entry: self._toggle_expand(e))
        name_wrap.addWidget(twist, 0)
        name = QLabel(entry.name)
        name.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {p.text};"
        )
        name_wrap.addWidget(name, 1)
        name_host = QWidget()
        name_host.setLayout(name_wrap)
        lay.addWidget(name_host, 1)

        when = QLabel(format_relative_mtime(entry.last_mtime))
        when.setFixedWidth(118)
        when.setStyleSheet(
            f"font-size: 12px; color: {p.text_secondary}; font-family: Consolas, monospace;"
        )
        lay.addWidget(when, 0)

        dirty_t, dirty_c = self._dirty_label(entry)
        dirty = QLabel(dirty_t)
        dirty.setFixedWidth(108)
        dirty.setStyleSheet(
            f"font-size: 12px; color: {dirty_c}; "
            f"font-weight: {'600' if entry.dirty else '400'};"
        )
        lay.addWidget(dirty, 0)

        branch = QLabel(entry.branch or "—")
        branch.setFixedWidth(92)
        branch.setStyleSheet(
            f"font-size: 12px; color: {p.text_muted}; font-family: Consolas, monospace;"
        )
        lay.addWidget(branch, 0)

        row.mousePressEvent = (  # type: ignore[method-assign]
            lambda _ev, e=entry: self._select_entry(e)
        )
        return row

    def _make_expand_panel(self, entry: ProjectEntry) -> QWidget:
        """Sub-rows share parent column widths; indent only in column 1."""
        p = active_palette()
        panel = QFrame()
        panel.setStyleSheet(f"background: {p.bg_hint};")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 4, 0, 12)
        pv.setSpacing(2)
        cap = QLabel("이 안에서 최근에 손댄 곳")
        cap.setStyleSheet(
            f"padding: 4px 16px 6px 54px; font-size: 11px; color: {p.text_muted};"
        )
        pv.addWidget(cap)
        subs = self._subs_for(entry)
        if not subs:
            empty = QLabel("최근에 손댄 하위 경로가 없습니다.")
            empty.setStyleSheet(
                f"padding: 4px 16px 4px 54px; font-size: 11.5px; color: {p.text_faint};"
            )
            pv.addWidget(empty)
            return panel
        for hit in subs:
            pv.addWidget(self._make_sub_row(hit))
        return panel

    def _make_sub_row(self, hit: SubPathHit) -> QWidget:
        p = active_palette()
        row = QFrame()
        lay = QHBoxLayout(row)
        # Same padding/gap as parent so 118/108/92 columns line up
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(12)
        name_host = QWidget()
        nh = QHBoxLayout(name_host)
        nh.setContentsMargins(38, 0, 0, 0)  # indent inside col 1 only
        nh.setSpacing(8)
        path_l = QLabel(hit.rel_path)
        path_l.setStyleSheet(
            f"font-size: 12px; color: {p.text_secondary}; "
            f"font-family: Consolas, monospace;"
        )
        nh.addWidget(path_l, 1)
        lay.addWidget(name_host, 1)
        when = QLabel(format_relative_mtime(hit.mtime))
        when.setFixedWidth(118)
        when.setStyleSheet(
            f"font-size: 11.5px; color: {p.text_muted};"
        )
        lay.addWidget(when, 0)
        # Empty placeholders keep the 4-column alignment
        spacer_a = QWidget()
        spacer_a.setFixedWidth(108)
        spacer_b = QWidget()
        spacer_b.setFixedWidth(92)
        lay.addWidget(spacer_a, 0)
        lay.addWidget(spacer_b, 0)
        return row

    def _subs_for(self, entry: ProjectEntry) -> list[SubPathHit]:
        cached = self._subs_cache.get(entry.path)
        if cached is not None:
            return cached
        hits = list_recent_child_paths(entry.path, limit=8, max_depth=2)
        self._subs_cache[entry.path] = hits
        return hits

    def _toggle_expand(self, entry: ProjectEntry) -> None:
        if entry.path in self._expanded:
            self._expanded.discard(entry.path)
        else:
            self._expanded.add(entry.path)
            self._subs_for(entry)  # warm cache
        self._selected = entry
        self._rebuild_list()
        self._apply_detail(entry)

    def _select_entry(self, entry: ProjectEntry) -> None:
        self._selected = entry
        self._rebuild_list()
        self._apply_detail(entry)

    def _apply_detail(self, entry: ProjectEntry) -> None:
        self._detail_title.setText(entry.name)
        self._detail_path.setText(entry.path)
        bits = [
            f"마지막 작업: {format_relative_mtime(entry.last_mtime)}",
            "Git: " + ("있음" if entry.has_git else "없음"),
        ]
        if entry.has_git:
            if entry.dirty and entry.dirty_count > 0:
                bits.append(f"안 올린 변경: 파일 {entry.dirty_count}개")
            elif entry.dirty:
                bits.append("안 올린 변경: 있음")
            elif entry.dirty is False:
                bits.append("안 올린 변경: 없음")
            if entry.branch:
                bits.append(f"브랜치: {entry.branch}")
        self._detail_meta.setText("\n".join(bits))
        self._btn_primary.setEnabled(True)
        self._btn_history.setEnabled(entry.has_git)
        if not entry.has_git:
            self._btn_primary.setText("GitHub에 올리기 시작")
        elif entry.dirty:
            self._btn_primary.setText("올리고 받기 열기")
        else:
            self._btn_primary.setText("작업 열기")

    def _on_primary(self) -> None:
        if self._selected is None:
            return
        self.open_workspace.emit(self._selected.path)

    def _on_history(self) -> None:
        if self._selected is None or not self._selected.has_git:
            return
        from app.ui.commit_history_dialog import show_commit_history

        show_commit_history(self.window(), self._selected.path)

    def _add_scan_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "찾을 위치 추가")
        if not path:
            return
        add_scan_root(path)
        self.refresh_projects()

    def _refresh_account(self) -> None:
        p = active_palette()
        if is_logged_in():
            login = load_last_github_login() or "GitHub"
            self._account_btn.setText(f"  {login}")
            self._account_btn.setStyleSheet(
                f"QPushButton {{ text-align: left; border: none; border-radius: 6px;"
                f" padding: 6px 8px; background: transparent; color: {p.text};"
                f" font-size: 12.5px; }}"
                f"QPushButton:hover {{ background: {p.hover_muted}; }}"
            )
        else:
            self._account_btn.setText("GitHub 로그인")
            self._account_btn.setStyleSheet(
                f"QPushButton {{ border: 1px solid {p.primary}; border-radius: 7px;"
                f" background: {p.bg_window}; color: {p.primary}; font-weight: 600;"
                f" font-size: 12.5px; }}"
                f"QPushButton:hover {{ background: {p.bg_hint}; }}"
            )

    def _on_account_clicked(self) -> None:
        if is_logged_in():
            self._show_overflow()
        else:
            self._ctrl.on_login()

    def _show_overflow(self) -> None:
        populate_overflow_menu(
            self._overflow_menu,
            git_ok=self._ctrl._git_ok,
            git_version=self._ctrl._git_version_label,
            logged_in=is_logged_in(),
            on_settings=self._ctrl.on_settings_menu,
            on_help=self._ctrl.on_help_onboarding,
            on_terms=self._ctrl._open_terms_from_chrome,
            on_login=self._ctrl.on_login,
            on_logout=self._ctrl.on_logout,
            on_git_setup=self._ctrl._on_git_banner_install,
        )
        pos = self._overflow.mapToGlobal(self._overflow.rect().bottomLeft())
        self._overflow_menu.popup(pos)

    def _sync_git_banner(self) -> None:
        self._ctrl._refresh_status_bar()
        self._git_banner.setVisible(not self._ctrl._git_ok)

    def sync_from_controller(self) -> None:
        self._refresh_account()
        self._sync_git_banner()


def install_home_shell(window, controller: MainController) -> HomeShellWidget:
    """
    Wrap the existing central widget in a stack: [home | legacy workspace].

    Home is default (index 0). ``CLONEUP_LEGACY_TABS=1`` skips this entirely.
    """
    from PySide6.QtWidgets import QMainWindow

    assert isinstance(window, QMainWindow)
    old = window.centralWidget()
    stack = QStackedWidget()
    stack.setObjectName("mainUiStack")
    home = HomeShellWidget(controller)
    stack.addWidget(home)  # 0
    if old is not None:
        stack.addWidget(old)  # 1 legacy tabs + status
    window.setCentralWidget(stack)
    controller._ui_stack = stack
    controller._home_shell = home

    def _open_workspace(folder: str) -> None:
        # Prefill publish + sync folder fields, then show legacy tabs
        from app.ui.main_window import _set_folder_path

        if controller.editFolder is not None:
            _set_folder_path(controller.editFolder, folder)
            controller._maybe_fill_repo_name()
        if controller.editSyncFolder is not None:
            _set_folder_path(controller.editSyncFolder, folder)
        remember = True
        try:
            from app.ui.settings_store import remember_folder

            remember_folder(folder)
        except Exception:
            remember = False
        stack.setCurrentIndex(1)
        # Ensure a visible back affordance on status bar
        _ensure_home_back_button(controller, stack)

    home.open_workspace.connect(_open_workspace)
    # Phase B: drop legacy status-bar chrome widgets (A only hid them).
    for name in ("btnSettings", "btnHelpOnboarding", "btnLogout", "labelStatusGit"):
        w = window.findChild(QWidget, name)
        if w is not None:
            w.setParent(None)
            w.deleteLater()
    # Phase A overflow on the legacy status row — keep for workspace page.
    return home


def _ensure_home_back_button(controller: MainController, stack: QStackedWidget) -> None:
    """Add 「← 홈」 on the legacy status row once."""
    if getattr(controller, "_home_back_btn", None) is not None:
        return
    status = controller.window.findChild(QWidget, "statusBarFrame")
    lay = status.layout() if status is not None else None
    if not isinstance(lay, QHBoxLayout):
        return
    btn = QPushButton("← 홈")
    btn.setObjectName("btnBackToHome")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFlat(True)
    p = active_palette()
    btn.setStyleSheet(
        f"QPushButton {{ color: {p.primary}; font-size: 12.5px; font-weight: 600;"
        f" border: none; padding: 4px 8px; }}"
        f"QPushButton:hover {{ color: {p.primary_hover}; }}"
    )

    def _back() -> None:
        stack.setCurrentIndex(0)
        shell = getattr(controller, "_home_shell", None)
        if shell is not None:
            shell.sync_from_controller()
            shell.refresh_projects()

    btn.clicked.connect(_back)
    lay.insertWidget(0, btn)
    controller._home_back_btn = btn
