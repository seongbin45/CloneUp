"""Finder-style home shell (Phase B) — folder first, actions second.

Replaces the tab-first main chrome when ``CLONEUP_LEGACY_TABS`` is unset.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
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
    DIRTY_ENRICH_CAP,
    DIRTY_SELECT_DEBOUNCE_MS,
    DIRTY_TTL_SEC,
    ProjectEntry,
    SubPathHit,
    dirty_probe_is_stale,
    format_clock,
    format_relative_mtime,
    group_by_time_bucket,
    list_recent_child_paths,
    scan_projects,
    select_dirty_enrich_paths,
)
from app.ui.home_chrome import (
    GitMissingBanner,
    PillFrame,
    make_overflow_button,
    populate_overflow_menu,
)
from app.ui.home_cta import CtaActionId, build_cta_plan
from app.ui.home_repo_meta import resolve_home_repo_meta
from app.ui.home_tokens import (
    GLYPH_BACK,
    GLYPH_CRUMB_SEP,
    GLYPH_FWD,
    GLYPH_TWIST_CLOSED,
    GLYPH_TWIST_OPEN,
    HOME_COL_BRANCH,
    HOME_COL_DIRTY,
    HOME_COL_TIME,
    HOME_DETAIL_W,
    HOME_FONT_GLYPH,
    HOME_FONT_MONO,
    HOME_FONT_UI,
    HOME_MIN_WIDTH,
    HOME_RECENT_FILTER_CAP,
    HOME_SIDEBAR_W,
    display_path,
    home_chrome_colors,
)
from app.ui.home_widgets import (
    FactRow,
    FolderGlyph,
    PathActionsBar,
    github_browse_url,
    make_nav_chevron_icon,
)
from app.ui.settings_store import add_scan_root, load_last_github_login

if TYPE_CHECKING:
    from app.ui.main_window import MainController

# Sidebar filter keys (T-3; FILTER_GIT removed — not in 시안)
FILTER_ALL = "all"
FILTER_NO_GIT = "no_git"
FILTER_NO_REMOTE = "no_remote"
FILTER_RECENT = "recent"
FILTER_DIRTY = "dirty"
FILTER_TIME = "time"

# Braille-ish spinner frames (same as login_dialog)
_SPIN_FRAMES = ("◐", "◓", "◑", "◒")


def _apply_glyph_font(widget: QWidget) -> None:
    """Qt stylesheet font-family lists are unreliable — set QFont families in code."""
    f = widget.font()
    f.setFamilies(
        ["Segoe UI Symbol", "Segoe UI", "IBM Plex Sans KR", "Malgun Gothic"]
    )
    widget.setFont(f)


class _ScanWorker(QThread):
    """Fast path scan; emits each entry as found for progressive list paint."""

    entry_found = Signal(object)  # ProjectEntry (discovery order)
    finished_ok = Signal(object)  # list[ProjectEntry] (sorted)
    failed = Signal(str)

    def __init__(
        self,
        *,
        probe_dirty: bool = False,
        force_full: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._probe_dirty = probe_dirty
        self._force_full = force_full

    def run(self) -> None:  # noqa: N802
        try:
            from app.git.project_scan import scan_projects_incremental
            from app.git.scan_cache import ScanCacheLock, save_scan_cache

            def _on_found(entry: ProjectEntry) -> None:
                if self.isInterruptionRequested():
                    return
                self.entry_found.emit(entry)

            # UI must not inherit worker SCAN_TIMEBOX_SEC (45s) — that is for
            # schtasks only; home refresh should complete the walk.
            entries, _partial, cache = scan_projects_incremental(
                force_full=self._force_full,
                probe_dirty=self._probe_dirty,
                on_found=_on_found,
                skip_unc=False,
                timebox_sec=None,
            )
            if self.isInterruptionRequested():
                return
            cache.generator = "ui"
            lock = ScanCacheLock(timeout_sec=0.0)
            if lock.acquire():
                try:
                    save_scan_cache(cache)
                finally:
                    lock.release()
            # lock busy → keep memory result only (plan S5)
            self.finished_ok.emit(entries)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class _DirtyEnrichWorker(QThread):
    """Fill dirty/branch/has_origin after the fast path list is on screen."""

    # path, dirty(bool), count, branch, has_origin(object: bool|None)
    one_done = Signal(str, object, int, str, object)
    finished_all = Signal()

    def __init__(self, paths: list[str], parent=None) -> None:
        super().__init__(parent)
        self._paths = list(paths)

    def run(self) -> None:  # noqa: N802
        from pathlib import Path as _P

        from app.git.project_scan import _probe_git_presence

        for raw in self._paths:
            if self.isInterruptionRequested():
                break
            try:
                dirty, branch, count, has_origin = _probe_git_presence(_P(raw))
            except Exception:
                dirty, branch, count, has_origin = False, "", 0, None
            self.one_done.emit(
                raw, dirty, int(count), branch or "", has_origin
            )
        self.finished_all.emit()


class _MetaWorker(QThread):
    """GitHub access / visibility off the UI thread (was ~0.7–1.3s per click)."""

    finished_meta = Signal(str, int, object)  # path, generation, HomeRepoMeta

    def __init__(
        self, path: str, login: str | None, generation: int, parent=None
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._login = login
        self._generation = generation

    def run(self) -> None:  # noqa: N802
        meta = resolve_home_repo_meta(
            self._path, login=self._login, network=True
        )
        self.finished_meta.emit(self._path, self._generation, meta)


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
        self._sort_key = "time"  # "name" | "time"
        self._sort_desc = True  # time default desc; name first-click asc
        self._selected: ProjectEntry | None = None
        self._expanded: set[str] = set()
        self._subs_cache: dict[str, list[SubPathHit]] = {}
        self._meta_cache: dict[str, object] = {}
        self._meta_worker: _MetaWorker | None = None
        self._meta_gen: int = 0
        self._worker: _ScanWorker | None = None
        self._scan_gen: int = 0
        self._scanning: bool = False
        self._dirty_worker: _DirtyEnrichWorker | None = None
        self._dirty_probed_at: dict[str, float] = {}
        self._dirty_queue: list[str] = []
        self._select_probe_timer = QTimer(self)
        self._select_probe_timer.setSingleShot(True)
        self._select_probe_timer.setInterval(int(DIRTY_SELECT_DEBOUNCE_MS))
        self._select_probe_timer.timeout.connect(self._on_select_probe_timeout)
        self._pending_select_probe: str | None = None
        self._cta_action_ids: list[CtaActionId] = []
        # Live row handles — selection/expand/dirty without full rebuild
        self._row_by_path: dict[str, QFrame] = {}
        self._block_by_path: dict[str, QFrame] = {}
        self._timeline_row_by_path: dict[str, QFrame] = {}
        self._dirty_lab_by_path: dict[str, QLabel] = {}
        self._branch_lab_by_path: dict[str, QLabel] = {}
        self._twist_by_path: dict[str, QPushButton] = {}
        self._list_spin_wrap: QWidget | None = None
        self._list_spin_lab: QLabel | None = None
        self._list_spin_text: QLabel | None = None
        self._list_spin_i = 0
        self._list_spin_timer = QTimer(self)
        self._list_spin_timer.setInterval(90)
        self._list_spin_timer.timeout.connect(self._tick_list_spin)
        self._detail_spin_i = 0
        self._detail_spin_timer = QTimer(self)
        self._detail_spin_timer.setInterval(90)
        self._detail_spin_timer.timeout.connect(self._tick_detail_spin)
        # Animate "◐ …" dirty cells while enrich is in flight
        self._row_spin_i = 0
        self._row_spin_timer = QTimer(self)
        self._row_spin_timer.setInterval(120)
        self._row_spin_timer.timeout.connect(self._tick_row_spin)
        self.setObjectName("homeShell")
        self.setMinimumWidth(int(HOME_MIN_WIDTH))

        hc = home_chrome_colors()
        self._hc = hc
        self.setStyleSheet(
            f"QWidget#homeShell {{ background: {hc.bg_window};"
            f" font-family: {HOME_FONT_UI}; }}"
            f"QLabel {{ color: {hc.text}; font-family: {HOME_FONT_UI}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- top bar ---
        top = QFrame()
        top.setObjectName("homeTopBar")
        top.setStyleSheet(
            f"QFrame#homeTopBar {{ background: {hc.bg_sidebar}; "
            f"border-bottom: 1px solid {hc.border_soft}; }}"
        )
        # 시안 L34: padding 11px 14px · align-items: center · gap 14
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(14, 11, 14, 11)
        top_l.setSpacing(14)
        top_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        # 시안 L40–42: nav cluster gap 4 · 24×24 chevrons
        nav = QWidget()
        nav.setObjectName("homeNavChevrons")
        nav.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        nav.setStyleSheet(
            "QWidget#homeNavChevrons { background: transparent; border: none; }"
        )
        nav_l = QHBoxLayout(nav)
        nav_l.setContentsMargins(0, 0, 0, 0)
        nav_l.setSpacing(4)
        nav_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        from app.ui.home_chrome import RoundedHoverButton

        # 시안 L41–42: 24×24 · border-radius 5px · hover #e4e0d7.
        # QAbstractButton — never QPushButton (app QSS paints a sharp muted rect).
        # Idle fill = top bar (bg_sidebar) so light mode never shows a black hole.
        self._btn_back = RoundedHoverButton(radius=5.0, pill=False)
        self._btn_back.setObjectName("homeBackBtn")
        self._btn_back.setFixedSize(24, 24)
        self._btn_back.set_chrome(
            idle=hc.bg_sidebar, hover=hc.nav_hover, press=hc.nav_selected
        )
        self._btn_back.setIcon(
            make_nav_chevron_icon(left=True, fg=hc.text_secondary, size=24)
        )
        self._btn_back.setIconSize(self._btn_back.size())
        self._btn_back.clicked.connect(self._on_go_back)
        self._btn_fwd = RoundedHoverButton(radius=5.0, pill=False)
        self._btn_fwd.setObjectName("homeFwdBtn")
        self._btn_fwd.setFixedSize(24, 24)
        self._btn_fwd.setEnabled(False)
        self._btn_fwd.set_chrome(
            idle=hc.bg_sidebar, hover=hc.nav_hover, press=hc.nav_selected
        )
        self._btn_fwd.setIcon(
            make_nav_chevron_icon(left=False, fg=hc.text_faint, size=24)
        )
        self._btn_fwd.setIconSize(self._btn_fwd.size())
        nav_l.addWidget(self._btn_back, 0, Qt.AlignmentFlag.AlignVCenter)
        nav_l.addWidget(self._btn_fwd, 0, Qt.AlignmentFlag.AlignVCenter)
        top_l.addWidget(nav, 0, Qt.AlignmentFlag.AlignVCenter)
        self._heading = QLabel("모든 프로젝트")
        self._heading.setStyleSheet(
            f"font-size: 13.5px; font-weight: 600; color: {hc.text};"
            f" padding: 0; margin: 0; background: transparent;"
        )
        self._heading.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        top_l.addWidget(self._heading, 0, Qt.AlignmentFlag.AlignVCenter)
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
            f"background: {hc.bg_segment}; border-radius: 7px;"
        )
        mode_l.addWidget(self._btn_list_mode)
        mode_l.addWidget(self._btn_time_mode)
        top_l.addWidget(mode_wrap, 0, Qt.AlignmentFlag.AlignVCenter)
        self._refresh_mode_segment_styles()

        # 시안 L51: 216×28 · border-radius 999px (full capsule). Paint pill —
        # Windows ignores QFrame QSS radius (same bug as ◀ hover / scrollbars).
        search_wrap = PillFrame()
        search_wrap.setObjectName("homeSearchWrap")
        search_wrap.setFixedSize(216, 28)
        search_wrap.set_pill_chrome(
            fill=hc.bg_window,
            border=hc.cta_quiet_border,
            outer=hc.bg_sidebar,
        )
        self._search_wrap = search_wrap
        sw_l = QHBoxLayout(search_wrap)
        sw_l.setContentsMargins(11, 0, 8, 0)
        sw_l.setSpacing(8)
        search_icon = QLabel("⌕")
        search_icon.setStyleSheet(
            f"font-size: 12px; color: {hc.text_muted}; background: transparent;"
        )
        self._search = QLineEdit()
        self._search.setPlaceholderText("폴더 이름으로 찾기")
        self._search.setClearButtonEnabled(True)
        self._search.setFrame(False)
        self._search.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none;"
            f" font-size: 12.5px; color: {hc.text}; padding: 0; }}"
            f"QLineEdit:focus {{ background: transparent; border: none; }}"
        )
        self._search.textChanged.connect(self._on_query)
        sw_l.addWidget(search_icon, 0)
        sw_l.addWidget(self._search, 1)
        top_l.addWidget(search_wrap, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(top)

        # Git banner (same home chrome map — T-1(b))
        self._git_banner = GitMissingBanner(self, colors=hc)
        self._git_banner.install_clicked.connect(self._ctrl._on_git_banner_install)
        root.addWidget(self._git_banner)

        # --- body ---
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Sidebar
        side = QFrame()
        side.setObjectName("homeSidebar")
        side.setFixedWidth(int(HOME_SIDEBAR_W))
        side.setStyleSheet(
            f"QFrame#homeSidebar {{ background: {hc.bg_sidebar}; "
            f"border-right: 1px solid {hc.border_soft}; }}"
        )
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.setSpacing(0)

        from app.ui.pill_scrollbar import wire_pill_scrollbars

        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        wire_pill_scrollbars(nav_scroll)
        nav_host = QWidget()
        self._nav_layout = QVBoxLayout(nav_host)
        self._nav_layout.setContentsMargins(0, 14, 0, 8)
        self._nav_layout.setSpacing(16)
        # key → (row, icon_lab, name_lab, count_lab)
        self._nav_rows: dict[str, tuple[QFrame, QLabel, QLabel, QLabel]] = {}
        self._build_nav()
        self._nav_layout.addStretch(1)
        nav_scroll.setWidget(nav_host)
        side_l.addWidget(nav_scroll, 1)

        # Footer: account + ⋯ (시안: avatar+name+dot | login CTA + overflow)
        # side must be position-able parent for the floating menu panel.
        side.setProperty("homeSidebarRoot", True)
        foot = QFrame()
        foot.setObjectName("homeSideFoot")
        foot.setStyleSheet(f"border-top: 1px solid {hc.border_soft};")
        foot_l = QHBoxLayout(foot)
        foot_l.setContentsMargins(8, 8, 8, 8)
        foot_l.setSpacing(6)
        self._account_host = QFrame()
        self._account_host.setObjectName("homeAccountHost")
        self._account_host.setCursor(Qt.CursorShape.PointingHandCursor)
        self._account_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._account_host.setMinimumHeight(35)
        self._account_host_l = QHBoxLayout(self._account_host)
        self._account_host_l.setContentsMargins(0, 0, 0, 0)
        self._account_host_l.setSpacing(0)
        self._account_host.mousePressEvent = (  # type: ignore[method-assign]
            lambda _ev: self._on_account_clicked()
        )
        foot_l.addWidget(self._account_host, 1)
        from app.ui.home_chrome import apply_overflow_colors

        self._overflow = make_overflow_button(foot, colors=hc)
        apply_overflow_colors(self._overflow, hc)
        self._overflow.clicked.connect(self._toggle_overflow_panel)
        foot_l.addWidget(self._overflow, 0)
        side_l.addWidget(foot, 0)
        self._side = side
        self._side_foot = foot
        # 시안 floating menu (not OS QMenu) — above footer inside sidebar
        self._overflow_panel: QFrame | None = None
        self._overflow_open = False
        body.addWidget(side)

        # Center list
        center = QFrame()
        center.setObjectName("homeCenter")
        center_l = QVBoxLayout(center)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(
            f"background: {hc.bg_detail}; border-bottom: 1px solid {hc.border_soft};"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(12)
        self._h_name = QLabel("이름")
        self._h_time = QLabel("마지막 작업")
        self._h_dirty = QLabel("안 올린 변경")
        self._h_branch = QLabel("브랜치")
        for lab in (self._h_name, self._h_time, self._h_dirty, self._h_branch):
            lab.setStyleSheet(
                f"font-size: 11.5px; font-weight: 600; color: {hc.text_muted};"
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
        self._h_time.setFixedWidth(int(HOME_COL_TIME))
        self._h_dirty.setFixedWidth(int(HOME_COL_DIRTY))
        self._h_branch.setFixedWidth(int(HOME_COL_BRANCH))
        h.addWidget(self._h_time, 0)
        h.addWidget(self._h_dirty, 0)
        h.addWidget(self._h_branch, 0)
        self._list_header = header
        center_l.addWidget(header)

        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_scroll.setStyleSheet(
            f"QScrollArea {{ background: {hc.bg_window}; border: none; }}"
        )
        wire_pill_scrollbars(self._list_scroll)
        self._list_host = QWidget()
        self._list_host.setObjectName("homeListHost")
        self._list_host.setStyleSheet(
            f"QWidget#homeListHost {{ background: {hc.bg_window}; }}"
        )
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch(1)
        self._list_scroll.setWidget(self._list_host)
        center_l.addWidget(self._list_scroll, 1)

        body.addWidget(center, 1)

        # Right detail
        right = QFrame()
        right.setObjectName("homeDetail")
        right.setFixedWidth(int(HOME_DETAIL_W))
        # Global app QSS sets `QWidget { background: bg_window }`. Punch through
        # with transparent children, but carve out #homeDetailNoteWrap — the
        # generic `QWidget` rule would otherwise erase the NOT_MINE warn banner.
        # No QScrollArea here: it crushed the 286px panel into a narrow column.
        right.setStyleSheet(
            f"QFrame#homeDetail {{ background: {hc.bg_detail}; "
            f"border-left: 1px solid {hc.border_soft}; }}"
            f"QFrame#homeDetail QWidget {{ background-color: transparent; }}"
            f"QFrame#homeDetail QLabel {{ background-color: transparent; }}"
            f"QFrame#homeDetail QWidget#homeDetailNoteWrap {{"
            f" background-color: {hc.bg_warn_note}; border-radius: 8px; }}"
            f"QFrame#homeDetail QLabel#homeDetailNote {{"
            f" background-color: transparent; color: {hc.text_secondary};"
            f" font-size: 11.5px; }}"
        )
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 16, 16, 16)
        rl.setSpacing(10)
        self._detail_icon = FolderGlyph(
            has_git=True, large=True, colors=hc, fill_bg=hc.bg_detail
        )
        icon_row = QHBoxLayout()
        icon_row.addStretch(1)
        icon_row.addWidget(self._detail_icon, 0)
        icon_row.addStretch(1)
        rl.addLayout(icon_row)
        from app.ui.marquee_label import MarqueeLabel

        self._detail_title = MarqueeLabel(
            "폴더를 하나 고르면 여기에서 바로 올리고 받을 수 있습니다."
        )
        self._detail_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._detail_title.setStyleSheet(
            f"font-size: 12.5px; font-weight: 400; color: {hc.text_muted};"
            f" background: transparent;"
        )
        self._detail_subtitle = QLabel("")
        self._detail_subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._detail_subtitle.setStyleSheet(
            f"font-size: 12px; color: {hc.text_muted}; background: transparent;"
        )
        rl.addWidget(self._detail_title)
        rl.addWidget(self._detail_subtitle)
        # Path actions under title — same box, side by side (not fact rows)
        self._path_actions = PathActionsBar()
        self._path_actions.hide()
        rl.addWidget(self._path_actions)
        # Meta-load spinner (GitHub access / visibility)
        self._detail_loading = QWidget()
        self._detail_loading.setObjectName("homeDetailLoading")
        self._detail_loading.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self._detail_loading.setAutoFillBackground(False)
        dl = QHBoxLayout(self._detail_loading)
        dl.setContentsMargins(0, 6, 0, 2)
        dl.setSpacing(8)
        dl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._detail_spin_lab = QLabel(_SPIN_FRAMES[0])
        self._detail_spin_lab.setObjectName("homeDetailSpin")
        self._detail_spin_lab.setStyleSheet(
            f"font-size: 14px; color: {hc.text_muted}; background: transparent;"
        )
        self._detail_spin_text = QLabel("GitHub 정보를 확인하는 중…")
        self._detail_spin_text.setStyleSheet(
            f"font-size: 12px; color: {hc.text_muted}; background: transparent;"
        )
        dl.addWidget(self._detail_spin_lab, 0)
        dl.addWidget(self._detail_spin_text, 0)
        self._detail_loading.hide()
        rl.addWidget(self._detail_loading)
        self._facts_host = QWidget()
        self._facts_host.setObjectName("homeFactsHost")
        self._facts_host.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self._facts_host.setAutoFillBackground(False)
        self._facts_layout = QVBoxLayout(self._facts_host)
        self._facts_layout.setContentsMargins(0, 8, 0, 0)
        self._facts_layout.setSpacing(0)
        rl.addWidget(self._facts_host)
        self._cta_host = QWidget()
        self._cta_host.setObjectName("homeCtaHost")
        self._cta_host.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self._cta_host.setAutoFillBackground(False)
        self._cta_layout = QVBoxLayout(self._cta_host)
        self._cta_layout.setContentsMargins(0, 4, 0, 0)
        self._cta_layout.setSpacing(8)
        rl.addWidget(self._cta_host)
        # Warn banner as QFrame so parent `QWidget{transparent}` cannot erase fill.
        self._note_wrap = QFrame()
        self._note_wrap.setObjectName("homeDetailNoteWrap")
        self._note_wrap.setStyleSheet(
            f"QWidget#homeDetailNoteWrap {{ background-color: {hc.bg_warn_note};"
            f" border-radius: 8px; }}"
        )
        note_l = QVBoxLayout(self._note_wrap)
        note_l.setContentsMargins(11, 11, 11, 11)
        note_l.setSpacing(0)
        self._note_label = QLabel("")
        self._note_label.setObjectName("homeDetailNote")
        self._note_label.setWordWrap(True)
        self._note_label.setStyleSheet(
            f"QLabel#homeDetailNote {{ background: transparent;"
            f" color: {hc.text_secondary}; font-size: 11.5px; }}"
        )
        note_l.addWidget(self._note_label)
        self._note_wrap.hide()
        rl.addWidget(self._note_wrap)
        rl.addStretch(1)
        body.addWidget(right)

        root.addLayout(body, 1)

        # Breadcrumb + count (시안 하단)
        crumb_bar = QFrame()
        crumb_bar.setObjectName("homeCrumbBar")
        crumb_bar.setStyleSheet(
            f"QFrame#homeCrumbBar {{ background: {hc.bg_window};"
            f" border-top: 1px solid {hc.border_soft}; }}"
        )
        crumb_l = QHBoxLayout(crumb_bar)
        crumb_l.setContentsMargins(16, 8, 16, 8)
        self._crumb = QLabel(f"이 컴퓨터  {GLYPH_CRUMB_SEP}  모든 프로젝트")
        self._crumb.setStyleSheet(
            f"font-size: 11.5px; color: {hc.text_muted}; font-family: {HOME_FONT_UI};"
        )
        crumb_l.addWidget(self._crumb, 1)
        self._status = QLabel("")
        self._status.setStyleSheet(
            f"font-size: 11.5px; color: {hc.text_muted};"
        )
        crumb_l.addWidget(self._status, 0)
        root.addWidget(crumb_bar)

        # Legacy QMenu kept unused — panel replaces OS popup (시안).
        self._overflow_menu = QMenu(self)
        self._refresh_account()
        self._sync_git_banner()
        self._clear_detail_nopick()
        self._update_header_emphasis()
        self._select_filter(FILTER_ALL, refresh=False)
        self.refresh_projects()

    def _style_cta(self, btn: QPushButton, *, variant: str) -> None:
        hc = self._hc
        # Use background-color (not shorthand) so we beat
        # `QFrame#homeDetail QWidget { background-color: transparent }`.
        if variant == "primary":
            from app.ui.theme import active_palette

            on_primary = active_palette().text_on_primary
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hc.primary}; color: {on_primary};"
                f" border: none; border-radius: 6px; font-weight: 600; font-size: 13.5px; }}"
                f"QPushButton:hover {{ background-color: {hc.primary_hover}; }}"
            )
        elif variant == "quiet":
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hc.cta_quiet_bg}; color: {hc.cta_quiet_fg};"
                f" border: 1px solid {hc.cta_quiet_border}; border-radius: 6px;"
                f" font-size: 13px; font-weight: 400; }}"
                f"QPushButton:hover {{ background-color: {hc.row_hover}; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hc.cta_normal_bg}; color: {hc.cta_normal_fg};"
                f" border: 1px solid {hc.cta_normal_border}; border-radius: 6px;"
                f" font-size: 13px; font-weight: 500; }}"
                f"QPushButton:hover {{ background-color: {hc.row_hover}; }}"
            )

    def _build_nav(self) -> None:
        """Sidebar filters — 시안: icon (15px) + label + optional count."""
        hc = self._hc
        groups = [
            (
                "내 작업",
                [
                    (FILTER_ALL, "모든 프로젝트", "◧"),
                    (FILTER_RECENT, "최근 작업", "◔"),
                    (FILTER_DIRTY, "안 올린 변경", "●"),
                    (FILTER_TIME, "시간순 보기", "☰"),
                ],
            ),
            (
                "아직 연결 안 됨",
                [
                    (FILTER_NO_GIT, "Git 없는 폴더", "◌"),
                    (FILTER_NO_REMOTE, "원격 없는 Git", "○"),
                ],
            ),
        ]
        self._nav_rows.clear()
        for title, items in groups:
            box = QVBoxLayout()
            box.setSpacing(2)
            lab = QLabel(title)
            lab.setStyleSheet(
                f"padding: 0 16px 6px; font-size: 11px; font-weight: 600; "
                f"color: {hc.text_muted}; letter-spacing: 0.02em;"
            )
            box.addWidget(lab)
            for key, label, icon in items:
                row = QFrame()
                row.setObjectName(f"homeNav_{key}")
                row.setCursor(Qt.CursorShape.PointingHandCursor)
                rl = QHBoxLayout(row)
                # 시안: margin 0 8px + padding 7px 10px → outer margins here
                rl.setContentsMargins(10, 7, 10, 7)
                rl.setSpacing(9)
                icon_lab = QLabel(icon)
                icon_lab.setFixedWidth(15)
                icon_lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon_lab.setStyleSheet(
                    f"font-size: 11px; color: {hc.text_muted}; background: transparent;"
                )
                name_lab = QLabel(label)
                name_lab.setStyleSheet(
                    f"font-size: 12.5px; color: {hc.text_secondary};"
                    f" background: transparent;"
                )
                count_lab = QLabel("")
                count_lab.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                count_lab.setStyleSheet(
                    f"font-size: 11px; color: {hc.text_muted}; background: transparent;"
                )
                count_lab.hide()
                rl.addWidget(icon_lab, 0)
                rl.addWidget(name_lab, 1)
                rl.addWidget(count_lab, 0)
                row.mousePressEvent = (  # type: ignore[method-assign]
                    lambda _ev, k=key: self._select_filter(k, refresh=True)
                )
                self._nav_rows[key] = (row, icon_lab, name_lab, count_lab)
                # Outer margin 0 8px via wrapper margins on the row stylesheet
                row.setStyleSheet(
                    f"QFrame#homeNav_{key} {{ margin: 0 8px; border-radius: 6px;"
                    f" background: transparent; }}"
                    f"QFrame#homeNav_{key}:hover {{ background: {hc.nav_hover}; }}"
                )
                box.addWidget(row)
            self._nav_layout.addLayout(box)

        add = QFrame()
        add.setObjectName("homeAddScanRoot")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        al = QHBoxLayout(add)
        al.setContentsMargins(10, 7, 10, 7)
        al.setSpacing(9)
        plus = QLabel("+")
        plus.setFixedWidth(15)
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus.setStyleSheet(
            f"font-size: 12px; color: {hc.text_muted}; background: transparent;"
        )
        add_lab = QLabel("찾을 위치 추가")
        add_lab.setStyleSheet(
            f"font-size: 12.5px; color: {hc.text_muted}; background: transparent;"
        )
        al.addWidget(plus, 0)
        al.addWidget(add_lab, 1)
        add.setStyleSheet(
            f"QFrame#homeAddScanRoot {{ margin: 0 8px; border-radius: 6px;"
            f" background: transparent; }}"
            f"QFrame#homeAddScanRoot:hover {{ background: {hc.nav_hover}; }}"
        )
        add.mousePressEvent = (  # type: ignore[method-assign]
            lambda _ev: self._add_scan_root()
        )
        self._nav_layout.addWidget(add)
        self._paint_nav_selection()

    def _paint_nav_selection(self) -> None:
        """Apply 시안 selected/idle colors to icon + label (+ count)."""
        from app.ui.home_tokens import HOME_SIDEBAR_W
        from app.ui.text_fit import apply_fitting_font, measure_text_width_px

        hc = self._hc
        side_w = int(getattr(self, "_side", None).width() if getattr(self, "_side", None) else HOME_SIDEBAR_W)
        for key, (row, icon_lab, name_lab, count_lab) in self._nav_rows.items():
            active = key == self._filter
            bg = hc.nav_selected if active else "transparent"
            fg = hc.text if active else hc.text_secondary
            icon_fg = hc.primary if active else hc.text_muted
            row.setStyleSheet(
                f"QFrame#homeNav_{key} {{ margin: 0 8px; border-radius: 6px;"
                f" background: {bg}; }}"
                f"QFrame#homeNav_{key}:hover {{ background: "
                f"{hc.nav_selected if active else hc.nav_hover}; }}"
            )
            icon_lab.setStyleSheet(
                f"font-size: 11px; color: {icon_fg}; background: transparent;"
            )
            count_txt = count_lab.text().strip()
            count_w = (
                measure_text_width_px(count_txt, 11.0) + 4.0 if count_txt else 0.0
            )
            # margin 16 + pad 20 + icon 15 + gap 9 + count
            budget = float(side_w - 16 - 20 - 15 - 9) - count_w
            apply_fitting_font(
                name_lab,
                name_lab.text() or "",
                max(40.0, budget),
                base_px=12.5,
                min_px=9.5,
                bold=active,
                color=fg,
            )
            if key == FILTER_DIRTY and count_txt:
                count_lab.setStyleSheet(
                    f"font-size: 11px; color: {hc.warn_text}; background: transparent;"
                )
            else:
                count_lab.setStyleSheet(
                    f"font-size: 11px; color: {hc.text_muted}; background: transparent;"
                )

    def _refresh_nav_counts(self) -> None:
        """Update sidebar counts (시안: 모든 프로젝트 / 안 올린 변경 / Git 없는 폴더)."""
        git_n = sum(1 for e in self._entries if e.has_git)
        nogit_n = sum(1 for e in self._entries if not e.has_git)
        dirty_n = sum(1 for e in self._entries if e.dirty)
        no_remote_n = sum(
            1 for e in self._entries if e.has_git and e.has_origin is False
        )
        mapping = {
            FILTER_ALL: str(git_n) if git_n else "",
            FILTER_DIRTY: str(dirty_n) if dirty_n else "",
            FILTER_NO_GIT: str(nogit_n) if nogit_n else "",
            FILTER_NO_REMOTE: str(no_remote_n) if no_remote_n else "",
        }
        for key, text in mapping.items():
            row = self._nav_rows.get(key)
            if row is None:
                continue
            _r, _i, _n, count_lab = row
            if text:
                count_lab.setText(text)
                count_lab.show()
            else:
                count_lab.setText("")
                count_lab.hide()
        self._paint_nav_selection()

    def _select_filter(self, key: str, *, refresh: bool) -> None:
        self._filter = key
        # 사이드바 「시간순 보기」만 타임라인; 다른 패널로 나가면 목록으로 복귀.
        # (이전: _view_timeline이 True로 남아 다른 필터에서도 시간순 UI가 유지됨)
        if key == FILTER_TIME:
            self._view_timeline = True
        else:
            self._view_timeline = False
        titles = {
            FILTER_ALL: "모든 프로젝트",
            FILTER_NO_GIT: "Git 없는 폴더",
            FILTER_NO_REMOTE: "원격 없는 Git",
            FILTER_RECENT: "최근 작업",
            FILTER_DIRTY: "안 올린 변경",
            FILTER_TIME: "시간순 보기",
        }
        self._heading.setText(titles.get(key, "모든 프로젝트"))
        if key == FILTER_TIME:
            self._btn_list_mode.setChecked(False)
            self._btn_time_mode.setChecked(True)
            if hasattr(self, "_list_header") and self._list_header is not None:
                self._list_header.setVisible(False)
        else:
            self._btn_list_mode.setChecked(True)
            self._btn_time_mode.setChecked(False)
            if hasattr(self, "_list_header") and self._list_header is not None:
                self._list_header.setVisible(True)
        self._paint_nav_selection()
        self._refresh_mode_segment_styles()
        self._update_breadcrumb()
        if refresh:
            self._rebuild_list()
            self._update_dirty_status_line()

    def _set_view_mode(self, *, timeline: bool) -> None:
        self._view_timeline = timeline
        self._btn_list_mode.setChecked(not timeline)
        self._btn_time_mode.setChecked(timeline)
        if timeline:
            self._filter = FILTER_TIME
        elif self._filter == FILTER_TIME:
            self._filter = FILTER_ALL
        if hasattr(self, "_list_header") and self._list_header is not None:
            self._list_header.setVisible(not timeline)
        self._paint_nav_selection()
        self._heading.setText(
            "시간순 보기" if timeline else {
                FILTER_ALL: "모든 프로젝트",
                FILTER_NO_GIT: "Git 없는 폴더",
                FILTER_NO_REMOTE: "원격 없는 Git",
                FILTER_RECENT: "최근 작업",
                FILTER_DIRTY: "안 올린 변경",
            }.get(self._filter, "모든 프로젝트")
        )
        self._refresh_mode_segment_styles()
        self._update_breadcrumb()
        self._rebuild_list()

    def _set_list_sort(self, *, time_sort: bool) -> None:
        """Header click: name first→asc▲, time first→desc▼; re-click toggles."""
        self._view_timeline = False
        if time_sort:
            if self._sort_key == "time":
                self._sort_desc = not self._sort_desc
            else:
                self._sort_key = "time"
                self._sort_desc = True
        else:
            if self._sort_key == "name":
                self._sort_desc = not self._sort_desc
            else:
                self._sort_key = "name"
                self._sort_desc = False
        self._btn_list_mode.setChecked(True)
        self._btn_time_mode.setChecked(False)
        if hasattr(self, "_list_header") and self._list_header is not None:
            self._list_header.setVisible(True)
        self._refresh_mode_segment_styles()
        self._update_header_emphasis()
        self._rebuild_list()

    def _refresh_mode_segment_styles(self) -> None:
        hc = self._hc
        for b, on in (
            (self._btn_list_mode, not self._view_timeline),
            (self._btn_time_mode, self._view_timeline),
        ):
            if on:
                b.setStyleSheet(
                    f"QPushButton {{ background: {hc.bg_window}; color: {hc.text};"
                    f" border: none; border-radius: 5px; padding: 4px 10px;"
                    f" font-weight: 600; font-size: 12px; }}"
                )
            else:
                b.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {hc.text_muted};"
                    f" border: none; border-radius: 5px; padding: 4px 10px;"
                    f" font-weight: 400; font-size: 12px; }}"
                )

    def _update_header_emphasis(self) -> None:
        hc = self._hc
        name_on = self._sort_key == "name"
        time_on = self._sort_key == "time"
        name_arrow = (
            (GLYPH_TWIST_OPEN if self._sort_desc else "\u25B2") if name_on else ""
        )
        time_arrow = (
            (GLYPH_TWIST_OPEN if self._sort_desc else "\u25B2") if time_on else ""
        )
        active = (
            f"font-size: 11.5px; font-weight: 600; color: {hc.text};"
            f" font-family: {HOME_FONT_GLYPH};"
        )
        idle = (
            f"font-size: 11.5px; font-weight: 600; color: {hc.text_muted};"
            f" font-family: {HOME_FONT_UI};"
        )
        self._h_name.setText(f"이름 {name_arrow}".rstrip())
        self._h_time.setText(f"마지막 작업 {time_arrow}".rstrip())
        self._h_name.setStyleSheet(active if name_on else idle)
        self._h_time.setStyleSheet(active if time_on else idle)

    def _on_query(self, text: str) -> None:
        self._query = (text or "").strip().lower()
        self._rebuild_list()

    def refresh_projects(self, *, force_full: bool = False) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        if self._dirty_worker is not None and self._dirty_worker.isRunning():
            self._dirty_worker.requestInterruption()
        self._select_probe_timer.stop()
        self._pending_select_probe = None
        self._dirty_queue.clear()
        self._dirty_probed_at.clear()
        self._subs_cache.clear()
        self._scan_gen += 1
        gen = self._scan_gen
        self._scanning = True

        # C-6: paint from disk cache immediately, then refresh in background.
        from app.git.scan_cache import load_scan_cache, validate_entries

        cached = load_scan_cache()
        if cached is not None and cached.entries and not force_full:
            from app.git.project_scan import resolve_scan_roots
            from app.git.scan_cache import filter_entries_for_roots

            self._entries = filter_entries_for_roots(
                validate_entries(list(cached.entries)),
                resolve_scan_roots(),
            )
            self._clear_list_rows(keep_spinner=False)
            self._show_list_spinner(True)
            self._rebuild_list()
            self._status.setText(
                f"{len(self._entries)}개 폴더 · 목록 확인 중…"
            )
        else:
            self._entries = []
            self._clear_list_rows(keep_spinner=False)
            self._show_list_spinner(True)
            self._status.setText("폴더를 찾는 중…")

        w = _ScanWorker(
            probe_dirty=False, force_full=force_full, parent=self
        )
        w.entry_found.connect(
            lambda e, g=gen: self._on_scan_entry(e, g)
        )
        w.finished_ok.connect(
            lambda entries, g=gen: self._on_scan_done(entries, g)
        )
        w.failed.connect(lambda msg, g=gen: self._on_scan_fail(msg, g))
        self._worker = w
        w.start()

    def _on_scan_entry(self, entry: object, generation: int) -> None:
        """Progressive list: append one row as soon as the scanner finds it."""
        if generation != self._scan_gen:
            return
        if not isinstance(entry, ProjectEntry):
            return
        if any(e.path == entry.path for e in self._entries):
            return
        self._entries.append(entry)
        n = len(self._entries)
        self._status.setText(f"{n}개 폴더 찾는 중…")
        if self._list_spin_text is not None:
            self._list_spin_text.setText(f"폴더를 찾는 중… ({n})")
        if self._entry_matches_filters(entry):
            self._append_list_entry(entry)

    def _on_scan_done(self, entries: object, generation: int = 0) -> None:
        if generation and generation != self._scan_gen:
            return
        self._worker = None
        self._scanning = False
        self._show_list_spinner(False)
        if isinstance(entries, list):
            self._entries = [e for e in entries if isinstance(e, ProjectEntry)]
        else:
            self._entries = []
        n = len(self._entries)
        git_n = sum(1 for e in self._entries if e.has_git)
        if git_n:
            self._status.setText(f"{n}개 폴더 · 최근 활동 폴더 확인 중…")
        else:
            self._status.setText(f"{n}개 폴더")
        # One final sorted rebuild (discovery order → mtime/name sort).
        self._rebuild_list()
        self._refresh_nav_counts()
        self._start_dirty_enrich()

    def _needs_dirty_probe(self, path: str) -> bool:
        entry = next((e for e in self._entries if e.path == path), None)
        if entry is None or not entry.has_git:
            return False
        return dirty_probe_is_stale(
            self._dirty_probed_at.get(path),
            now=time.monotonic(),
            ttl_sec=float(DIRTY_TTL_SEC),
        )

    def _initial_dirty_paths(self) -> list[str]:
        """mtime 상위 K ∪ 현재 선택 (S0: DIRTY_ENRICH_CAP)."""
        selected = self._selected.path if self._selected is not None else None
        paths = select_dirty_enrich_paths(
            self._entries,
            cap=int(DIRTY_ENRICH_CAP),
            selected_path=selected,
        )
        return [p for p in paths if self._needs_dirty_probe(p)]

    def _start_dirty_enrich(self) -> None:
        paths = self._initial_dirty_paths()
        if not paths:
            self._update_dirty_status_line()
            return
        self._enqueue_dirty(paths)

    def _enqueue_dirty(self, paths: list[str]) -> None:
        for p in paths:
            if not p or p in self._dirty_queue:
                continue
            if not self._needs_dirty_probe(p):
                continue
            self._dirty_queue.append(p)
        self._pump_dirty_worker()

    def _pump_dirty_worker(self) -> None:
        if self._dirty_worker is not None and self._dirty_worker.isRunning():
            return
        if not self._dirty_queue:
            self._update_dirty_status_line()
            return
        batch = self._dirty_queue[:]
        self._dirty_queue.clear()
        self._status.setText(
            f"{len(self._entries)}개 폴더 · 최근 활동 폴더 확인 중…"
        )
        w = _DirtyEnrichWorker(batch, parent=self)
        w.one_done.connect(self._on_dirty_one)
        w.finished_all.connect(self._on_dirty_all)
        self._dirty_worker = w
        self._ensure_row_spin()
        w.start()

    def _on_dirty_one(
        self,
        path: str,
        dirty: object,
        count: int,
        branch: str,
        has_origin: object = None,
    ) -> None:
        self._dirty_probed_at[path] = time.monotonic()
        updated: list[ProjectEntry] = []
        changed = False
        origin_was = None
        for e in self._entries:
            if e.path != path:
                updated.append(e)
                continue
            dirty_b = bool(dirty) if isinstance(dirty, bool) else None
            origin_b = (
                bool(has_origin)
                if isinstance(has_origin, bool)
                else e.has_origin
            )
            origin_was = e.has_origin
            updated.append(
                ProjectEntry(
                    path=e.path,
                    name=e.name,
                    has_git=e.has_git,
                    last_mtime=e.last_mtime,
                    dirty=dirty_b,
                    dirty_count=int(count or 0),
                    branch=branch or e.branch,
                    has_origin=origin_b,
                )
            )
            changed = True
        if changed:
            self._entries = updated
            entry = next((x for x in self._entries if x.path == path), None)
            # Keep selection object in sync
            if self._selected is not None and self._selected.path == path:
                self._selected = entry if entry is not None else self._selected
                self._apply_detail(self._selected)
            # DIRTY / NO_REMOTE membership can change → full rebuild; else patch.
            origin_now = entry.has_origin if entry is not None else None
            if self._filter == FILTER_DIRTY or (
                self._filter == FILTER_NO_REMOTE and origin_was != origin_now
            ):
                self._rebuild_list()
            elif entry is not None:
                self._patch_row_dirty(entry)

    def _on_dirty_all(self) -> None:
        self._dirty_worker = None
        # Drain anything enqueued while the batch ran (e.g. debounced select)
        if self._dirty_queue:
            self._pump_dirty_worker()
            return
        self._update_dirty_status_line()

    def _update_dirty_status_line(self) -> None:
        self._refresh_nav_counts()
        shown = len(self._filtered())
        dirty_n = sum(1 for e in self._entries if e.dirty)
        pending = sum(
            1
            for e in self._entries
            if e.has_git and e.dirty is None and self._needs_dirty_probe(e.path)
        )
        origin_pending = sum(
            1 for e in self._entries if e.has_git and e.has_origin is None
        )
        base = f"{shown}개 폴더"
        if dirty_n and self._filter not in (FILTER_NO_GIT, FILTER_NO_REMOTE):
            base += f" · 변경 {dirty_n}곳"
        if pending and self._filter == FILTER_DIRTY:
            base += " · 일부는 아직 확인 전"
        if origin_pending and self._filter == FILTER_NO_REMOTE:
            base += " · 일부는 아직 확인 전"
        self._status.setText(base)
        self._update_breadcrumb()

    def _update_breadcrumb(self) -> None:
        hc = self._hc
        heading = self._heading.text() if hasattr(self, "_heading") else "모든 프로젝트"
        sep = f" {GLYPH_CRUMB_SEP} "
        parts = [f'<span style="color:{hc.text_muted}">이 컴퓨터</span>']
        parts.append(f'<span style="color:{hc.text_muted}">{sep}</span>')
        parts.append(f'<span style="color:{hc.text_muted}">{heading}</span>')
        if self._selected is not None:
            parts.append(f'<span style="color:{hc.text_muted}">{sep}</span>')
            parts.append(
                f'<span style="color:{hc.text}">{self._selected.name}</span>'
            )
        self._crumb.setText("".join(parts))

    def _on_go_back(self) -> None:
        """시안 goBack: nav→all, view→list, query clear; pick kept."""
        self._query = ""
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self._view_timeline = False
        self._filter = FILTER_ALL
        self._btn_list_mode.setChecked(True)
        self._btn_time_mode.setChecked(False)
        if hasattr(self, "_list_header") and self._list_header is not None:
            self._list_header.setVisible(True)
        self._heading.setText("모든 프로젝트")
        self._paint_nav_selection()
        self._refresh_mode_segment_styles()
        self._update_breadcrumb()
        self._rebuild_list()
        self._update_dirty_status_line()

    def _schedule_select_probe(self, path: str) -> None:
        if not path:
            return
        self._pending_select_probe = path
        self._select_probe_timer.start()

    def _on_select_probe_timeout(self) -> None:
        path = self._pending_select_probe
        self._pending_select_probe = None
        if not path:
            return
        # Only the last selection after debounce (S2-T2)
        if self._selected is None or self._selected.path != path:
            return
        if self._needs_dirty_probe(path):
            self._enqueue_dirty([path])

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if (
            self._selected is not None
            and self._selected.has_git
            and self._needs_dirty_probe(self._selected.path)
        ):
            self._schedule_select_probe(self._selected.path)

    def _on_scan_fail(self, msg: str, generation: int = 0) -> None:
        if generation and generation != self._scan_gen:
            return
        self._worker = None
        self._scanning = False
        self._show_list_spinner(False)
        self._status.setText(f"목록을 읽지 못했습니다: {msg[:80]}")

    def _filtered(self) -> list[ProjectEntry]:
        from app.ui.settings_store import load_recent_folders

        items = list(self._entries)
        q = self._query
        if q:
            items = [e for e in items if q in e.name.lower()]
        # T-3: 「모든 프로젝트」= git only; nogit has its own nav
        if self._filter == FILTER_ALL or self._filter == FILTER_TIME:
            items = [e for e in items if e.has_git]
        elif self._filter == FILTER_NO_GIT:
            items = [e for e in items if not e.has_git]
        elif self._filter == FILTER_NO_REMOTE:
            items = [
                e for e in items if e.has_git and e.has_origin is False
            ]
        elif self._filter == FILTER_DIRTY:
            items = [e for e in items if e.has_git and e.dirty]
        elif self._filter == FILTER_RECENT:
            recent_paths = []
            for raw in load_recent_folders():
                try:
                    recent_paths.append(str(Path(raw).resolve()).lower())
                except OSError:
                    continue
            by_path = {str(Path(e.path).resolve()).lower(): e for e in items}
            picked: list[ProjectEntry] = []
            for key in recent_paths:
                e = by_path.get(key)
                if e is not None:
                    picked.append(e)
                if len(picked) >= int(HOME_RECENT_FILTER_CAP):
                    break
            items = picked
        if self._view_timeline or self._filter == FILTER_TIME:
            if self._filter != FILTER_RECENT:
                items.sort(key=lambda e: e.last_mtime, reverse=True)
        elif self._filter == FILTER_RECENT:
            pass  # keep recent order
        elif self._sort_key == "time":
            items.sort(key=lambda e: e.last_mtime, reverse=self._sort_desc)
        else:
            items.sort(key=lambda e: e.name.lower(), reverse=self._sort_desc)
        return items

    def _clear_row_maps(self) -> None:
        self._row_by_path.clear()
        self._block_by_path.clear()
        self._timeline_row_by_path.clear()
        self._dirty_lab_by_path.clear()
        self._branch_lab_by_path.clear()
        self._twist_by_path.clear()

    def _clear_list_rows(self, *, keep_spinner: bool = False) -> None:
        """Remove list children except trailing stretch (and optional spinner)."""
        self._clear_row_maps()
        i = 0
        while i < self._list_layout.count() - 1:
            item = self._list_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if (
                keep_spinner
                and w is not None
                and w.objectName() == "homeListSpinner"
            ):
                i += 1
                continue
            taken = self._list_layout.takeAt(i)
            ww = taken.widget() if taken is not None else None
            if ww is not None:
                ww.hide()
                ww.setParent(None)
                ww.deleteLater()
            if ww is self._list_spin_wrap:
                self._list_spin_wrap = None
                self._list_spin_lab = None
                self._list_spin_text = None

    def _ensure_list_spinner(self) -> QWidget:
        if self._list_spin_wrap is not None:
            return self._list_spin_wrap
        hc = self._hc
        wrap = QWidget()
        wrap.setObjectName("homeListSpinner")
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        spin = QLabel(_SPIN_FRAMES[0])
        spin.setObjectName("homeListSpinLab")
        spin.setStyleSheet(f"font-size: 14px; color: {hc.text_muted};")
        text = QLabel("폴더를 찾는 중…")
        text.setStyleSheet(f"font-size: 12.5px; color: {hc.text_muted};")
        lay.addWidget(spin, 0)
        lay.addWidget(text, 0)
        lay.addStretch(1)
        self._list_spin_wrap = wrap
        self._list_spin_lab = spin
        self._list_spin_text = text
        return wrap

    def _show_list_spinner(self, on: bool) -> None:
        if on:
            wrap = self._ensure_list_spinner()
            # Keep spinner at top (index 0), before progressive rows.
            if self._list_layout.indexOf(wrap) < 0:
                self._list_layout.insertWidget(0, wrap)
            wrap.show()
            self._list_spin_i = 0
            if self._list_spin_lab is not None:
                self._list_spin_lab.setText(_SPIN_FRAMES[0])
            if not self._list_spin_timer.isActive():
                self._list_spin_timer.start()
        else:
            self._list_spin_timer.stop()
            wrap = self._list_spin_wrap
            if wrap is not None:
                idx = self._list_layout.indexOf(wrap)
                if idx >= 0:
                    self._list_layout.takeAt(idx)
                wrap.hide()
                wrap.setParent(None)
                wrap.deleteLater()
                self._list_spin_wrap = None
                self._list_spin_lab = None
                self._list_spin_text = None

    def _tick_list_spin(self) -> None:
        if self._list_spin_lab is None:
            return
        self._list_spin_i = (self._list_spin_i + 1) % len(_SPIN_FRAMES)
        self._list_spin_lab.setText(_SPIN_FRAMES[self._list_spin_i])

    def _tick_detail_spin(self) -> None:
        if not hasattr(self, "_detail_spin_lab") or self._detail_spin_lab is None:
            return
        self._detail_spin_i = (self._detail_spin_i + 1) % len(_SPIN_FRAMES)
        self._detail_spin_lab.setText(_SPIN_FRAMES[self._detail_spin_i])

    def _tick_row_spin(self) -> None:
        pending = False
        self._row_spin_i = (self._row_spin_i + 1) % len(_SPIN_FRAMES)
        frame = _SPIN_FRAMES[self._row_spin_i]
        for path, lab in list(self._dirty_lab_by_path.items()):
            entry = next((e for e in self._entries if e.path == path), None)
            if entry is None or not entry.has_git or entry.dirty is not None:
                continue
            pending = True
            lab.setText(f"{frame} …")
        if not pending:
            self._row_spin_timer.stop()

    def _ensure_row_spin(self) -> None:
        if any(
            e.has_git and e.dirty is None for e in self._entries
        ) and not self._row_spin_timer.isActive():
            self._row_spin_timer.start()

    def _show_detail_spinner(self, on: bool, msg: str = "") -> None:
        if not hasattr(self, "_detail_loading"):
            return
        if on:
            if msg and hasattr(self, "_detail_spin_text"):
                self._detail_spin_text.setText(msg)
            elif hasattr(self, "_detail_spin_text"):
                self._detail_spin_text.setText("GitHub 정보를 확인하는 중…")
            self._detail_spin_i = 0
            if hasattr(self, "_detail_spin_lab"):
                self._detail_spin_lab.setText(_SPIN_FRAMES[0])
            self._detail_loading.show()
            if not self._detail_spin_timer.isActive():
                self._detail_spin_timer.start()
        else:
            self._detail_spin_timer.stop()
            self._detail_loading.hide()

    def _entry_matches_filters(self, entry: ProjectEntry) -> bool:
        """Whether *entry* would appear under the current filter/query/view."""
        q = self._query
        if q and q not in entry.name.lower():
            return False
        if self._filter == FILTER_ALL or self._filter == FILTER_TIME:
            return bool(entry.has_git)
        if self._filter == FILTER_NO_GIT:
            return not entry.has_git
        if self._filter == FILTER_NO_REMOTE:
            return bool(entry.has_git and entry.has_origin is False)
        if self._filter == FILTER_DIRTY:
            return bool(entry.has_git and entry.dirty)
        if self._filter == FILTER_RECENT:
            from app.ui.settings_store import load_recent_folders

            try:
                key = str(Path(entry.path).resolve()).lower()
            except OSError:
                return False
            recent = []
            for raw in load_recent_folders():
                try:
                    recent.append(str(Path(raw).resolve()).lower())
                except OSError:
                    continue
            return key in recent[: int(HOME_RECENT_FILTER_CAP)]
        return True

    def _append_list_entry(self, entry: ProjectEntry) -> None:
        """Insert one row while scanning (before trailing stretch / after spinner)."""
        if self._view_timeline or self._filter == FILTER_TIME:
            # Timeline needs buckets — wait for final rebuild.
            return
        if entry.path in self._block_by_path or entry.path in self._row_by_path:
            return
        self._list_layout.insertWidget(
            self._list_layout.count() - 1, self._make_project_block(entry)
        )

    def _rebuild_list(self) -> None:
        keep_spin = self._scanning
        self._clear_list_rows(keep_spinner=keep_spin)
        if keep_spin:
            self._show_list_spinner(True)
        rows = self._filtered()
        hc = self._hc
        if not rows:
            if self._scanning:
                return  # spinner already visible; avoid empty-state flash
            # Dirty empty: not in 시안 — app-specific (enrich budget). Others = L200–201.
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(24, 70, 24, 24)
            wl.setSpacing(11)
            wl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            if self._filter == FILTER_DIRTY:
                t = QLabel("확인된 안 올린 변경이 없어요")
                t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                t.setStyleSheet(
                    f"font-size: 14px; font-weight: 600; color: {hc.text_secondary};"
                )
                b = QLabel(
                    "최근 활동 폴더만 먼저 살펴봅니다.\n"
                    "다른 폴더를 누르면 그곳 변경도 확인합니다."
                )
            elif self._filter == FILTER_NO_REMOTE:
                t = QLabel("원격 없는 Git이 없어요")
                t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                t.setStyleSheet(
                    f"font-size: 14px; font-weight: 600; color: {hc.text_secondary};"
                )
                b = QLabel(
                    "로컬에만 있는 Git 저장소가 여기 모입니다.\n"
                    "origin이 없는 폴더를 찾으면 이 목록에 나타납니다."
                )
            else:
                t = QLabel("찾는 폴더가 없어요")
                t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                t.setStyleSheet(
                    f"font-size: 14px; font-weight: 600; color: {hc.text_secondary};"
                )
                b = QLabel(
                    "이름을 다르게 적어 보시거나, "
                    "왼쪽 아래 찾을 위치 추가로 폴더를 알려 주세요."
                )
            b.setWordWrap(True)
            b.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            b.setMaximumWidth(300)
            b.setStyleSheet(
                f"font-size: 12.5px; color: {hc.text_muted}; line-height: 1.65;"
            )
            wl.addWidget(t)
            wl.addWidget(b)
            self._list_layout.insertWidget(
                self._list_layout.count() - 1, wrap
            )
            return
        if self._view_timeline or self._filter == FILTER_TIME:
            self._rebuild_timeline(rows)
        else:
            for entry in rows:
                self._list_layout.insertWidget(
                    self._list_layout.count() - 1, self._make_project_block(entry)
                )
            self._ensure_row_spin()

    def _rebuild_timeline(self, rows: list[ProjectEntry]) -> None:
        hc = self._hc
        for label, items in group_by_time_bucket(rows):
            title = QLabel(label)
            title.setStyleSheet(
                f"padding: 13px 16px 7px; font-size: 11.5px; font-weight: 600; "
                f"color: {hc.text_muted};"
            )
            self._list_layout.insertWidget(self._list_layout.count() - 1, title)
            for entry in items:
                self._list_layout.insertWidget(
                    self._list_layout.count() - 1, self._make_timeline_row(entry)
                )

    def _make_timeline_row(self, entry: ProjectEntry) -> QWidget:
        hc = self._hc
        row = QFrame()
        row.setObjectName("homeTimelineRow")
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        selected = (
            self._selected is not None and self._selected.path == entry.path
        )
        bg = hc.row_selected if selected else "transparent"
        row.setStyleSheet(
            f"QFrame#homeTimelineRow {{ background: {bg}; "
            f"border-bottom: 1px solid {hc.border_soft}; }}"
            f"QFrame#homeTimelineRow:hover {{ background: {hc.row_hover}; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)
        clock = QLabel(format_clock(entry.last_mtime))
        clock.setFixedWidth(52)
        clock.setStyleSheet(
            f"font-size: 11.5px; color: {hc.text_muted}; font-family: {HOME_FONT_MONO};"
        )
        lay.addWidget(clock, 0)
        name = QLabel(entry.name)
        name.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {hc.text};"
        )
        lay.addWidget(name, 0)
        what = QLabel(
            "변경 있음"
            if entry.dirty
            else ("Git 없음" if not entry.has_git else format_relative_mtime(entry.last_mtime))
        )
        what.setStyleSheet(f"font-size: 12px; color: {hc.text_muted};")
        lay.addWidget(what, 1)
        if entry.dirty:
            flag = QLabel("안 올림")
            flag.setStyleSheet(
                f"padding: 2px 8px; border-radius: 999px; font-size: 10.5px; "
                f"font-weight: 600; background: {hc.badge_warn_bg}; color: {hc.badge_warn_fg};"
            )
            lay.addWidget(flag, 0)
        row.mousePressEvent = (  # type: ignore[method-assign]
            lambda _ev, e=entry: self._select_entry(e)
        )
        self._timeline_row_by_path[entry.path] = row
        return row

    def _dirty_label(self, entry: ProjectEntry) -> tuple[str, str]:
        hc = self._hc
        if not entry.has_git:
            return "Git 없음", hc.text_muted
        if entry.dirty and entry.dirty_count > 0:
            return f"파일 {entry.dirty_count}개", hc.warn_text
        if entry.dirty:
            return "변경 있음", hc.warn_text
        if entry.dirty is False:
            return "없음", hc.text_muted
        return "—", hc.text_muted

    def _make_project_block(self, entry: ProjectEntry) -> QWidget:
        """Parent row + optional expanded sub-rows (same 4-col widths)."""
        hc = self._hc
        block = QFrame()
        block.setObjectName("homeProjectBlock")
        block.setStyleSheet(
            f"QFrame#homeProjectBlock {{ border-bottom: 1px solid {hc.border_soft}; }}"
        )
        v = QVBoxLayout(block)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._make_parent_row(entry))
        if entry.path in self._expanded:
            v.addWidget(self._make_expand_panel(entry))
        self._block_by_path[entry.path] = block
        return block

    def _make_parent_row(self, entry: ProjectEntry) -> QWidget:
        hc = self._hc
        row = QFrame()
        row.setObjectName("homeProjectRow")
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        selected = (
            self._selected is not None and self._selected.path == entry.path
        )
        # Only the row paints bg + :hover. Children stay transparent so hover
        # never leaves a nested whiter strip (name_host / twist / folder).
        base_bg = hc.row_selected if selected else hc.bg_window
        row.setStyleSheet(
            f"QFrame#homeProjectRow {{ background: {base_bg}; border: none; }}"
            f"QFrame#homeProjectRow:hover {{ background: {hc.row_hover}; }}"
            f"QFrame#homeProjectRow QWidget#homeNameHost {{"
            f" background: transparent; border: none; }}"
            f"QFrame#homeProjectRow QPushButton#homeTwist {{"
            f" border: none; background: transparent; padding: 0; }}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        name_wrap = QHBoxLayout()
        name_wrap.setContentsMargins(0, 0, 0, 0)
        name_wrap.setSpacing(8)
        # 시안 L146/502–504: ▶ / ▼ text
        # Do NOT walk the FS here — list_recent_child_paths is ~50–80ms/row and
        # was making every click rebuild cost hundreds of ms.
        has_subs = self._twist_active_hint(entry)
        expanded = entry.path in self._expanded
        twist_fg = hc.text_muted if (has_subs or expanded) else "transparent"
        twist = QPushButton(
            GLYPH_TWIST_OPEN if expanded else GLYPH_TWIST_CLOSED
        )
        twist.setObjectName("homeTwist")
        twist.setFixedSize(14, 16)
        twist.setFlat(True)
        twist.setCursor(
            Qt.CursorShape.PointingHandCursor
            if has_subs or expanded
            else Qt.CursorShape.ArrowCursor
        )
        _apply_glyph_font(twist)
        twist.setStyleSheet(
            f"QPushButton#homeTwist {{ border: none; background: transparent;"
            f" padding: 0; color: {twist_fg}; font-size: 10px; }}"
        )
        if has_subs or expanded:
            twist.clicked.connect(
                lambda _checked=False, ent=entry: self._toggle_expand(ent)
            )
        else:
            twist.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
        folder = FolderGlyph(
            has_git=entry.has_git,
            large=False,
            colors=hc,
            fill_bg=None,
        )
        name_wrap.addWidget(twist, 0, Qt.AlignmentFlag.AlignVCenter)
        name_wrap.addWidget(folder, 0)
        name = QLabel(entry.name)
        name.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {hc.text};"
            f" background: transparent;"
        )
        name_wrap.addWidget(name, 0)
        if not entry.has_git:
            badge = QLabel("Git 없음")
            badge.setStyleSheet(
                f"padding: 2px 8px; border-radius: 999px; font-size: 10.5px;"
                f" background: {hc.badge_nogit_bg}; color: {hc.badge_nogit_fg};"
            )
            name_wrap.addWidget(badge, 0)
        elif entry.has_origin is False:
            badge = QLabel("원격 없음")
            badge.setStyleSheet(
                f"padding: 2px 8px; border-radius: 999px; font-size: 10.5px;"
                f" background: {hc.badge_nogit_bg}; color: {hc.badge_nogit_fg};"
            )
            name_wrap.addWidget(badge, 0)
        name_wrap.addStretch(1)
        name_host = QWidget()
        name_host.setObjectName("homeNameHost")
        name_host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        name_host.setAutoFillBackground(False)
        name_host.setStyleSheet(
            "QWidget#homeNameHost { background: transparent; border: none; }"
        )
        name_host.setLayout(name_wrap)
        lay.addWidget(name_host, 1)

        when = QLabel(format_relative_mtime(entry.last_mtime))
        when.setFixedWidth(int(HOME_COL_TIME))
        when.setStyleSheet(
            f"font-size: 12px; color: {hc.text_secondary}; font-family: {HOME_FONT_MONO};"
            f" background: transparent;"
        )
        lay.addWidget(when, 0)

        dirty_t, dirty_c = self._dirty_label(entry)
        if entry.has_git and entry.dirty is None:
            dirty_t, dirty_c = f"{_SPIN_FRAMES[0]} …", hc.text_muted
        dirty = QLabel(dirty_t if entry.has_git else "—")
        dirty.setFixedWidth(int(HOME_COL_DIRTY))
        dirty.setStyleSheet(
            f"font-size: 12px; color: {dirty_c if entry.has_git else hc.text_muted}; "
            f"font-weight: {'600' if entry.dirty else '400'}; background: transparent;"
        )
        lay.addWidget(dirty, 0)

        branch = QLabel((entry.branch or "—") if entry.has_git else "—")
        branch.setFixedWidth(int(HOME_COL_BRANCH))
        branch.setStyleSheet(
            f"font-size: 12px; color: {hc.text_muted}; font-family: {HOME_FONT_MONO};"
            f" background: transparent;"
        )
        lay.addWidget(branch, 0)

        row.mousePressEvent = (  # type: ignore[method-assign]
            lambda _ev, e=entry: self._select_entry(e)
        )
        self._row_by_path[entry.path] = row
        self._dirty_lab_by_path[entry.path] = dirty
        self._branch_lab_by_path[entry.path] = branch
        self._twist_by_path[entry.path] = twist
        return row

    def _make_expand_panel(self, entry: ProjectEntry) -> QWidget:
        """Sub-rows share parent column widths; indent only in column 1."""
        hc = self._hc
        panel = QFrame()
        panel.setStyleSheet(f"background: {hc.bg_subrow};")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 4, 0, 12)
        pv.setSpacing(2)
        cap = QLabel("이 안에서 최근에 손댄 곳")
        cap.setStyleSheet(
            f"padding: 4px 16px 6px 54px; font-size: 11px; color: {hc.text_muted};"
        )
        pv.addWidget(cap)
        subs = self._subs_for(entry)
        if not subs:
            empty = QLabel("최근에 손댄 하위 경로가 없습니다.")
            empty.setStyleSheet(
                f"padding: 4px 16px 4px 54px; font-size: 11.5px; color: {hc.text_faint};"
            )
            pv.addWidget(empty)
            return panel
        for hit in subs:
            pv.addWidget(self._make_sub_row(hit))
        return panel

    def _make_sub_row(self, hit: SubPathHit) -> QWidget:
        hc = self._hc
        row = QFrame()
        lay = QHBoxLayout(row)
        # Same padding/gap as parent so 118/108/92 columns line up
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(12)
        name_host = QWidget()
        nh = QHBoxLayout(name_host)
        nh.setContentsMargins(38, 0, 0, 0)  # indent inside col 1 only
        nh.setSpacing(8)
        path_l = QLabel(display_path(hit.rel_path))
        path_l.setStyleSheet(
            f"font-size: 12px; color: {hc.text_secondary}; "
            f"font-family: {HOME_FONT_MONO};"
        )
        nh.addWidget(path_l, 1)
        lay.addWidget(name_host, 1)
        when = QLabel(format_relative_mtime(hit.mtime))
        when.setFixedWidth(int(HOME_COL_TIME))
        when.setStyleSheet(
            f"font-size: 11.5px; color: {hc.text_muted};"
        )
        lay.addWidget(when, 0)
        # Empty placeholders keep the 4-column alignment
        spacer_a = QWidget()
        spacer_a.setFixedWidth(int(HOME_COL_DIRTY))
        spacer_b = QWidget()
        spacer_b.setFixedWidth(int(HOME_COL_BRANCH))
        lay.addWidget(spacer_a, 0)
        lay.addWidget(spacer_b, 0)
        return row

    def _twist_active_hint(self, entry: ProjectEntry) -> bool:
        """Whether to show an active ▶ without walking the disk."""
        cached = self._subs_cache.get(entry.path)
        if cached is not None:
            return bool(cached)
        # Optimistic: show twist; expand walks FS once.
        return True

    def _subs_for(self, entry: ProjectEntry) -> list[SubPathHit]:
        cached = self._subs_cache.get(entry.path)
        if cached is not None:
            return cached
        hits = list_recent_child_paths(entry.path, limit=8, max_depth=2)
        self._subs_cache[entry.path] = hits
        return hits

    def _row_selected_style(self, *, selected: bool, timeline: bool) -> str:
        hc = self._hc
        if timeline:
            bg = hc.row_selected if selected else "transparent"
            return (
                f"QFrame#homeTimelineRow {{ background: {bg}; "
                f"border-bottom: 1px solid {hc.border_soft}; }}"
                f"QFrame#homeTimelineRow:hover {{ background: {hc.row_hover}; }}"
            )
        base_bg = hc.row_selected if selected else hc.bg_window
        return (
            f"QFrame#homeProjectRow {{ background: {base_bg}; border: none; }}"
            f"QFrame#homeProjectRow:hover {{ background: {hc.row_hover}; }}"
            f"QFrame#homeProjectRow QWidget#homeNameHost {{"
            f" background: transparent; border: none; }}"
            f"QFrame#homeProjectRow QPushButton#homeTwist {{"
            f" border: none; background: transparent; padding: 0; }}"
        )

    def _paint_path_selected(self, path: str, selected: bool) -> None:
        row = self._row_by_path.get(path)
        if row is not None:
            row.setStyleSheet(
                self._row_selected_style(selected=selected, timeline=False)
            )
            return
        trow = self._timeline_row_by_path.get(path)
        if trow is not None:
            trow.setStyleSheet(
                self._row_selected_style(selected=selected, timeline=True)
            )

    def _patch_row_dirty(self, entry: ProjectEntry) -> None:
        """Update dirty/branch labels in place (no list rebuild)."""
        hc = self._hc
        dirty_lab = self._dirty_lab_by_path.get(entry.path)
        if dirty_lab is not None:
            dirty_t, dirty_c = self._dirty_label(entry)
            if entry.has_git and entry.dirty is None:
                dirty_t, dirty_c = f"{_SPIN_FRAMES[0]} …", hc.text_muted
            dirty_lab.setText(dirty_t if entry.has_git else "—")
            dirty_lab.setStyleSheet(
                f"font-size: 12px; color: {dirty_c if entry.has_git else hc.text_muted}; "
                f"font-weight: {'600' if entry.dirty else '400'}; background: transparent;"
            )
        branch_lab = self._branch_lab_by_path.get(entry.path)
        if branch_lab is not None:
            branch_lab.setText(
                (entry.branch or "—") if entry.has_git else "—"
            )

    def _toggle_expand(self, entry: ProjectEntry) -> None:
        expanding = entry.path not in self._expanded
        if expanding:
            self._expanded.add(entry.path)
            self._subs_for(entry)  # FS walk only when user expands
        else:
            self._expanded.discard(entry.path)

        block = self._block_by_path.get(entry.path)
        if block is not None:
            lay = block.layout()
            if lay is not None:
                while lay.count() > 1:
                    item = lay.takeAt(1)
                    w = item.widget() if item is not None else None
                    if w is not None:
                        w.hide()
                        w.setParent(None)
                        w.deleteLater()
                if expanding:
                    lay.addWidget(self._make_expand_panel(entry))
            twist = self._twist_by_path.get(entry.path)
            if twist is not None:
                twist.setText(
                    GLYPH_TWIST_OPEN if expanding else GLYPH_TWIST_CLOSED
                )
        else:
            # Timeline / missing handle — fall back
            prev = self._selected
            self._selected = entry
            self._rebuild_list()
            self._apply_detail(entry)
            if entry.has_git and self._needs_dirty_probe(entry.path):
                self._schedule_select_probe(entry.path)
            return

        prev_path = self._selected.path if self._selected is not None else None
        self._selected = entry
        if prev_path and prev_path != entry.path:
            self._paint_path_selected(prev_path, False)
        self._paint_path_selected(entry.path, True)
        self._apply_detail(entry)
        if entry.has_git and self._needs_dirty_probe(entry.path):
            self._schedule_select_probe(entry.path)

    def _select_entry(self, entry: ProjectEntry) -> None:
        same = (
            self._selected is not None and self._selected.path == entry.path
        )
        prev_path = self._selected.path if self._selected is not None else None
        self._selected = entry
        if not same:
            # Style-only — never rebuild the whole list on click.
            if prev_path:
                self._paint_path_selected(prev_path, False)
            self._paint_path_selected(entry.path, True)
        self._apply_detail(entry)
        if entry.has_git and self._needs_dirty_probe(entry.path):
            self._schedule_select_probe(entry.path)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                # Immediate detach — avoid deleteLater ghost FactRow borders (noPick bars)
                layout.removeWidget(w)
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _clear_detail_nopick(self) -> None:
        """시안 noPick (L243): 선택 없을 때 우패널 안내."""
        hc = self._hc
        self._show_detail_spinner(False)
        self._detail_icon.hide()
        self._detail_subtitle.hide()
        if hasattr(self, "_path_actions"):
            self._path_actions.clear_actions()
            self._path_actions.hide()
        self._clear_layout(self._facts_layout)
        if hasattr(self, "_note_wrap"):
            self._note_wrap.hide()
        self._note_label.hide()
        self._clear_layout(self._cta_layout)
        self._cta_action_ids = []
        self._fit_detail_typography(
            title="폴더를 하나 고르면 여기에서 바로 올리고 받을 수 있습니다.",
            title_muted=True,
        )

    def _apply_detail(self, entry: ProjectEntry) -> None:
        hc = self._hc
        self._detail_icon.set_colors(hc)
        self._detail_icon.set_fill_bg(hc.bg_detail)
        self._detail_icon.set_has_git(entry.has_git)
        self._detail_icon.show()
        self._detail_title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {hc.text};"
        )
        login = load_last_github_login() if is_logged_in() else None
        if entry.has_git:
            # Known no-origin: skip network meta (nothing to look up).
            if entry.has_origin is False:
                self._show_detail_spinner(False)
                self._paint_detail(entry, None)
                return
            cached = self._meta_cache.get(entry.path)
            if cached is not None:
                self._show_detail_spinner(False)
                self._paint_detail(entry, cached)
            else:
                # Instant paint — git+HTTP (~0.3–1.3s) run on _MetaWorker
                self._show_detail_spinner(True, "GitHub 정보를 확인하는 중…")
                self._paint_detail(entry, None, meta_pending=True)
                self._schedule_meta_network(entry.path, login)
        else:
            self._show_detail_spinner(False)
            self._paint_detail(entry, None)

    def _paint_detail(
        self,
        entry: ProjectEntry,
        meta: object | None,
        *,
        meta_pending: bool = False,
    ) -> None:
        hc = self._hc
        is_mine = True
        has_origin = entry.has_origin
        if meta is not None:
            m_mine = getattr(meta, "is_mine", None)
            owner = (getattr(meta, "owner", None) or "").strip()
            login = ""
            if is_logged_in():
                login = (load_last_github_login() or "").strip()
            # Prefer explicit meta; if unset, owner≠login ⇒ not mine (시안).
            if m_mine is False:
                is_mine = False
            elif m_mine is True:
                is_mine = True
            elif login and owner and owner.lower() != login.lower():
                is_mine = False
            else:
                is_mine = True
            origin_disp = (getattr(meta, "origin_display", None) or "").strip()
            if origin_disp and origin_disp != "—":
                has_origin = True
            elif origin_disp == "—" or not origin_disp:
                # Meta resolved with no remote URL
                if getattr(meta, "owner", "") == "" and getattr(meta, "repo", "") == "":
                    has_origin = False
        plan = build_cta_plan(
            has_git=entry.has_git,
            is_mine=is_mine,
            dirty=bool(entry.dirty) if entry.dirty is not None else False,
            signed_in=is_logged_in(),
            has_origin=has_origin,
        )
        from app.ui.text_fit import detail_fact_value_width

        fact_vw = detail_fact_value_width(int(HOME_DETAIL_W), pad_x=16)
        # Title row path actions (same box, side by side) — not fact rows
        remote = ""
        visibility = "—"
        if entry.has_git:
            if has_origin is False:
                remote = "연결 안 됨"
                visibility = "—"
            elif meta is not None:
                remote = getattr(meta, "origin_display", None) or "—"
                visibility = getattr(meta, "visibility", None) or "—"
            elif meta_pending:
                remote = f"{_SPIN_FRAMES[0]} 확인 중…"
                visibility = f"{_SPIN_FRAMES[0]} 확인 중…"
            else:
                remote = "—"
                visibility = "—"
            if is_mine is False:
                vis = (visibility or "").strip()
                if not vis or vis == "—":
                    visibility = "남의 저장소"
                elif "남의" not in vis:
                    visibility = f"{vis} · 남의 저장소"

        gh_url = github_browse_url(str(remote)) if entry.has_git else None
        self._path_actions.set_actions(
            folder_path=entry.path,
            folder_tip=display_path(entry.path),
            github_url=gh_url,
            github_tip=str(remote) if gh_url else "",
            colors=hc,
        )

        self._clear_layout(self._facts_layout)
        self._facts_layout.addWidget(
            FactRow(
                "마지막 작업",
                format_relative_mtime(entry.last_mtime),
                colors=hc,
                value_max_width=fact_vw,
            )
        )
        if entry.has_git:
            dirty_val = "—"
            dirty_fg = hc.text_secondary
            dirty_w = 400
            if entry.dirty and entry.dirty_count > 0:
                dirty_val = f"파일 {entry.dirty_count}개"
                dirty_fg = hc.warn_text
                dirty_w = 600
            elif entry.dirty:
                dirty_val = "있음"
                dirty_fg = hc.warn_text
                dirty_w = 600
            elif entry.dirty is False:
                dirty_val = "없음"
            elif entry.dirty is None:
                dirty_val = f"{_SPIN_FRAMES[0]} 확인 중…"
                dirty_fg = hc.text_muted
            self._facts_layout.addWidget(
                FactRow(
                    "공개 범위",
                    visibility,
                    colors=hc,
                    value_max_width=fact_vw,
                )
            )
            self._facts_layout.addWidget(
                FactRow(
                    "안 올린 변경",
                    dirty_val,
                    value_color=dirty_fg,
                    value_weight=dirty_w,
                    colors=hc,
                    value_max_width=fact_vw,
                )
            )

        if plan.note:
            self._note_wrap.setStyleSheet(
                f"QWidget#homeDetailNoteWrap {{ background-color: {hc.bg_warn_note};"
                f" border-radius: 8px; }}"
            )
            self._note_label.show()
            self._note_wrap.show()
        else:
            self._note_label.hide()
            self._note_wrap.hide()

        self._rebuild_cta_buttons(plan)
        self._fit_detail_typography(
            title=entry.name,
            subtitle=plan.subtitle,
            note=plan.note if plan.note else "",
        )
        self._update_breadcrumb()

    def _fit_detail_typography(
        self,
        *,
        title: str,
        subtitle: str = "",
        note: str = "",
        title_muted: bool = False,
    ) -> None:
        """Shrink title/subtitle/note/CTA; title marquees RTL on hover if still wide."""
        from app.ui.marquee_label import MarqueeLabel
        from app.ui.text_fit import (
            DETAIL_CTA_BASE_PX,
            DETAIL_CTA_MIN_PX,
            DETAIL_NOTE_BASE_PX,
            DETAIL_NOTE_MAX_H,
            DETAIL_NOTE_MIN_PX,
            DETAIL_SUB_BASE_PX,
            DETAIL_SUB_MAX_H,
            DETAIL_SUB_MIN_PX,
            DETAIL_TITLE_BASE_PX,
            DETAIL_TITLE_MAX_H,
            DETAIL_TITLE_MIN_PX,
            apply_fitting_font_box,
            detail_content_width,
            fit_font_px,
        )

        hc = self._hc
        content_w = detail_content_width(int(HOME_DETAIL_W), pad_x=16)
        # Prefer live width if laid out already
        if self._detail_title.width() > 40:
            content_w = float(self._detail_title.width())

        title_color = hc.text_muted if title_muted else hc.text
        title_base = float(DETAIL_TITLE_BASE_PX) if not title_muted else 12.5
        title_min = float(DETAIL_TITLE_MIN_PX) if not title_muted else 10.0
        title_px = fit_font_px(
            title,
            content_w,
            base_px=title_base,
            min_px=title_min,
            bold=not title_muted,
        )
        if isinstance(self._detail_title, MarqueeLabel):
            # Single-line: shrink to floor, then hover marquee if still clipped.
            self._detail_title.set_marquee_text(
                title,
                max_width_px=content_w,
                pixel_size=title_px,
                bold=not title_muted,
                color=title_color,
                align_center=True,
            )
        else:
            apply_fitting_font_box(
                self._detail_title,
                title,
                content_w,
                float(DETAIL_TITLE_MAX_H),
                base_px=title_base,
                min_px=title_min,
                bold=not title_muted,
                color=title_color,
                align_center=True,
            )
            self._detail_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        if subtitle:
            apply_fitting_font_box(
                self._detail_subtitle,
                subtitle,
                content_w,
                float(DETAIL_SUB_MAX_H),
                base_px=float(DETAIL_SUB_BASE_PX),
                min_px=float(DETAIL_SUB_MIN_PX),
                bold=False,
                color=hc.text_muted,
                align_center=True,
            )
            self._detail_subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self._detail_subtitle.show()

        if note and self._note_wrap.isVisible():
            note_w = content_w - 22  # note_l margins 11+11
            apply_fitting_font_box(
                self._note_label,
                note,
                max(60.0, note_w),
                float(DETAIL_NOTE_MAX_H),
                base_px=float(DETAIL_NOTE_BASE_PX),
                min_px=float(DETAIL_NOTE_MIN_PX),
                bold=False,
                color=hc.text_secondary,
            )

        # CTA buttons: shrink label to button width
        btn_w = max(80.0, content_w)
        for i in range(self._cta_layout.count()):
            item = self._cta_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if not isinstance(w, QPushButton):
                continue
            text = w.text()
            if not text:
                continue
            px = fit_font_px(
                text,
                btn_w - 24,
                base_px=float(DETAIL_CTA_BASE_PX),
                min_px=float(DETAIL_CTA_MIN_PX),
                bold=True,
            )
            # Keep existing colors from _style_cta; only nudge font-size via font
            f = w.font()
            f.setPixelSize(max(1, int(round(px))))
            w.setFont(f)
            w.setToolTip(text)

    def _schedule_meta_network(self, path: str, login: str | None) -> None:
        """Fill 공개 범위 / is_mine via GitHub API off the UI thread."""
        if self._meta_worker is not None and self._meta_worker.isRunning():
            self._meta_worker.requestInterruption()
        self._meta_gen += 1
        gen = self._meta_gen
        self._show_detail_spinner(True, "GitHub 정보를 확인하는 중…")
        w = _MetaWorker(path, login, gen, parent=self)
        w.finished_meta.connect(self._on_meta_network_done)
        self._meta_worker = w
        w.start()

    def _on_meta_network_done(
        self, path: str, generation: int, meta: object
    ) -> None:
        if generation != self._meta_gen:
            return
        self._meta_cache[path] = meta
        # Sync has_origin onto the list entry when meta settles.
        origin_disp = (getattr(meta, "origin_display", None) or "").strip()
        confirmed_origin: bool | None
        if origin_disp and origin_disp != "—":
            confirmed_origin = True
        elif getattr(meta, "owner", "") == "" and getattr(meta, "repo", "") == "":
            confirmed_origin = False
        else:
            confirmed_origin = None
        if confirmed_origin is not None:
            updated: list[ProjectEntry] = []
            for e in self._entries:
                if e.path != path:
                    updated.append(e)
                    continue
                if e.has_origin == confirmed_origin:
                    updated.append(e)
                    continue
                updated.append(
                    ProjectEntry(
                        path=e.path,
                        name=e.name,
                        has_git=e.has_git,
                        last_mtime=e.last_mtime,
                        dirty=e.dirty,
                        dirty_count=e.dirty_count,
                        branch=e.branch,
                        has_origin=confirmed_origin,
                    )
                )
            self._entries = updated
            if self._selected is not None and self._selected.path == path:
                self._selected = next(
                    (x for x in self._entries if x.path == path), self._selected
                )
            if self._filter == FILTER_NO_REMOTE:
                self._rebuild_list()
        if self._selected is None or self._selected.path != path:
            self._show_detail_spinner(False)
            return
        self._show_detail_spinner(False)
        # Refresh detail with network-enriched meta (CTA may flip not_mine)
        self._paint_detail(self._selected, meta)

    def _rebuild_cta_buttons(self, plan) -> None:  # noqa: ANN001
        self._clear_layout(self._cta_layout)
        self._cta_action_ids = []
        for i, act in enumerate(plan.actions):
            btn = QPushButton(act.label)
            btn.setMinimumHeight(40 if act.variant == "primary" else 36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_cta(btn, variant=act.variant)
            aid = act.action_id
            btn.clicked.connect(
                lambda _=False, a=aid: self._on_cta(a)
            )
            self._cta_layout.addWidget(btn)
            self._cta_action_ids.append(aid)

    def _open_local_path(self, path: str) -> None:
        """U-10: open folder in OS file manager."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if not path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_cta(self, action_id: CtaActionId) -> None:
        if self._selected is None:
            return
        path = self._selected.path
        if action_id is CtaActionId.HISTORY:
            from app.ui.commit_history_dialog import show_commit_history

            show_commit_history(self.window(), path)
            return
        if action_id is CtaActionId.OPEN_FOLDER:
            self._open_local_path(path)
            return
        if not is_logged_in() and action_id in (
            CtaActionId.PUBLISH_START,
            CtaActionId.PUSH,
            CtaActionId.PULL,
            CtaActionId.FORK_COPY,
        ):
            self._ctrl.on_login()
            return
        # U-9: publish/clone → tab+prefill only; push/pull → controller
        if action_id is CtaActionId.PUBLISH_START:
            self._ctrl.open_workspace_from_home(path, tab_substr="올리기")
            return
        if action_id is CtaActionId.PUSH:
            self._ctrl.open_workspace_from_home(path, tab_substr="동기화")
            QTimer.singleShot(0, lambda: self._ctrl.on_sync_action("push"))
            return
        if action_id is CtaActionId.PULL:
            self._ctrl.open_workspace_from_home(path, tab_substr="동기화")
            QTimer.singleShot(0, lambda: self._ctrl.on_sync_action("pull"))
            return
        if action_id is CtaActionId.FORK_COPY:
            meta = resolve_home_repo_meta(
                path, login=load_last_github_login() if is_logged_in() else None
            )
            self._ctrl.open_workspace_from_home(path, tab_substr="받기")
            if meta.owner and meta.repo and self._ctrl.editCloneUrl is not None:
                url = f"https://github.com/{meta.owner}/{meta.repo}"
                try:
                    self._ctrl.editCloneUrl.setEditText(url)
                except Exception:
                    try:
                        self._ctrl.editCloneUrl.setCurrentText(url)
                    except Exception:
                        pass
            return
        self._ctrl.open_workspace_from_home(path)

    def _add_scan_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "찾을 위치 추가")
        if not path:
            return
        add_scan_root(path)
        self.refresh_projects()

    def _refresh_account(self) -> None:
        """시안 sidebar footer: avatar+name+dot (signed-in) or outline login CTA."""
        from app.ui.home_avatar import (
            AvatarFetchWorker,
            HomeAvatar,
            load_cached_avatar_pixmap,
        )
        from app.ui.settings_store import load_github_avatar_url

        hc = self._hc
        # Clear previous children
        while self._account_host_l.count():
            item = self._account_host_l.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        if is_logged_in():
            login = load_last_github_login() or "GitHub"
            initial = (login[:1] or "s").lower()
            # Painted circle — avoids QLabel stretch → green bar above name
            avatar = HomeAvatar(
                initial=initial, bg=hc.avatar_bg, fg=hc.avatar_fg
            )
            dpr = float(avatar.devicePixelRatioF() or 1.0)
            cached = load_cached_avatar_pixmap(
                login, device_pixel_ratio=dpr
            )
            if cached is not None:
                avatar.set_pixmap(cached)
            name = QLabel(login)
            name.setObjectName("homeAccountName")
            name.setStyleSheet(
                f"QLabel#homeAccountName {{ font-size: 12.5px; color: {hc.text};"
                f" background: transparent; border: none; padding: 0; margin: 0; }}"
            )
            name.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            dot = QLabel()
            dot.setFixedSize(6, 6)
            dot.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            dot.setStyleSheet(
                f"background: {hc.primary}; border-radius: 3px; border: none;"
            )
            self._account_host.setMinimumHeight(35)
            self._account_host.setMaximumHeight(16777215)
            self._account_host_l.setContentsMargins(6, 6, 8, 6)
            self._account_host_l.setSpacing(9)
            self._account_host_l.addWidget(
                avatar, 0, Qt.AlignmentFlag.AlignVCenter
            )
            self._account_host_l.addWidget(
                name, 1, Qt.AlignmentFlag.AlignVCenter
            )
            self._account_host_l.addWidget(
                dot, 0, Qt.AlignmentFlag.AlignVCenter
            )
            self._account_host.setStyleSheet(
                f"QFrame#homeAccountHost {{ border: none; border-radius: 6px;"
                f" background: transparent; }}"
                f"QFrame#homeAccountHost:hover {{ background: {hc.nav_hover}; }}"
            )
            self._account_host.setToolTip(f"{login} · 온라인")
            self._avatar_widget = avatar
            # Background fetch if cache miss but we have a URL
            url = load_github_avatar_url()
            if url and cached is None:
                self._start_avatar_fetch(login, url)
            elif url and cached is not None:
                pass
            elif url is None:
                # Try live user once (token already in keyring)
                self._ensure_avatar_url_async(login)
        else:
            self._avatar_widget = None
            lab = QLabel("GitHub 로그인")
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setStyleSheet(
                f"font-size: 12.5px; font-weight: 600; color: {hc.primary};"
                f" background: transparent;"
            )
            self._account_host_l.setContentsMargins(0, 0, 0, 0)
            self._account_host_l.addWidget(lab, 1)
            self._account_host.setFixedHeight(35)
            self._account_host.setStyleSheet(
                f"QFrame#homeAccountHost {{ border: 1px solid {hc.primary};"
                f" border-radius: 7px; background: {hc.bg_window}; }}"
                f"QFrame#homeAccountHost:hover {{ background: {hc.row_hover}; }}"
            )
            self._account_host.setToolTip("GitHub에 연결")

    def _start_avatar_fetch(self, login: str, url: str) -> None:
        from app.ui.home_avatar import AvatarFetchWorker, load_cached_avatar_pixmap

        old = getattr(self, "_avatar_worker", None)
        if old is not None and old.isRunning():
            return
        w = AvatarFetchWorker(login, url, parent=self)
        w.finished_ok.connect(self._on_avatar_fetched)
        self._avatar_worker = w
        w.start()

    def _on_avatar_fetched(self, login: str, path: str) -> None:
        from app.ui.home_avatar import load_cached_avatar_pixmap

        av = getattr(self, "_avatar_widget", None)
        if av is None:
            return
        cur = load_last_github_login() or ""
        if cur.lower() != (login or "").lower():
            return
        dpr = float(av.devicePixelRatioF() or 1.0)
        pm = load_cached_avatar_pixmap(login, device_pixel_ratio=dpr)
        if pm is not None:
            av.set_pixmap(pm)

    def _ensure_avatar_url_async(self, login: str) -> None:
        """If avatar_url not stored yet, GET /user once and cache photo."""

        class _UserWorker(QThread):
            done = Signal(object)

            def run(self) -> None:  # noqa: N802
                try:
                    from app.auth.token_store import load_token
                    from app.github.api_client import get_authenticated_user
                    from app.ui.home_avatar import persist_avatar_from_user

                    token = load_token()
                    if not token:
                        self.done.emit(None)
                        return
                    user = get_authenticated_user(token, timeout=12)
                    persist_avatar_from_user(user)
                    self.done.emit(user)
                except Exception:  # noqa: BLE001
                    self.done.emit(None)

        def _done(user: object) -> None:
            if not isinstance(user, dict):
                return
            url = str(user.get("avatar_url") or "").strip()
            if url:
                self._start_avatar_fetch(login, url)

        w = _UserWorker(parent=self)
        w.done.connect(_done)
        self._avatar_user_worker = w
        w.start()

    def _on_account_clicked(self) -> None:
        if is_logged_in():
            self._toggle_overflow_panel()
        else:
            self._ctrl.on_login()

    def _toggle_overflow_panel(self) -> None:
        if self._overflow_open:
            self._hide_overflow_panel()
        else:
            self._show_overflow_panel()

    def _hide_overflow_panel(self) -> None:
        self._overflow_open = False
        if self._overflow_panel is not None:
            self._overflow_panel.hide()
        from app.ui.home_chrome import apply_overflow_colors

        apply_overflow_colors(self._overflow, self._hc, menu_open=False)

    def _show_overflow_panel(self) -> None:
        """시안: floating panel above sidebar footer (not OS QMenu)."""
        hc = self._hc
        if self._overflow_panel is None:
            panel = QFrame(self._side)
            panel.setObjectName("homeOverflowPanel")
            self._overflow_panel = panel
        else:
            panel = self._overflow_panel
            # Clear old rows
            lay0 = panel.layout()
            if lay0 is not None:
                while lay0.count():
                    it = lay0.takeAt(0)
                    w = it.widget()
                    if w is not None:
                        w.hide()
                        w.setParent(None)
                        w.deleteLater()

        panel.setStyleSheet(
            f"QFrame#homeOverflowPanel {{ background: {hc.bg_window};"
            f" border: 1px solid {hc.border}; border-radius: 9px; }}"
        )
        lay = panel.layout()
        if lay is None:
            lay = QVBoxLayout(panel)
        lay.setContentsMargins(5, 5, 5, 5)
        lay.setSpacing(0)

        # Panel width first so we can fit label fonts (시안 sidebar 206 − 16).
        from app.ui.home_tokens import HOME_SIDEBAR_W
        from app.ui.text_fit import apply_fitting_font, measure_text_width_px

        side_w = self._side.width() if self._side.width() > 0 else int(HOME_SIDEBAR_W)
        pw = max(120, side_w - 16)
        # row pad 8+8 (시안 8px 10px → use 8); 0.92 = Malgun/Plex wider than metrics pad
        base_label_budget = float(pw - 16) * 0.92

        def _add_item(
            label: str,
            *,
            fg: str,
            hint: str = "",
            on_click=None,
            danger: bool = False,
        ) -> None:
            row = QFrame()
            row.setObjectName("homeOverflowItem")
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 8, 8, 8)
            rl.setSpacing(8)
            lab = QLabel()
            hint_w = 0.0
            if hint:
                hint_w = measure_text_width_px(hint, 11.0) + 8.0
            budget = max(48.0, base_label_budget - hint_w)
            apply_fitting_font(
                lab, label, budget, base_px=12.5, min_px=9.0, color=fg
            )
            lab.setWordWrap(False)
            lab.setToolTip(label)
            rl.addWidget(lab, 1)
            if hint:
                h = QLabel()
                apply_fitting_font(
                    h,
                    hint,
                    max(32.0, min(80.0, hint_w)),
                    base_px=11.0,
                    min_px=9.0,
                    color=hc.text_muted,
                    extra_css=f"font-family: {HOME_FONT_MONO};",
                )
                h.setToolTip(hint)
                rl.addWidget(h, 0)

            def _go(_ev=None, cb=on_click) -> None:
                self._hide_overflow_panel()
                if cb is not None:
                    cb()

            row.mousePressEvent = _go  # type: ignore[method-assign]
            row.setStyleSheet(
                f"QFrame#homeOverflowItem {{ border-radius: 6px;"
                f" background: transparent; }}"
                f"QFrame#homeOverflowItem:hover {{ background: {hc.menu_hover}; }}"
            )
            lay.addWidget(row)

        def _rule() -> None:
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background: {hc.border_soft}; margin: 4px 6px;")
            lay.addWidget(line)

        _add_item("설정", fg=hc.text, on_click=self._ctrl.on_settings_menu)
        _add_item(
            "도움말 · 시작 안내",
            fg=hc.text,
            on_click=self._ctrl.on_help_onboarding,
        )
        _add_item(
            "이용약관",
            fg=hc.text,
            on_click=self._ctrl._open_terms_from_chrome,
        )
        _rule()
        if getattr(self._ctrl, "_git_ok", True):
            raw = getattr(self._ctrl, "_git_version_label", "") or ""
            ver = str(raw).strip() or "확인됨"
            _add_item("Git", fg=hc.text_secondary, hint=ver, on_click=None)
        else:
            _add_item(
                "Git  없음 — 설치 방법…",
                fg=hc.text_secondary,
                on_click=self._ctrl._on_git_banner_install,
            )
        _rule()
        if is_logged_in():
            _add_item(
                "로그아웃",
                fg=hc.danger,
                on_click=self._ctrl.on_logout,
                danger=True,
            )
        else:
            _add_item(
                "GitHub 로그인",
                fg=hc.primary,
                on_click=self._ctrl.on_login,
            )

        panel.setFixedWidth(pw)
        panel.adjustSize()
        # Place above footer: left/right 8px, bottom = foot height + 8
        foot_h = self._side_foot.height() if self._side_foot else 52
        ph = panel.sizeHint().height()
        panel.setGeometry(8, max(8, self._side.height() - foot_h - 8 - ph), pw, ph)
        panel.raise_()
        panel.show()
        self._overflow_open = True
        # 시안 menuBg = nav_selected (warm gray), never primary green
        from app.ui.home_chrome import OverflowMenuButton, apply_overflow_colors

        apply_overflow_colors(self._overflow, hc, menu_open=True)
        if isinstance(self._overflow, OverflowMenuButton):
            self._overflow.set_menu_open(True)

    def _sync_git_banner(self) -> None:
        # Do NOT call ``_refresh_status_bar`` here — that calls
        # ``sync_from_controller`` again (infinite recursion) and also
        # touches deleted legacy status-bar widgets.
        ok = bool(getattr(self._ctrl, "_git_ok", True))
        self._git_banner.setVisible(not ok)

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

    home.open_workspace.connect(
        lambda folder: controller.open_workspace_from_home(folder)
    )
    # Phase B: drop legacy status-bar chrome widgets (A only hid them).
    # Clear controller refs — otherwise ``_refresh_status_bar`` / busy helpers
    # keep dangling shiboken wrappers and crash on setText/isVisible.
    attr_by_name = {
        "btnSettings": "btnSettings",
        "btnHelpOnboarding": "btnHelpOnboarding",
        "btnLogout": "btnLogout",
        "labelStatusGit": "labelStatusGit",
    }
    for name, attr in attr_by_name.items():
        w = window.findChild(QWidget, name)
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        if hasattr(controller, attr):
            setattr(controller, attr, None)
    # Phase A overflow on the legacy status row — keep for workspace page.
    return home


def ensure_home_back_button(controller: MainController, stack: QStackedWidget) -> None:
    """Add 「← 홈」 on the legacy status row once."""
    if getattr(controller, "_home_back_btn", None) is not None:
        return
    status = controller.window.findChild(QWidget, "statusBarFrame")
    lay = status.layout() if status is not None else None
    if not isinstance(lay, QHBoxLayout):
        return
    # statusBarFrame min-height is 36 with 6+6 margins → ~24px content.
    # Extra vertical padding on the button was clipping 「← 홈」 glyphs.
    if status is not None and status.minimumHeight() < 40:
        status.setMinimumHeight(40)
    lay.setContentsMargins(
        max(lay.contentsMargins().left(), 12),
        4,
        max(lay.contentsMargins().right(), 12),
        4,
    )
    btn = QPushButton("← 홈")
    btn.setObjectName("btnBackToHome")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFlat(True)
    btn.setMinimumHeight(28)
    btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
    hc = home_chrome_colors()
    btn.setStyleSheet(
        f"QPushButton#btnBackToHome {{ color: {hc.primary}; font-size: 12.5px;"
        f" font-weight: 600; border: none; background: transparent;"
        f" padding: 2px 10px; margin: 0; }}"
        f"QPushButton#btnBackToHome:hover {{ color: {hc.primary_hover}; }}"
    )

    def _back() -> None:
        stack.setCurrentIndex(0)
        shell = getattr(controller, "_home_shell", None)
        if shell is not None:
            shell.sync_from_controller()
            shell.refresh_projects()

    btn.clicked.connect(_back)
    lay.insertWidget(0, btn, 0, Qt.AlignmentFlag.AlignVCenter)
    controller._home_back_btn = btn
