"""Path B auth-screen detection via screenshot OCR (UIA fallback).

Supplements title/UIA when StayOnTop guide steals focus or Chromium hides
DOM text from accessibility. Targets:

- GitHub 「Confirm access」 + 「Use passkey」 (sudo / sensitive settings)
- GitHub 「Verify your device」 / 「Device verification」 email code
- Windows Security 「패스키로 로그인」 OS sheet

Call only when UIA already failed to classify passkey / email auth.
"""

from __future__ import annotations

import sys
import time
from typing import Any


def _norm_blob(window_title: str = "", ui_text: str = "") -> str:
    blob = f"{window_title or ''}\n{ui_text or ''}".lower()
    return (
        blob.replace("\xa0", " ")
        .replace("\u00a0", " ")
        .replace("‘", "'")
        .replace("’", "'")
    )


def looks_like_github_sudo_passkey(
    window_title: str = "",
    ui_text: str = "",
) -> bool:
    """
    GitHub Confirm access / sudo gate with Passkey (screenshot 2026-08-22).

    Often sits *on top of* ``/settings/tokens/new`` — URL alone looks like
    the PAT form, but the visible card is still an auth step.
    """
    blob = _norm_blob(window_title, ui_text)
    if not blob.strip():
        return False
    confirm = (
        "confirm access" in blob
        or "sudo mode" in blob
        or "sudo-protected" in blob
        or "entering sudo" in blob
    )
    passkey = (
        "use passkey" in blob
        or "verify with a passkey" in blob
        or ("passkey" in blob and ("authenticate" in blob or "confirm" in blob))
    )
    return confirm and passkey


def looks_like_device_email_verify(
    window_title: str = "",
    ui_text: str = "",
) -> bool:
    """
    GitHub device / email one-time code screens (OCR + UIA).

    Covers both:
    - 「Verify your device」 + code boxes / optional passkey
    - 「Device verification」 + 「We just sent your authentication code…」
    """
    blob = _norm_blob(window_title, ui_text)
    if not blob.strip():
        return False
    if "verify your device" in blob:
        return True
    if "device verification" in blob and (
        "email" in blob
        or "authentication code" in blob
        or "verification code" in blob
        or "sent" in blob
    ):
        return True
    if "we just sent" in blob and (
        "code" in blob or "email" in blob or "authentication" in blob
    ):
        return True
    if "verification code" in blob and (
        "email" in blob or "we just sent" in blob or "verify" in blob
    ):
        return True
    if "device verification code" in blob:
        return True
    if "verify with a passkey" in blob and (
        "verification" in blob or "verify your device" in blob or "verify with a code" in blob
    ):
        return True
    if "verify with a code" in blob and (
        "verify your device" in blob or "we just sent" in blob or "email" in blob
    ):
        return True
    if "re-send the authentication code" in blob or "resend the authentication code" in blob:
        return True
    return False


def classify_auth_ocr_text(
    text: str,
    *,
    window_title: str = "",
) -> str | None:
    """
    Classify OCR / UIA blob into a sign-in method.

    Returns ``passkey`` | ``github_2fa`` | ``None``.
    Prefer OS passkey, then GitHub sudo passkey, then email/device verify.
    """
    from app.util.browser_address import looks_like_passkey_os_prompt

    title = window_title or ""
    body = text or ""
    if looks_like_passkey_os_prompt(title, body):
        return "passkey"
    if looks_like_github_sudo_passkey(title, body):
        return "passkey"
    if looks_like_device_email_verify(title, body):
        return "github_2fa"
    return None


def _crop_for_auth(img: Any) -> Any:
    """Keep the center card; drop noisy desktop chrome around it."""
    try:
        w, h = img.size
        left = int(w * 0.12)
        top = int(h * 0.08)
        right = int(w * 0.88)
        bottom = int(h * 0.92)
        if right - left < 120 or bottom - top < 120:
            return img
        return img.crop((left, top, right, bottom))
    except Exception:
        return img


def _ocr_image_fast(img: Any) -> tuple[str, str]:
    """WinOCR first, Tesseract on miss — same engines as expiry OCR."""
    from app.util.expiry_ocr import (
        _downscale_for_ocr,
        ocr_image_tesseract,
        ocr_image_windows,
        tesseract_available,
        windows_ocr_available,
    )

    cropped = _downscale_for_ocr(_crop_for_auth(img), max_width=1200)
    if windows_ocr_available():
        text, det = ocr_image_windows(cropped)
        if (text or "").strip():
            return text, f"winocr|{det}|ocr={cropped.size[0]}x{cropped.size[1]}"
    if tesseract_available():
        text, det = ocr_image_tesseract(cropped)
        if (text or "").strip():
            return text, f"tesseract|{det}|ocr={cropped.size[0]}x{cropped.size[1]}"
    return "", "no-ocr-text"


def _iter_auth_candidate_hwnds() -> list[tuple[int, str, str]]:
    """
    Ranked (hwnd, title, reason) for auth screenshots.

    Prefers Windows Security, then Chromium titles that look like verify /
    confirm-access / GitHub, then foreground Chromium.
    """
    if sys.platform != "win32":
        return []
    out: list[tuple[int, str, str]] = []
    seen: set[int] = set()

    def _add(hwnd: int, title: str, reason: str) -> None:
        h = int(hwnd or 0)
        if not h or h in seen:
            return
        seen.add(h)
        out.append((h, title or "", reason))

    try:
        import uiautomation as auto

        from app.util.browser_address import (
            _BROWSER_CLASS,
            _iter_chromium_windows,
            _window_hwnd,
            list_chromium_browser_pids,
        )
        from app.util.expiry_ocr import _is_minimized
    except Exception:
        return []

    # 1) Foreground top-level (often Windows Security while guide is StayOnTop
    #    of other apps — but Security itself is usually true foreground).
    try:
        fg = auto.GetForegroundControl()
        win = fg
        top = None
        for _ in range(12):
            if win is None:
                break
            top = win
            try:
                parent = win.GetParentControl()
            except Exception:
                parent = None
            if parent is None:
                break
            win = parent
        if top is not None:
            title = (getattr(top, "Name", None) or "").strip()
            hwnd = _window_hwnd(top)
            tl = title.lower()
            if hwnd and not _is_minimized(hwnd):
                if (
                    "windows 보안" in tl
                    or "windows security" in tl
                    or "confirm access" in tl
                    or "verify your device" in tl
                    or "device verification" in tl
                    or "github" in tl
                ):
                    _add(hwnd, title, "foreground-title")
                elif (getattr(top, "ClassName", None) or "") == _BROWSER_CLASS:
                    _add(hwnd, title, "foreground-browser")
    except Exception:
        pass

    # 2) Chromium windows by title score for verify / confirm / GitHub.
    try:
        pids = list_chromium_browser_pids()
        ranked: list[tuple[int, int, str]] = []
        for w in _iter_chromium_windows(auto, pids=pids or None):
            try:
                if (w.ClassName or "") != _BROWSER_CLASS:
                    continue
                title = (w.Name or "").strip()
                tl = title.lower()
                hwnd = _window_hwnd(w)
                if not hwnd or _is_minimized(hwnd):
                    continue
                score = 0
                if "verify your device" in tl or "device verification" in tl:
                    score += 80
                if "confirm access" in tl:
                    score += 70
                if "two-factor" in tl or "authentication" in tl:
                    score += 40
                if "github" in tl:
                    score += 20
                if "personal access token" in tl or "settings/tokens" in tl:
                    # Still may be sudo overlay — keep as weak candidate.
                    score += 15
                if score > 0:
                    ranked.append((score, hwnd, title))
            except Exception:
                continue
        ranked.sort(key=lambda x: -x[0])
        for score, hwnd, title in ranked[:4]:
            _add(hwnd, title, f"chromium-score={score}")
    except Exception:
        pass

    return out


def read_auth_screen_ocr() -> tuple[str | None, str, str]:
    """
    Screenshot candidate windows and OCR-classify auth screens.

    Returns ``(method|None, ocr_text, detail)``.
    ``method`` is ``passkey`` or ``github_2fa`` when confident.
    """
    t0 = time.monotonic()
    if sys.platform != "win32":
        return None, "", "not-windows"
    try:
        from PIL import Image  # noqa: F401
    except Exception as e:
        return None, "", f"pillow-missing:{e}"

    from app.util.expiry_ocr import _grab_hwnd_image

    candidates = _iter_auth_candidate_hwnds()
    if not candidates:
        return None, "", "no-auth-hwnd"

    parts: list[str] = []
    for hwnd, title, reason in candidates:
        img = _grab_hwnd_image(hwnd)
        if img is None:
            parts.append(f"{reason}:capture-fail|hwnd={hwnd}")
            continue
        text, ocr_det = _ocr_image_fast(img)
        preview = " ".join((text or "").split())[:80]
        parts.append(
            f"{reason}|hwnd={hwnd}|title={title[:40]!r}"
            f"|{ocr_det}|preview={preview!r}"
        )
        method = classify_auth_ocr_text(text, window_title=title)
        if method:
            ms = int((time.monotonic() - t0) * 1000)
            return method, text or "", f"hit:{method}|{'|'.join(parts)}|ms={ms}"

    ms = int((time.monotonic() - t0) * 1000)
    return None, "", f"miss|{'|'.join(parts)}|ms={ms}"


def enrich_sample_with_auth_ocr(sample: Any) -> tuple[Any, str]:
    """
    If UIA sample is not already auth, try OCR and merge text into sample.

    Returns ``(sample_or_new, detail)``. Detail empty when OCR was skipped.
    """
    from app.util.browser_address import (
        BrowserPageSample,
        detect_signin_method,
        looks_like_passkey_os_prompt,
    )

    url = getattr(sample, "url", "") if sample is not None else ""
    title = getattr(sample, "window_title", "") if sample is not None else ""
    ui = getattr(sample, "ui_text", "") if sample is not None else ""
    method = detect_signin_method(url or "", window_title=title or "", ui_text=ui or "")
    if method in ("passkey", "github_2fa", "apple", "google", "google_blocked"):
        return sample, ""
    if looks_like_passkey_os_prompt(title or "", ui or ""):
        return sample, ""
    if looks_like_github_sudo_passkey(title or "", ui or ""):
        return sample, ""
    if looks_like_device_email_verify(title or "", ui or ""):
        return sample, ""

    ocr_method, ocr_text, detail = read_auth_screen_ocr()
    if not ocr_method:
        return sample, detail or "ocr-miss"

    merged_ui = (ui or "").rstrip()
    if ocr_text:
        merged_ui = f"{merged_ui}\n{ocr_text}".strip() if merged_ui else ocr_text
    src = getattr(sample, "source", "") if sample is not None else ""
    new_src = f"{src}+ocr-{ocr_method}" if src else f"ocr-{ocr_method}"
    if sample is None:
        sample = BrowserPageSample(
            url=url or "",
            window_title=title or "",
            ui_text=merged_ui,
            source=new_src,
        )
    else:
        sample = BrowserPageSample(
            url=url or "",
            window_title=title or "",
            ui_text=merged_ui,
            source=new_src,
        )
    return sample, f"ocr-{ocr_method}|{detail}"
