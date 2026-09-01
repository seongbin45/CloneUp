"""Boot toast: unpushed changes (시안 ``desin/CloneUp 시작 알림.dc.html``).

Layout matches the design (382px, radius 10, header/body/buttons). Colors
follow ``active_palette()`` so OS dark mode is detected like the rest of the app.
"""

from __future__ import annotations

from enum import IntEnum

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.boot_scan import PendingFolder
from app.ui.icons import load_app_icon
from app.ui.theme import active_palette

# 시안 geometry (colors come from active_palette)
_RADIUS_CARD = 10
_RADIUS_INNER = 9
# Kind-badge glyph on saturated M/A/D tones — always light cream.
_KIND_FG = "#fbfaf8"


class BootNotifyScene(IntEnum):
    ONE = 0
    MANY = 1
    WAIT = 2
    QUIET = 3


def _toast_qss() -> str:
    """시안 layout + ``active_palette()`` colors (light/dark)."""
    p = active_palette()
    r = _RADIUS_CARD
    ri = _RADIUS_INNER
    return f"""
    QWidget#bootToastShell {{
        background: transparent;
    }}
    QFrame#bootToastCard {{
        background: {p.bg_window};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: {r}px;
    }}
    QFrame#bootToastHead {{
        background: {p.bg_bar};
        border: none;
        border-bottom: 1px solid {p.border_soft};
        border-top-left-radius: {r}px;
        border-top-right-radius: {r}px;
    }}
    QLabel#bootToastBrand {{
        font-size: 11.5px; font-weight: 600; color: {p.text};
        background: transparent; border: none;
    }}
    QLabel#bootToastStamp {{
        font-size: 11.5px; color: {p.text_muted};
        background: transparent; border: none;
    }}
    QPushButton#bootToastX {{
        background: transparent; color: {p.text_muted}; border: none;
        font-size: 14px; padding: 0 4px; min-width: 22px;
    }}
    QPushButton#bootToastX:hover {{ color: {p.text}; }}
    QLabel#bootToastTitle {{
        font-size: 15.5px; font-weight: 600; color: {p.text};
        background: transparent; border: none;
        letter-spacing: -0.01em;
    }}
    QLabel#bootToastLead {{
        font-size: 12.5px; color: {p.text_secondary}; background: transparent; border: none;
    }}
    QFrame#bootToastPanel {{
        background: {p.bg_bar}; border: none; border-radius: {ri}px;
    }}
    QLabel#bootToastMono {{
        font-size: 12.5px; font-weight: 500; color: {p.text};
        font-family: "IBM Plex Mono", Consolas, monospace;
        background: transparent; border: none;
    }}
    QLabel#bootToastMeta {{
        font-size: 11.5px; color: {p.text_muted};
        background: transparent; border: none;
    }}
    QLabel#bootToastFile {{
        font-size: 11.5px; color: {p.text_secondary};
        font-family: "IBM Plex Mono", Consolas, monospace;
        background: transparent; border: none;
    }}
    QLabel#bootToastKind {{
        font-size: 9px; font-weight: 600; color: {_KIND_FG};
        font-family: "IBM Plex Mono", Consolas, monospace;
        border-radius: 3px;
    }}
    QLineEdit#bootToastMsg {{
        background: {p.bg_input}; color: {p.text};
        border: 1px solid {p.border_input}; border-radius: 7px;
        padding: 0 11px; min-height: 34px; font-size: 12.5px;
    }}
    QPushButton#bootToastPrimary {{
        background: {p.primary}; color: {p.text_on_primary}; border: 1px solid {p.primary};
        border-radius: {ri}px; font-size: 13px; font-weight: 600;
        min-height: 38px; padding: 0 16px;
    }}
    QPushButton#bootToastPrimary:hover {{ background: {p.primary_hover}; }}
    QPushButton#bootToastPrimary:disabled {{
        background: {p.bg_muted}; color: {p.text_disabled}; border: 1px solid {p.border_soft};
    }}
    QPushButton#bootToastNormal {{
        background: {p.bg_input}; color: {p.text};
        border: 1px solid {p.border_outline};
        border-radius: {ri}px; font-size: 13px; font-weight: 500;
        min-height: 38px; padding: 0 16px;
    }}
    QPushButton#bootToastQuiet {{
        background: {p.bg_muted}; color: {p.text_secondary};
        border: 1px solid {p.border_input};
        border-radius: {ri}px; font-size: 13px; font-weight: 400;
        min-height: 38px; padding: 0 16px;
    }}
    QPushButton#bootToastLink {{
        background: transparent; color: {p.text_muted}; border: none;
        font-size: 11.5px; text-align: left; padding: 0;
    }}
    QPushButton#bootToastLink:hover {{ color: {p.text}; }}
    QCheckBox#bootToastFolder {{
        spacing: 10px; font-size: 12.5px; color: {p.text};
        font-family: "IBM Plex Mono", Consolas, monospace;
        padding: 11px 13px; background: {p.bg_window};
        border: 1px solid transparent; border-radius: {ri}px;
    }}
    QCheckBox#bootToastFolder:checked {{
        border: 1px solid {p.primary}; background: {p.bg_window};
    }}
    """


class BootNotifyToast(QWidget):
    """Frameless bottom-right toast — 시안 floating card (382px, radius 10)."""

    upload_requested = Signal(list, str)  # folder paths, commit message
    later_clicked = Signal()
    open_app_requested = Signal(str)  # folder path or ""
    snooze_week_requested = Signal()
    disable_requested = Signal()
    dismissed = Signal()

    def __init__(
        self,
        pending: list[PendingFolder],
        *,
        default_message: str = "Update",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pending = list(pending)
        self._picked: dict[str, bool] = {p.path: True for p in self._pending}
        self._scene = (
            BootNotifyScene.ONE
            if len(self._pending) <= 1
            else BootNotifyScene.MANY
        )
        self._wait_text = ""
        self._dot_i = 0

        self.setObjectName("bootToastShell")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        # Transparent shell so only the inner card paints — bottom radii clip.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(382)
        try:
            app = QGuiApplication.instance()
            if app is not None and hasattr(app, "styleHints"):
                app.styleHints().colorSchemeChanged.connect(self._on_color_scheme)
        except Exception:
            pass

        shell = QVBoxLayout(self)
        # Margins leave room for the drop shadow so corners are not clipped.
        shell.setContentsMargins(10, 10, 10, 14)
        shell.setSpacing(0)

        card = QFrame()
        card.setObjectName("bootToastCard")
        self._card = card
        self._shadow = QGraphicsDropShadowEffect(card)
        self._shadow.setBlurRadius(34)
        self._shadow.setOffset(QPointF(0, 10))
        card.setGraphicsEffect(self._shadow)
        self._apply_theme_qss()

        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        head = QFrame()
        head.setObjectName("bootToastHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(13, 10, 10, 10)
        hl.setSpacing(9)
        icon = QLabel()
        ic = load_app_icon()
        if not ic.isNull():
            icon.setPixmap(ic.pixmap(14, 14))
        brand = QLabel("클론업")
        brand.setObjectName("bootToastBrand")
        self._stamp = QLabel("지금")
        self._stamp.setObjectName("bootToastStamp")
        btn_x = QPushButton("✕")
        btn_x.setObjectName("bootToastX")
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.clicked.connect(self._on_later)
        hl.addWidget(icon, 0)
        hl.addWidget(brand, 0)
        hl.addWidget(self._stamp, 0)
        hl.addStretch(1)
        hl.addWidget(btn_x, 0)
        card_lay.addWidget(head)

        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(16, 15, 16, 16)
        self._body.setSpacing(13)
        card_lay.addWidget(body)

        self._title = QLabel("")
        self._title.setObjectName("bootToastTitle")
        self._title.setWordWrap(True)
        self._lead = QLabel("")
        self._lead.setObjectName("bootToastLead")
        self._lead.setWordWrap(True)
        self._body.addWidget(self._title)
        self._body.addWidget(self._lead)

        self._panel_host = QVBoxLayout()
        self._panel_host.setContentsMargins(0, 0, 0, 0)
        self._panel_host.setSpacing(8)
        self._body.addLayout(self._panel_host)

        self._msg_lab = QLabel("저장 메시지")
        self._msg_lab.setObjectName("bootToastMeta")
        self._msg = QLineEdit(default_message or "Update")
        self._msg.setObjectName("bootToastMsg")
        self._body.addWidget(self._msg_lab)
        self._body.addWidget(self._msg)

        self._btn_row = QHBoxLayout()
        self._btn_row.setContentsMargins(0, 0, 0, 0)
        self._btn_row.setSpacing(9)
        self._body.addLayout(self._btn_row)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        self._quiet_link = QPushButton("이 알림 그만 받기")
        self._quiet_link.setObjectName("bootToastLink")
        self._quiet_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._quiet_link.clicked.connect(self._go_quiet)
        self._foot = QLabel("")
        self._foot.setObjectName("bootToastMeta")
        self._foot.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        foot.addWidget(self._quiet_link, 0)
        foot.addStretch(1)
        foot.addWidget(self._foot, 0)
        self._body.addLayout(foot)

        shell.addWidget(card)

        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(420)
        self._dot_timer.timeout.connect(self._tick_dots)

        self._render()
        self._place_bottom_right()

    def _apply_theme_qss(self) -> None:
        self.setStyleSheet(_toast_qss())
        # Slightly stronger shadow on dark so the card lifts off wallpaper.
        try:
            p = active_palette()
            alpha = 120 if p.name == "dark" else 87
            self._shadow.setColor(QColor(20, 24, 30, alpha))
        except Exception:
            pass

    def _on_color_scheme(self, *_args) -> None:
        try:
            from app.ui.theme import apply_system_theme

            apply_system_theme()
        except Exception:
            pass
        self._apply_theme_qss()
        if self.isVisible():
            self._render()

    # --- public ---
    def set_waiting(self, text: str) -> None:
        self._wait_text = text
        self._scene = BootNotifyScene.WAIT
        self._stamp.setText("방금")
        self._render()
        if not self._dot_timer.isActive():
            self._dot_timer.start()

    def set_done_quiet(self) -> None:
        self._dot_timer.stop()
        self.close()

    # --- layout helpers ---
    def _clear_layout(self, lay: QVBoxLayout | QHBoxLayout) -> None:
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            child = item.layout()
            if child is not None:
                self._clear_layout(child)

    def _place_bottom_right(self) -> None:
        # 시안: right 18px, above taskbar (~52px)
        margin = 18
        taskbar = 52
        self.adjustSize()
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        x = avail.right() - self.width() - margin + 1
        y = avail.bottom() - self.height() - taskbar
        y = max(avail.top() + margin, y)
        self.move(max(avail.left() + margin, x), y)

    def _selected_paths(self) -> list[str]:
        if len(self._pending) == 1:
            return [self._pending[0].path]
        return [p for p, on in self._picked.items() if on]

    def _render(self) -> None:
        self._clear_layout(self._panel_host)
        self._clear_layout(self._btn_row)
        scene = self._scene
        show_msg = scene in (BootNotifyScene.ONE, BootNotifyScene.MANY)
        self._msg_lab.setVisible(show_msg)
        self._msg.setVisible(show_msg)
        self._quiet_link.setVisible(
            scene in (BootNotifyScene.ONE, BootNotifyScene.MANY)
        )

        if scene == BootNotifyScene.ONE and self._pending:
            pf = self._pending[0]
            n = pf.file_count
            self._title.setText("안 올린 수정이 있어요")
            self._lead.setText(
                f"{pf.name} 폴더에 GitHub로 보내지 않은 변경이 있습니다. "
                "지금 올릴까요?"
            )
            self._foot.setText("커밋하고 푸시합니다")
            panel = QFrame()
            panel.setObjectName("bootToastPanel")
            pl = QVBoxLayout(panel)
            pl.setContentsMargins(14, 12, 14, 12)
            pl.setSpacing(8)
            row = QHBoxLayout()
            name = QLabel(pf.name)
            name.setObjectName("bootToastMono")
            meta = QLabel(f"파일 {n}개" if n else "보낼 커밋 있음")
            meta.setObjectName("bootToastMeta")
            row.addWidget(name, 1)
            row.addWidget(meta, 0)
            pl.addLayout(row)
            for f in pf.files:
                fr = QHBoxLayout()
                kind = QLabel(f.kind)
                kind.setObjectName("bootToastKind")
                kind.setFixedSize(15, 15)
                kind.setAlignment(Qt.AlignmentFlag.AlignCenter)
                kind.setStyleSheet(
                    f"QLabel#bootToastKind {{ background: {f.tone}; "
                    f"border-radius: 3px; color: {_KIND_FG}; font-size: 9px; "
                    f"font-weight: 600; }}"
                )
                path = QLabel(f.path)
                path.setObjectName("bootToastFile")
                path.setToolTip(f.path)
                fr.addWidget(kind, 0)
                fr.addWidget(path, 1)
                pl.addLayout(fr)
            self._panel_host.addWidget(panel)
            self._add_btn("올리기", "primary", self._on_upload, stretch=True)
            self._add_btn("나중에", "normal", self._on_later)
            self._add_btn(
                "열어서 보기",
                "quiet",
                lambda: self.open_app_requested.emit(pf.path),
            )

        elif scene == BootNotifyScene.MANY:
            n_all = len(self._pending)
            chosen = len(self._selected_paths())
            if n_all == 2:
                self._title.setText("두 폴더에 안 올린 수정이 있어요")
            elif n_all == 3:
                self._title.setText("세 폴더에 안 올린 수정이 있어요")
            elif n_all > 3:
                self._title.setText(f"{n_all}개 폴더에 안 올린 수정이 있어요")
            else:
                self._title.setText("안 올린 수정이 있어요")
            self._lead.setText(
                "올릴 폴더를 골라 주세요. 고른 폴더만 커밋하고 푸시합니다."
            )
            self._foot.setText("메시지는 모두에 같이 씁니다")
            for pf in self._pending:
                cb = QCheckBox(
                    f"{pf.name}    파일 {pf.file_count}개"
                    if pf.file_count
                    else pf.name
                )
                cb.setObjectName("bootToastFolder")
                cb.setChecked(self._picked.get(pf.path, True))
                cb.toggled.connect(
                    lambda on, path=pf.path: self._on_toggle(path, on)
                )
                self._panel_host.addWidget(cb)
            label = (
                f"{chosen}개 올리기" if chosen > 0 else "폴더를 골라 주세요"
            )
            self._add_btn(
                label,
                "primary" if chosen > 0 else "off",
                self._on_upload if chosen > 0 else None,
                stretch=True,
                enabled=chosen > 0,
            )
            self._add_btn("나중에", "normal", self._on_later)

        elif scene == BootNotifyScene.WAIT:
            self._title.setText("올리는 중입니다")
            self._lead.setText("끝나면 알려드릴게요. 이 알림은 닫아도 됩니다.")
            self._foot.setText("")
            panel = QFrame()
            panel.setObjectName("bootToastPanel")
            pl = QHBoxLayout(panel)
            pl.setContentsMargins(14, 12, 14, 12)
            pl.setSpacing(10)
            self._wait_dots = QLabel("●○○")
            self._wait_dots.setObjectName("bootToastMeta")
            self._wait_lab = QLabel(self._wait_text or "GitHub로 보내는 중")
            self._wait_lab.setObjectName("bootToastLead")
            self._wait_lab.setWordWrap(True)
            pl.addWidget(self._wait_dots, 0)
            pl.addWidget(self._wait_lab, 1)
            self._panel_host.addWidget(panel)
            self._add_btn(
                "앱에서 보기",
                "normal",
                lambda: self.open_app_requested.emit(""),
                stretch=True,
            )
            self._add_btn("닫기", "quiet", self._on_later)

        else:  # QUIET
            self._stamp.setText("설정")
            self._title.setText("이 알림을 어떻게 할까요?")
            self._lead.setText("언제든 설정에서 다시 켤 수 있습니다.")
            self._foot.setText("")
            panel = QFrame()
            panel.setObjectName("bootToastPanel")
            pl = QVBoxLayout(panel)
            pl.setContentsMargins(14, 12, 14, 12)
            pl.setSpacing(7)
            for key, val in (
                ("지금", "부팅할 때마다 확인"),
                ("바꾸면", "설정 · 알림"),
            ):
                row = QHBoxLayout()
                k = QLabel(key)
                k.setObjectName("bootToastMeta")
                v = QLabel(val)
                v.setObjectName("bootToastMono")
                v.setStyleSheet("font-size: 12px;")
                row.addWidget(k)
                row.addStretch(1)
                row.addWidget(v)
                pl.addLayout(row)
            self._panel_host.addWidget(panel)
            self._add_btn(
                "일주일 쉬기", "primary", self._on_snooze_week, stretch=True
            )
            self._add_btn("아예 끄기", "normal", self._on_disable)
            self._add_btn("취소", "quiet", self._back_from_quiet)

        self.adjustSize()
        self._place_bottom_right()

    def _add_btn(
        self,
        label: str,
        kind: str,
        slot,
        *,
        stretch: bool = False,
        enabled: bool = True,
    ) -> None:
        btn = QPushButton(label)
        if kind == "primary":
            btn.setObjectName("bootToastPrimary")
        elif kind == "normal":
            btn.setObjectName("bootToastNormal")
        elif kind == "off":
            btn.setObjectName("bootToastPrimary")
            enabled = False
        else:
            btn.setObjectName("bootToastQuiet")
        btn.setEnabled(enabled)
        if enabled and slot is not None:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(slot)
        else:
            btn.setCursor(Qt.CursorShape.ArrowCursor)
        self._btn_row.addWidget(btn, 1 if stretch else 0)

    def _on_toggle(self, path: str, on: bool) -> None:
        self._picked[path] = bool(on)
        if self._scene == BootNotifyScene.MANY:
            self._render()

    def _on_upload(self) -> None:
        paths = self._selected_paths()
        if not paths:
            return
        msg = (self._msg.text() or "").strip() or "Update"
        names = ", ".join(_folder_name(p) for p in paths[:2])
        if len(paths) > 2:
            names += f" 외 {len(paths) - 2}"
        self.set_waiting(f"{names} · 커밋하고 GitHub로 보내는 중")
        self.upload_requested.emit(paths, msg)

    def _on_later(self) -> None:
        self._dot_timer.stop()
        self.later_clicked.emit()
        self.dismissed.emit()
        self.close()

    def _go_quiet(self) -> None:
        self._scene = BootNotifyScene.QUIET
        self._render()

    def _back_from_quiet(self) -> None:
        self._scene = (
            BootNotifyScene.ONE
            if len(self._pending) <= 1
            else BootNotifyScene.MANY
        )
        self._stamp.setText("지금")
        self._render()

    def _on_snooze_week(self) -> None:
        self.snooze_week_requested.emit()
        self._on_later()

    def _on_disable(self) -> None:
        self.disable_requested.emit()
        self._on_later()

    def _tick_dots(self) -> None:
        self._dot_i = (self._dot_i + 1) % 3
        if hasattr(self, "_wait_dots"):
            self._wait_dots.setText(["●○○", "○●○", "○○●"][self._dot_i])


def _folder_name(path: str) -> str:
    from pathlib import Path

    return Path(path).name or path
