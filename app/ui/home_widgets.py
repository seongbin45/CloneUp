"""Small home-shell paint widgets (folder glyph, fact row)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from app.ui.home_tokens import (
    HOME_FACT_KEY_W,
    HOME_FOLDER_ICON_H,
    HOME_FOLDER_ICON_W,
    home_chrome_colors,
)


def make_nav_chevron_icon(
    *,
    left: bool,
    fg: str,
    size: int = 24,
) -> QIcon:
    """Toolbar ‹ / › — pixmap so we never depend on fonts (‹ tofu → white square)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(fg), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    cx = cy = size / 2.0
    # Match 시안 ~12px chevron weight inside 24px hit target
    if left:
        p.drawLine(QPointF(cx + 2.5, cy - 5.0), QPointF(cx - 3.0, cy))
        p.drawLine(QPointF(cx - 3.0, cy), QPointF(cx + 2.5, cy + 5.0))
    else:
        p.drawLine(QPointF(cx - 2.5, cy - 5.0), QPointF(cx + 3.0, cy))
        p.drawLine(QPointF(cx + 3.0, cy), QPointF(cx - 2.5, cy + 5.0))
    p.end()
    return QIcon(pm)


class FolderGlyph(QWidget):
    """Tabbed folder icon: git vs plain.

    ``fill_bg`` must match the parent row/card so corners don't show a nested
    white (or wrong) rectangle.
    """

    def __init__(
        self,
        *,
        has_git: bool,
        large: bool = False,
        colors: Any | None = None,
        fill_bg: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._has_git = has_git
        self._colors = colors
        self._fill_bg = fill_bg  # unused when transparent; kept for API compat
        w = HOME_FOLDER_ICON_W if large else 17
        h = HOME_FOLDER_ICON_H if large else 15
        self.setFixedSize(w, h)
        # Let parent row paint hover/selection; only draw the folder shape here.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

    def set_colors(self, colors: Any | None) -> None:
        self._colors = colors
        self.update()

    def set_fill_bg(self, fill_bg: str | None) -> None:
        self._fill_bg = fill_bg
        self.update()

    def set_has_git(self, has_git: bool) -> None:
        self._has_git = has_git
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        c = self._colors or home_chrome_colors()
        body = QColor(c.folder_git_bg if self._has_git else c.folder_plain_bg)
        tab = QColor(c.folder_git_top if self._has_git else c.folder_plain_top)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()
        tab_h = max(3, int(h * 0.22))
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, w * 0.42, tab_h + 2), 2, 2)
        p.fillPath(path, tab)
        body_path = QPainterPath()
        body_path.addRoundedRect(QRectF(1, tab_h, w - 2, h - tab_h - 1), 3, 3)
        p.fillPath(body_path, body)
        p.setPen(QPen(tab, 1.0))
        p.drawPath(body_path)
        p.end()


class FactRow(QWidget):
    """Key (fixed width) + value for detail panel."""

    def __init__(
        self,
        key: str,
        value: str,
        *,
        value_color: str | None = None,
        value_weight: int = 400,
        colors: Any | None = None,
        value_max_width: float | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        c = colors or home_chrome_colors()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(10)
        k = QLabel(key)
        k.setFixedWidth(HOME_FACT_KEY_W)
        v = QLabel()
        v.setWordWrap(True)
        v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fg = value_color or c.text_secondary
        lay.addWidget(k, 0)
        lay.addWidget(v, 1)
        # Must be transparent: global QSS paints QWidget with bg_window, which
        # shows as a nested slab inside homeDetail (bg_detail).
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet(
            f"background-color: transparent;"
            f" border-bottom: 1px solid {c.border_soft};"
        )
        k.setStyleSheet(
            f"font-size: 12px; color: {c.text_muted}; font-weight: 500;"
            f" background-color: transparent;"
        )
        from app.ui.text_fit import (
            DETAIL_FACT_BASE_PX,
            DETAIL_FACT_MAX_H,
            DETAIL_FACT_MIN_PX,
            DETAIL_FACT_VALUE_W,
            apply_fitting_font_box,
        )

        budget = (
            float(value_max_width)
            if value_max_width is not None
            else float(DETAIL_FACT_VALUE_W)
        )
        # Paths / owner/repo: break on "/" and grow row height — never clip.
        path_like = ("/" in value) or ("\\" in value) or (key in ("위치", "GitHub"))
        apply_fitting_font_box(
            v,
            value,
            budget,
            float(DETAIL_FACT_MAX_H),
            base_px=float(DETAIL_FACT_BASE_PX),
            min_px=float(DETAIL_FACT_MIN_PX),
            bold=int(value_weight) >= 600,
            color=fg,
            path_like=path_like,
        )
        self._value_label = v
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )


def _path_link_openable(text: str) -> bool:
    """True when we can show an open-button (not a placeholder / pending)."""
    if not text or text in ("—", "연결 안 됨"):
        return False
    if "확인 중" in text:
        return False
    return True


def github_browse_url(origin_display: str) -> str | None:
    """owner/repo or URL → https GitHub URL; None if not openable."""
    d = (origin_display or "").strip()
    if not d or d in ("—", "연결 안 됨") or "확인 중" in d:
        return None
    if d.startswith("https://") or d.startswith("http://"):
        return d
    # strip .git suffix
    if d.endswith(".git"):
        d = d[:-4]
    if "/" in d and " " not in d:
        return f"https://github.com/{d}"
    return None


def _make_path_open_button(
    *,
    label: str,
    tooltip: str,
    open_target: str,
    is_local: bool,
    colors: Any,
) -> QPushButton:
    """Outline button; hover fills primary; click opens path/URL."""
    c = colors
    btn = QPushButton(label)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(tooltip)
    btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    btn.setStyleSheet(
        f"QPushButton {{ text-align: left; border: 1px solid {c.primary};"
        f" border-radius: 5px; padding: 4px 10px; background: transparent;"
        f" color: {c.primary}; font-size: 12.5px; font-weight: 600; }}"
        f"QPushButton:hover {{ background: {c.primary}; color: #fbfaf8;"
        f" border-color: {c.primary}; }}"
        f"QPushButton:pressed {{ background: {c.primary_hover};"
        f" border-color: {c.primary_hover}; color: #fbfaf8; }}"
    )

    def _open(_checked: bool = False, t=open_target, local=is_local) -> None:
        if local:
            QDesktopServices.openUrl(QUrl.fromLocalFile(t))
        else:
            QDesktopServices.openUrl(QUrl(t))

    btn.clicked.connect(_open)
    return btn


class PathActionsBar(QWidget):
    """Under folder title: 「폴더 열기」+「GitHub에서 보기」 in one row (same box)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("homePathActions")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 4, 0, 10)
        self._lay.setSpacing(8)
        self._lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

    def clear_actions(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def set_actions(
        self,
        *,
        folder_path: str | None,
        folder_tip: str = "",
        github_url: str | None = None,
        github_tip: str = "",
        colors: Any | None = None,
    ) -> None:
        """Rebuild the two buttons side-by-side (no separate fact rows)."""
        c = colors or home_chrome_colors()
        self.clear_actions()
        self.setStyleSheet(
            f"QWidget#homePathActions {{ background: transparent;"
            f" border-bottom: 1px solid {c.border_soft}; }}"
        )
        if folder_path:
            self._lay.addWidget(
                _make_path_open_button(
                    label="폴더 열기",
                    tooltip=folder_tip or folder_path,
                    open_target=folder_path,
                    is_local=True,
                    colors=c,
                ),
                0,
            )
        if github_url:
            self._lay.addWidget(
                _make_path_open_button(
                    label="GitHub에서 보기",
                    tooltip=github_tip or github_url,
                    open_target=github_url,
                    is_local=False,
                    colors=c,
                ),
                0,
            )
        # Keep the pair centered as a unit
        if self._lay.count() == 0:
            self.hide()
        else:
            self.show()
