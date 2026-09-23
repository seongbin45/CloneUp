"""Circular sidebar avatar — initial fallback or GitHub profile photo.

Avoids QLabel+border-radius stretch bugs (green bar above username).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

_log = logging.getLogger(__name__)

AVATAR_PX = 23
# GitHub avatar CDN ``s=`` max is typically 460 — fetch large, downscale for HiDPI.
AVATAR_FETCH_PX = 460
_CACHE_TAG = "s460"  # bump to invalidate old tiny caches (e.g. s=46)


def avatar_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMP") or "."
    d = Path(base) / "CloneUp" / "avatars"
    d.mkdir(parents=True, exist_ok=True)
    return d


def avatar_cache_path(login: str) -> Path:
    safe = "".join(c for c in (login or "user").lower() if c.isalnum() or c in "-_")
    return avatar_cache_dir() / f"{safe or 'user'}_{_CACHE_TAG}.png"


def avatar_fetch_url(url: str, *, size: int = AVATAR_FETCH_PX) -> str:
    """Force GitHub avatar CDN to the requested pixel size (highest useful)."""
    u = (url or "").strip()
    if not u:
        return u
    # Strip existing size query bits, then set s=
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(u)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "s"]
    q.append(("s", str(int(size))))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment)
    )


def load_cached_avatar_pixmap(
    login: str,
    size: int = AVATAR_PX,
    *,
    device_pixel_ratio: float = 1.0,
) -> QPixmap | None:
    path = avatar_cache_path(login)
    if not path.is_file():
        return None
    pm = QPixmap(str(path))
    if pm.isNull():
        return None
    dpr = max(1.0, float(device_pixel_ratio or 1.0))
    target = max(size, int(round(size * dpr)))
    scaled = pm.scaled(
        target,
        target,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    return scaled


def save_avatar_bytes(login: str, data: bytes) -> Path | None:
    if not data:
        return None
    path = avatar_cache_path(login)
    try:
        path.write_bytes(data)
        return path
    except OSError as e:
        _log.debug("avatar cache write failed: %s", e)
        return None


class HomeAvatar(QWidget):
    """Fixed 23×23 circle: photo if set, else initial on tinted bg."""

    def __init__(
        self,
        *,
        initial: str = "?",
        bg: str = "#cfe3da",
        fg: str = "#1f6f5c",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._initial = (initial or "?").upper()[:1]
        self._bg = QColor(bg)
        self._fg = QColor(fg)
        self._pixmap: QPixmap | None = None
        self.setFixedSize(AVATAR_PX, AVATAR_PX)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_initial(self, initial: str, *, bg: str, fg: str) -> None:
        self._initial = (initial or "?").upper()[:1]
        self._bg = QColor(bg)
        self._fg = QColor(fg)
        self.update()

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addEllipse(rect)
        p.setClipPath(path)
        if self._pixmap is not None and not self._pixmap.isNull():
            # HiDPI-aware draw into widget rect (pixmap may have devicePixelRatio)
            p.drawPixmap(self.rect(), self._pixmap, self._pixmap.rect())
        else:
            p.fillRect(self.rect(), self._bg)
            p.setPen(self._fg)
            font = p.font()
            font.setPixelSize(12)
            font.setBold(True)
            p.setFont(font)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self._initial)
        p.end()


class AvatarFetchWorker(QThread):
    """Download high-res avatar_url → cache → emit path."""

    finished_ok = Signal(str, str)  # login, cache_path
    failed = Signal(str)

    def __init__(self, login: str, url: str, parent=None) -> None:
        super().__init__(parent)
        self._login = login
        self._url = url

    def run(self) -> None:  # noqa: N802
        try:
            import requests

            url = avatar_fetch_url(self._url, size=AVATAR_FETCH_PX)
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            path = save_avatar_bytes(self._login, resp.content)
            if path is None:
                self.failed.emit("cache write failed")
                return
            self.finished_ok.emit(self._login, str(path))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


def persist_avatar_from_user(user: dict | None) -> None:
    """Save login + avatar_url from GET /user payload; kick cache if needed."""
    if not isinstance(user, dict):
        return
    from app.ui.settings_store import save_github_avatar_url, save_last_github_login

    login = str(user.get("login") or "").strip()
    avatar = str(user.get("avatar_url") or "").strip()
    if login:
        save_last_github_login(login)
    if avatar:
        save_github_avatar_url(avatar)
        # Refresh cache if missing (high-res s=460 file)
        if login and not avatar_cache_path(login).is_file():
            try:
                import requests

                url = avatar_fetch_url(avatar, size=AVATAR_FETCH_PX)
                r = requests.get(url, timeout=20)
                if r.ok:
                    save_avatar_bytes(login, r.content)
            except Exception:  # noqa: BLE001
                _log.debug("avatar prefetch failed", exc_info=True)
