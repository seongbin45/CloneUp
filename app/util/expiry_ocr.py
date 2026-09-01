"""Path B Expiration detection via window screenshot + dual OCR.

Captures the classic PAT Chromium window, then runs **Windows.Media.Ocr** and
**Tesseract** in parallel on the same crop. Parses ``30 days`` / ``No expiration``
and **Custom** calendar dates (``2027년 1월 1일``, ``2027-01-01``, ``Jan 1, 2027``).

Requires Pillow. Optional: pytesseract+Tesseract binary, winrt Windows OCR packs.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import re
import sys
import time
from typing import Any

_DAYS_RE = re.compile(r"(?<!\d)(7|30|60|90)\s*days?\b", re.IGNORECASE)
_DAYS_BARE_RE = re.compile(r"(?<!\d)(7|30|60|90)(?!\d)")
_NONE_RE = re.compile(r"\bno\s+expiration\b|\bnever\b|만료\s*없음", re.IGNORECASE)
_ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_KO_DATE_RE = re.compile(
    r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?"
)
_DOT_DATE_RE = re.compile(r"(20\d{2})\s*[./]\s*(\d{1,2})\s*[./]\s*(\d{1,2})")
_EN_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_EN_DATE_RE = re.compile(
    r"\b("
    + "|".join(_EN_MONTHS.keys())
    + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b",
    re.IGNORECASE,
)
_EXPIRATION_LABEL_RE = re.compile(r"\bexpiration\b|만료", re.IGNORECASE)


def tesseract_available() -> bool:
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


def windows_ocr_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401

        return True
    except Exception:
        return False


def _configure_tesseract() -> str | None:
    import pytesseract

    env = (os.environ.get("TESSERACT_CMD") or "").strip()
    # Prefer CloneUp-bundled / post-install path, then system.
    local = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")
    app_dir = os.environ.get("CLONEUP_APP_DIR") or ""
    bundled = (
        os.path.join(app_dir, "tesseract", "tesseract.exe") if app_dir else ""
    )
    candidates = [
        env,
        bundled,
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        local,
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


def _ymd(y: int, m: int, d: int) -> str | None:
    try:
        if not (2015 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31):
            return None
        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return None


def parse_expiration_from_ocr_text(text: str) -> tuple[str | None, str]:
    """
    Extract days token or absolute date from OCR text.

    Supports preset ``7|30|60|90 days``, ``No expiration``, and Custom calendar
    labels such as ``2027년 1월 1일``, ``2027. 1. 1.``, ``2027-01-01``,
    ``Jan 1, 2027``.
    """
    raw = text or ""
    if not raw.strip():
        return None, "ocr-empty"

    lines = [ln.strip() for ln in raw.replace("\r", "\n").split("\n") if ln.strip()]
    blob = "\n".join(lines)

    for i, ln in enumerate(lines):
        if not _EXPIRATION_LABEL_RE.search(ln):
            continue
        # Closed button: selection is usually on the same or next line only.
        # Do not pull in open-menu siblings ("Custom…", "No expiration").
        window = " ".join(lines[i : i + 2])
        got, how = _parse_days_blob(window, near_label=True)
        if got is not None:
            return got, f"near-label:{how}:{window[:56]}"

    for ln in lines:
        if re.fullmatch(r"(7|30|60|90)\s*days?", ln, re.I):
            return ln.split()[0], f"line-only:{ln[:24]}"
        if _NONE_RE.search(ln) and len(ln) < 48:
            return "none", f"line-only:{ln[:24]}"
        got_ln, how_ln = _parse_custom_date(ln)
        if got_ln is not None and len(ln) < 48:
            return got_ln, f"line-custom:{how_ln}:{ln[:32]}"

    got, how = _parse_days_blob(blob, near_label=False)
    if got is not None:
        return got, f"page:{how}"
    return None, f"ocr-no-match|chars={len(blob)}"


def _parse_custom_date(blob: str) -> tuple[str | None, str]:
    m = _KO_DATE_RE.search(blob)
    if m:
        ymd = _ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if ymd:
            return ymd, "ko-date"
    m = _DOT_DATE_RE.search(blob)
    if m:
        ymd = _ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if ymd:
            return ymd, "dot-date"
    m = _ISO_RE.search(blob)
    if m:
        ymd = _ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if ymd:
            return ymd, "iso-date"
    m = _EN_DATE_RE.search(blob)
    if m:
        mo = _EN_MONTHS.get(m.group(1).lower())
        if mo:
            ymd = _ymd(int(m.group(3)), mo, int(m.group(2)))
            if ymd:
                return ymd, "en-date"
    return None, "none"


def _parse_days_blob(blob: str, *, near_label: bool) -> tuple[str | None, str]:
    # Prefer concrete selection over "No expiration" when both appear in OCR.
    custom, how = _parse_custom_date(blob)
    if custom is not None:
        return custom, how
    m = _DAYS_RE.search(blob)
    if m:
        return m.group(1), f"{m.group(1)}-days"
    # OCR often drops the word "days" (e.g. "Expiration 30").
    if near_label:
        m2 = _DAYS_BARE_RE.search(blob)
        if m2:
            return m2.group(1), f"{m2.group(1)}-bare"
    if _NONE_RE.search(blob):
        return "none", "none"
    return None, "none"


def _is_minimized(hwnd: int) -> bool:
    import ctypes

    user32 = ctypes.windll.user32
    try:
        return bool(user32.IsIconic(hwnd))
    except Exception:
        return False


def _restore_window(hwnd: int) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.25)
    except Exception:
        pass


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    # Minimized windows report ~(-32000,-32000)
    if left <= -10000 or top <= -10000:
        return None
    if right - left < 120 or bottom - top < 120:
        return None
    return left, top, right, bottom


def _grab_hwnd_image(hwnd: int) -> Any | None:
    """
    Capture a visible top-level window as a Pillow RGB image.

    Restores minimized windows, then prefers ``ImageGrab.grab(bbox=…)``
    (real screen pixels). Falls back to ``PrintWindow``.
    """
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        from PIL import Image, ImageGrab
    except Exception:
        return None

    _restore_window(hwnd)
    box = _window_rect(hwnd)
    if box is None:
        return None
    left, top, right, bottom = box
    w, h = right - left, bottom - top

    # 1) Screen grab (most reliable for Chromium)
    try:
        img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        if img is not None and img.size[0] >= 80 and img.size[1] >= 80:
            return img.convert("RGB")
    except TypeError:
        # Older Pillow: no all_screens
        try:
            img = ImageGrab.grab(bbox=(left, top, right, bottom))
            if img is not None and img.size[0] >= 80 and img.size[1] >= 80:
                return img.convert("RGB")
        except Exception:
            pass
    except Exception:
        pass

    # 2) PrintWindow fallback
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.GetWindowDC.restype = wintypes.HDC
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]

    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        return None
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    if not mem_dc or not bmp:
        if hwnd_dc:
            user32.ReleaseDC(hwnd, hwnd_dc)
        return None
    old = gdi32.SelectObject(mem_dc, bmp)
    user32.PrintWindow(hwnd, mem_dc, 2)

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

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0
    buf_len = w * h * 4
    buf = (ctypes.c_char * buf_len)()
    rows = gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.SelectObject(mem_dc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)
    if not rows:
        return None
    return Image.frombuffer("RGB", (w, h), bytes(buf), "raw", "BGRX", 0, 1).copy()


def _crop_for_expiration(img: Any) -> Any:
    try:
        w, h = img.size
        top = int(h * 0.10)
        bottom = int(h * 0.62)
        left = int(w * 0.08)
        right = int(w * 0.92)
        if bottom - top < 80 or right - left < 80:
            return img
        return img.crop((left, top, right, bottom))
    except Exception:
        return img


def ocr_image_tesseract(img: Any) -> tuple[str, str]:
    try:
        import pytesseract
    except Exception as e:
        return "", f"pytesseract-missing:{e}"
    cmd = _configure_tesseract()
    if cmd is None:
        return "", "tesseract-binary-missing"
    try:
        text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")
        return text or "", f"tesseract:{cmd}"
    except Exception as e:
        return "", f"tesseract-error:{e}"


def ocr_image_windows(img: Any) -> tuple[str, str]:
    """Windows.Media.Ocr (built-in). Sync wrapper around RecognizeAsync."""
    if sys.platform != "win32":
        return "", "not-windows"
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter
    except Exception as e:
        return "", f"winocr-import:{e}"

    try:
        eng = OcrEngine.try_create_from_language(
            Language("en-US")
        ) or OcrEngine.try_create_from_user_profile_languages()
        if eng is None:
            return "", "winocr-engine-none"
        rgba = img.convert("RGBA")
        width, height = rgba.size

        async def _run() -> str:
            writer = DataWriter()
            writer.write_bytes(rgba.tobytes())
            sb = SoftwareBitmap.create_copy_from_buffer(
                writer.detach_buffer(),
                BitmapPixelFormat.RGBA8,
                width,
                height,
            )
            result = await eng.recognize_async(sb)
            if result is None or result.lines is None:
                return ""
            return "\n".join(line.text for line in result.lines if line and line.text)

        text = asyncio.run(_run())
        return text or "", "winocr:en-US"
    except Exception as e:
        return "", f"winocr-error:{e}"


# Back-compat alias
def ocr_image_to_text(img: Any) -> tuple[str, str]:
    return ocr_image_tesseract(img)


def ocr_image_to_string_safe(img: Any) -> tuple[str, str]:
    return ocr_image_tesseract(img)


def _pick_token_hwnd() -> tuple[int, str]:
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
                if "personal access token" in tl or "new personal access" in tl:
                    score += 40
                if "/settings/tokens" in tl or "tokens/new" in tl:
                    score += 20
                if "token" in tl and ("github" in tl or "classic" in tl):
                    score += 15
                hwnd = _window_hwnd(w)
                if not hwnd:
                    continue
                # Prefer visible windows for screenshot OCR.
                if _is_minimized(hwnd):
                    score -= 50
                if score > best_score:
                    best_score = score
                    best_hwnd = hwnd
                    best_title = title[:48]
            except Exception:
                continue
    except Exception as e:
        return 0, f"scan:{e}"
    if not best_hwnd or best_score < 28:
        return (
            0,
            f"no-token-hwnd|best_score={best_score}|title={best_title}"
            f"|pids={len(pids)}",
        )
    return best_hwnd, f"hwnd={best_hwnd}|title={best_title}|score={best_score}"


def _pick_best_parse(
    results: list[tuple[str, str, str]],
) -> tuple[str | None, str]:
    """
    ``results`` items: (engine, text, engine_detail).
    Prefer agreeing tokens; else first successful parse.
    """
    parsed: list[tuple[str, str, str]] = []  # token, engine, detail
    details: list[str] = []
    for engine, text, eng_detail in results:
        got, how = parse_expiration_from_ocr_text(text)
        details.append(f"{engine}:{eng_detail}|{how}|chars={len(text or '')}")
        if got is not None:
            parsed.append((got, engine, how))
            preview = " ".join((text or "").split())[:60]
            if preview:
                details[-1] += f"|preview={preview!r}"
    if not parsed:
        # Attach previews from engines that returned text but no parse
        for engine, text, eng_detail in results:
            if text and text.strip():
                preview = " ".join(text.split())[:60]
                details.append(f"{engine}-unparsed-preview={preview!r}")
        return None, "|".join(details)

    # Majority / first
    tokens = [p[0] for p in parsed]
    if len(set(tokens)) == 1:
        tok = tokens[0]
        engines = ",".join(p[1] for p in parsed)
        return tok, f"agree:{engines}|{'|'.join(details)}"
    # Prefer absolute custom date over relative days if both appear
    for tok, eng, how in parsed:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", tok):
            return tok, f"prefer-custom:{eng}|{'|'.join(details)}"
    tok, eng, how = parsed[0]
    return tok, f"first:{eng}|{'|'.join(details)}"


def read_token_expiration_ocr() -> tuple[str | None, str]:
    """
    Screenshot the PAT Chromium window, run Windows OCR + Tesseract in parallel.

    Returns ``(days_or_none_or_YYYY-MM-DD, detail)``.
    """
    if sys.platform != "win32":
        return None, "not-windows"
    try:
        from PIL import Image  # noqa: F401
    except Exception as e:
        return None, f"pillow-missing:{e}"

    hwnd, pick_detail = _pick_token_hwnd()
    if not hwnd:
        return None, pick_detail

    img = _grab_hwnd_image(hwnd)
    if img is None:
        return None, f"capture-failed|{pick_detail}"

    cropped = _crop_for_expiration(img)
    jobs: list[tuple[str, Any]] = []
    if windows_ocr_available():
        jobs.append(("winocr", ocr_image_windows))
    if tesseract_available():
        jobs.append(("tesseract", ocr_image_tesseract))
    if not jobs:
        return None, f"no-ocr-engine|{pick_detail}"

    results: list[tuple[str, str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futs = {pool.submit(fn, cropped): name for name, fn in jobs}
        for fut in concurrent.futures.as_completed(futs):
            name = futs[fut]
            try:
                text, eng_detail = fut.result()
            except Exception as e:
                text, eng_detail = "", f"error:{e}"
            results.append((name, text, eng_detail))

    got, parse_detail = _pick_best_parse(results)
    detail = f"{pick_detail}|capture={img.size[0]}x{img.size[1]}|{parse_detail}"
    return got, detail
