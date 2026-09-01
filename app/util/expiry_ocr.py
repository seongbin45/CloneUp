"""Path B Expiration detection via window screenshot + Tesseract OCR.

GitHub classic PAT form often exposes the closed dropdown a11y Name as bare
``Expiration`` (no days). Screenshot OCR reads the visible ``30 days`` /
``No expiration`` text instead.

Requires:
  - ``Pillow``, ``pytesseract`` (pip)
  - Tesseract OCR binary on PATH, or ``TESSERACT_CMD`` / common install path
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

# Reuse the same day tokens as UIA helpers.
_DAYS_RE = re.compile(
    r"(?<!\d)(7|30|60|90)\s*days?\b",
    re.IGNORECASE,
)
_NONE_RE = re.compile(
    r"\bno\s+expiration\b|\bnever\b|만료\s*없음",
    re.IGNORECASE,
)
_ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_EXPIRATION_LABEL_RE = re.compile(r"\bexpiration\b", re.IGNORECASE)


def tesseract_available() -> bool:
    """True if pytesseract can reach a Tesseract binary."""
    try:
        import pytesseract  # noqa: F401
    except Exception:
        return False
    try:
        _configure_tesseract()
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _configure_tesseract() -> str | None:
    """Set ``pytesseract.pytesseract.tesseract_cmd`` if needed. Return path used."""
    import pytesseract

    env = (os.environ.get("TESSERACT_CMD") or "").strip()
    candidates = [
        env,
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        "tesseract",
    ]
    for path in candidates:
        if not path:
            continue
        if path != "tesseract" and not os.path.isfile(path):
            continue
        if path != "tesseract":
            pytesseract.pytesseract.tesseract_cmd = path
        return path
    return None


def parse_expiration_from_ocr_text(text: str) -> tuple[str | None, str]:
    """
    Extract days token from OCR text.

    Prefers a value near an ``Expiration`` label (same/next lines), then any
    clear ``N days`` / ``No expiration`` / ``YYYY-MM-DD``.
    Returns ``(token, detail)``.
    """
    raw = text or ""
    if not raw.strip():
        return None, "ocr-empty"

    lines = [ln.strip() for ln in raw.replace("\r", "\n").split("\n") if ln.strip()]
    blob = "\n".join(lines)

    # 1) Look near "Expiration" label (button shows current selection beside it).
    for i, ln in enumerate(lines):
        if not _EXPIRATION_LABEL_RE.search(ln):
            continue
        window = " ".join(lines[i : i + 3])
        got, how = _parse_days_blob(window)
        if got is not None:
            return got, f"near-label:{how}:{window[:48]}"

    # 2) Whole-page first solid match (open dropdown lists many options —
    #    prefer selected-looking: line that is ONLY "N days" / No expiration).
    for ln in lines:
        if re.fullmatch(r"(7|30|60|90)\s*days?", ln, re.I):
            return ln.split()[0], f"line-only:{ln[:24]}"
        if _NONE_RE.search(ln) and len(ln) < 40:
            return "none", f"line-only:{ln[:24]}"

    got, how = _parse_days_blob(blob)
    if got is not None:
        return got, f"page:{how}"
    return None, f"ocr-no-match|chars={len(blob)}"


def _parse_days_blob(blob: str) -> tuple[str | None, str]:
    if _NONE_RE.search(blob):
        return "none", "none"
    m = _DAYS_RE.search(blob)
    if m:
        return m.group(1), f"{m.group(1)}-days"
    m_iso = _ISO_RE.search(blob)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)}", "iso-date"
    return None, "none"


def _grab_hwnd_image(hwnd: int) -> Any | None:
    """Capture a top-level window bitmap via PrintWindow (Pillow Image)."""
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        from PIL import Image
    except Exception:
        return None

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    # DPI-aware rect
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
    w, h = right - left, bottom - top
    if w < 80 or h < 80:
        return None
    # Cap huge monitors — OCR middle band of the client area later.
    if w > 3840:
        w = 3840
        right = left + w
    if h > 2160:
        h = 2160
        bottom = top + h

    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        return None
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    old = gdi32.SelectObject(mem_dc, bmp)
    # PW_RENDERFULLCONTENT = 2 (captures Chromium better than BitBlt alone)
    ok = user32.PrintWindow(hwnd, mem_dc, 2)
    if not ok:
        # Fallback BitBlt from screen DC
        screen_dc = user32.GetDC(0)
        gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, left, top, 0x00CC0020)
        user32.ReleaseDC(0, screen_dc)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h  # top-down
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    buf_len = w * h * 4
    buf = (ctypes.c_char * buf_len)()
    gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(bmi), 0)

    gdi32.SelectObject(mem_dc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)

    img = Image.frombuffer("RGB", (w, h), bytes(buf), "raw", "BGRX", 0, 1)
    return img


def _crop_for_expiration(img: Any) -> Any:
    """
    Focus OCR on the upper-middle form band where Expiration usually sits.

    Full-window OCR is slow and noisy (chrome UI). Classic PAT form puts
    Note / Expiration in roughly the top half of the content area.
    """
    try:
        w, h = img.size
        # Skip top chrome (~12%) and bottom half; keep a wide center band.
        top = int(h * 0.10)
        bottom = int(h * 0.62)
        left = int(w * 0.08)
        right = int(w * 0.92)
        if bottom - top < 80 or right - left < 80:
            return img
        return img.crop((left, top, right, bottom))
    except Exception:
        return img


def ocr_image_to_text(img: Any) -> tuple[str, str]:
    """Run Tesseract on a PIL image. Returns ``(text, detail)``."""
    try:
        import pytesseract
    except Exception as e:
        return "", f"pytesseract-missing:{e}"

    cmd = _configure_tesseract()
    if cmd is None:
        return "", "tesseract-binary-missing"

    try:
        # eng is enough for "30 days" / "No expiration" / "Expiration"
        text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")
        return text or "", f"tesseract:{cmd}"
    except Exception as e:
        return "", f"tesseract-error:{e}"


def _pick_token_hwnd() -> tuple[int, str]:
    """Best Chromium HWND for classic token form (title score)."""
    if sys.platform != "win32":
        return 0, "not-windows"
    try:
        import uiautomation as auto

        from app.util.browser_address import (
            _BROWSER_CLASS,
            _iter_chromium_windows,
            _window_hwnd,
            list_chromium_browser_pids,
            window_title_connect_score,
        )
    except Exception as e:
        return 0, f"import:{e}"

    pids = list_chromium_browser_pids()
    best_hwnd = 0
    best_score = -1
    best_title = ""
    try:
        for w in _iter_chromium_windows(auto, pids=pids or None):
            try:
                if (w.ClassName or "") != _BROWSER_CLASS:
                    continue
                title = (w.Name or "").strip()
                tl = title.lower()
                score = window_title_connect_score(title)
                # Prefer classic token create title strongly.
                if "personal access token" in tl or "new personal access" in tl:
                    score += 40
                if "/settings/tokens" in tl or "tokens/new" in tl:
                    score += 20
                if "token" in tl and ("github" in tl or "classic" in tl):
                    score += 15
                hwnd = _window_hwnd(w)
                if hwnd and score > best_score:
                    best_score = score
                    best_hwnd = hwnd
                    best_title = title[:48]
            except Exception:
                continue
    except Exception as e:
        return 0, f"scan:{e}"
    # Reject unrelated Chromium (IDE, YouTube, …) — need a PAT/GitHub signal.
    if not best_hwnd or best_score < 28:
        return (
            0,
            f"no-token-hwnd|best_score={best_score}|title={best_title}"
            f"|pids={len(pids)}",
        )
    return best_hwnd, f"hwnd={best_hwnd}|title={best_title}|score={best_score}"


def read_token_expiration_ocr() -> tuple[str | None, str]:
    """
    Screenshot the best Chromium window + OCR → Expiration days token.

    Returns ``(days_or_none_or_date, detail)``. Safe to call off the UI thread.
    """
    if sys.platform != "win32":
        return None, "not-windows"
    try:
        from PIL import Image  # noqa: F401
    except Exception as e:
        return None, f"pillow-missing:{e}"
    if not tesseract_available():
        return None, "tesseract-unavailable"

    hwnd, pick_detail = _pick_token_hwnd()
    if not hwnd:
        return None, pick_detail

    img = _grab_hwnd_image(hwnd)
    if img is None:
        return None, f"capture-failed|{pick_detail}"

    cropped = _crop_for_expiration(img)
    text, ocr_detail = ocr_image_to_string_safe(cropped)
    got, parse_detail = parse_expiration_from_ocr_text(text)
    detail = f"{pick_detail}|{ocr_detail}|{parse_detail}|chars={len(text)}"
    if got is None:
        # Keep a short OCR preview for logs (no secrets expected on this form).
        preview = " ".join(text.split())[:80]
        if preview:
            detail += f"|preview={preview!r}"
    return got, detail


def ocr_image_to_string_safe(img: Any) -> tuple[str, str]:
    return ocr_image_to_text(img)
