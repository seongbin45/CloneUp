"""Path B optional: control user Chrome/Edge via CDP (Playwright connect_over_cdp).

Enable with ``CLONEUP_CDP=1`` and a Chromium started with
``--remote-debugging-port=9222`` (see :func:`launch_cdp_browser` for a
CloneUp-owned profile so the default User Data lock is avoided).

Soft-fails when Playwright is missing, CDP is off, or the port is closed —
callers fall back to UIA / manual Path B.

Security: probe/connect **localhost only**. Never call ``browser.close()`` on a
CDP session (that would quit the user's browser).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from app.auth.pat_form_js import (
    JS_CLICK_GENERATE_TOKEN,
    JS_READ_EXPIRATION,
    JS_SET_EXPIRATION,
)
from app.util.browser_address import path_b_log

DEFAULT_CDP_HOST = "127.0.0.1"
DEFAULT_CDP_PORT = 9222


def cdp_enabled() -> bool:
    v = (os.getenv("CLONEUP_CDP") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def cdp_endpoint_url(*, host: str = DEFAULT_CDP_HOST, port: int = DEFAULT_CDP_PORT) -> str:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError(f"CDP host must be loopback, got {host!r}")
    return f"http://{host}:{int(port)}"


def probe_cdp_endpoint(
    *, host: str = DEFAULT_CDP_HOST, port: int = DEFAULT_CDP_PORT, timeout_s: float = 1.5
) -> dict | None:
    """
    GET ``/json/version`` on the debug port. Returns parsed JSON or None.

    Refuses non-loopback hosts.
    """
    if host not in ("127.0.0.1", "localhost", "::1"):
        path_b_log(f"[Path B][CDP] 거부: localhost가 아닌 host={host}")
        return None
    url = f"{cdp_endpoint_url(host=host, port=port)}/json/version"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None
    except Exception:
        return None


def cdp_profile_dir() -> Path:
    """``%LOCALAPPDATA%\\CloneUp\\cdp-profile`` (dedicated; not the default Chrome profile)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMP") or tempfile.gettempdir()
    path = Path(base) / "CloneUp" / "cdp-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_chromium_executable() -> Path | None:
    """Best-effort Chrome / Edge path on Windows (then common mac/linux names)."""
    env = os.environ
    candidates: list[Path] = []
    if sys.platform == "win32":
        pf = env.get("PROGRAMFILES") or r"C:\Program Files"
        pf86 = env.get("PROGRAMFILES(X86)") or r"C:\Program Files (x86)"
        local = env.get("LOCALAPPDATA") or ""
        candidates.extend(
            [
                Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(pf86) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(pf86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(local) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            ]
        )
    else:
        for name in (
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
            "microsoft-edge",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ):
            candidates.append(Path(name))
    for p in candidates:
        try:
            if p.is_file():
                return p
        except Exception:
            continue
    return None


def launch_cdp_browser(
    *,
    port: int = DEFAULT_CDP_PORT,
    start_url: str = "https://github.com/login",
) -> tuple[bool, str]:
    """
    Start Chrome/Edge with remote debugging + CloneUp-owned profile.

    Does **not** touch the user's default profile and does not kill existing
    Chrome processes.
    """
    exe = find_chromium_executable()
    if exe is None:
        path_b_log("[Path B][CDP] Chrome/Edge 실행 파일을 못 찾음")
        return False, "browser-exe-not-found"
    profile = cdp_profile_dir()
    args = [
        str(exe),
        f"--remote-debugging-port={int(port)}",
        f"--remote-debugging-address={DEFAULT_CDP_HOST}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        start_url,
    ]
    try:
        kwargs: dict = {}
        if sys.platform == "win32":
            # Visible browser window; do not CREATE_NO_WINDOW.
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        subprocess.Popen(args, close_fds=sys.platform != "win32", **kwargs)
        path_b_log(
            f"[Path B][CDP] 제어용 브라우저 기동 port={port} profile={profile}"
        )
        return True, f"launched:{exe.name}|port={port}"
    except Exception as e:
        path_b_log(f"[Path B][CDP] 기동 실패: {e}")
        return False, f"launch-fail:{e}"


def _page_pat_score(url: str, title: str) -> int:
    u = (url or "").lower()
    t = (title or "").lower()
    score = 0
    if "github.com" in u:
        score += 20
    if "/settings/tokens" in u:
        score += 40
    if "tokens/new" in u or "personal-access-tokens" in u:
        score += 30
    if "new personal access token" in t:
        score += 50
    elif "personal access token" in t:
        score += 25
    if "token" in t:
        score += 5
    return score


def _iter_cdp_pages(browser) -> list:
    pages = []
    try:
        for ctx in browser.contexts:
            for page in ctx.pages:
                pages.append(page)
    except Exception:
        return []
    return pages


def _pick_pat_page(browser):
    """Only pages that look like classic PAT create/list settings.

    Requires a strong score (≥40): ``/settings/tokens`` URL and/or
    \"New Personal Access Token\" title. Avoids evaluating form JS on
    arbitrary github.com tabs (login/home).
    """
    best = None
    best_score = -1
    for page in _iter_cdp_pages(browser):
        try:
            url = page.url or ""
            title = page.title() or ""
        except Exception:
            continue
        score = _page_pat_score(url, title)
        if score > best_score:
            best_score = score
            best = page
    if best is not None and best_score >= 40:
        return best
    return None


def wait_for_cdp_ready(
    *,
    host: str = DEFAULT_CDP_HOST,
    port: int = DEFAULT_CDP_PORT,
    attempts: int = 15,
    interval_s: float = 0.4,
) -> bool:
    """Poll ``/json/version`` until the debug port answers (or give up)."""
    import time

    for i in range(max(1, int(attempts))):
        if probe_cdp_endpoint(host=host, port=port) is not None:
            if i > 0:
                path_b_log(f"[Path B][CDP] 포트 ready ({i + 1}회 시도)")
            return True
        time.sleep(max(0.05, float(interval_s)))
    path_b_log("[Path B][CDP] 포트 ready 대기 시간 초과")
    return False


def _with_cdp_browser(fn):
    """Connect, run ``fn(browser)``, never close the user browser."""
    if not cdp_enabled():
        return False, "cdp-disabled"
    info = probe_cdp_endpoint()
    if info is None:
        return False, "cdp-not-listening"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        path_b_log(
            "[Path B][CDP] Playwright 미설치 — "
            "pip install playwright 후 CLONEUP_CDP=1"
        )
        return False, "playwright-missing"

    endpoint = cdp_endpoint_url()
    path_b_log(f"[Path B][CDP] 연결 시도 {endpoint}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint)
            try:
                return fn(browser)
            finally:
                # Do NOT browser.close() — that quits the user's Chrome.
                pass
    except Exception as e:
        path_b_log(f"[Path B][CDP] 연결/실행 오류: {e}")
        return False, f"cdp-error:{e}"


def set_pat_expiration_cdp(days_value: str) -> tuple[bool, str]:
    """Set classic PAT Expiration via DOM on a CDP-attached page."""
    want = (days_value or "90").strip().lower()
    if want in ("", "no-expiration", "never"):
        want = "none"

    def _run(browser) -> tuple[bool, str]:
        page = _pick_pat_page(browser)
        if page is None:
            path_b_log("[Path B][CDP] PAT 폼 탭을 못 찾음")
            return False, "pat-page-not-found"
        try:
            url = page.url or ""
            title = (page.title() or "")[:64]
        except Exception:
            url, title = "", ""
        path_b_log(f"[Path B][CDP] Expiration 시도 want={want} title={title}")
        try:
            result = page.evaluate(f"{JS_SET_EXPIRATION}({want!r})")
        except Exception as e:
            path_b_log(f"[Path B][CDP] evaluate 실패: {e}")
            return False, f"evaluate-fail:{e}"
        detail = str(result or "")
        try:
            got = page.evaluate(JS_READ_EXPIRATION)
            got_s = str(got or "").strip()
        except Exception:
            got_s = ""
        ok = detail.startswith("set-") and (
            got_s == want
            or got_s == ""
            or (want == "none" and got_s in ("", "none"))
        )
        # Hidden write success is enough even if UI label lags.
        if detail.startswith("set-hidden:") or detail.startswith("set-select:"):
            ok = True
        msg = f"{detail}|read={got_s}|url={url[:80]}"
        if ok:
            path_b_log(f"[Path B][CDP] Expiration 성공: {msg}")
            return True, msg
        path_b_log(f"[Path B][CDP] Expiration 실패: {msg}")
        return False, msg

    return _with_cdp_browser(_run)


def click_generate_token_cdp() -> tuple[bool, str]:
    """Click Generate token via DOM on a CDP-attached PAT page."""

    def _run(browser) -> tuple[bool, str]:
        page = _pick_pat_page(browser)
        if page is None:
            path_b_log("[Path B][CDP] Generate: PAT 탭 없음")
            return False, "pat-page-not-found"
        path_b_log("[Path B][CDP] Generate 시도")
        try:
            result = page.evaluate(JS_CLICK_GENERATE_TOKEN)
        except Exception as e:
            path_b_log(f"[Path B][CDP] Generate evaluate 실패: {e}")
            return False, f"evaluate-fail:{e}"
        detail = str(result or "")
        ok = detail.startswith("submitted:") or detail.startswith("clicked:")
        if ok:
            path_b_log(f"[Path B][CDP] Generate 성공: {detail}")
            return True, detail
        path_b_log(f"[Path B][CDP] Generate 실패: {detail}")
        return False, detail

    return _with_cdp_browser(_run)


def try_cdp_expiration_then_uia_fallback(
    days_value: str, *, uia_fallback
) -> tuple[bool, str]:
    """CDP first when enabled; otherwise / on failure call ``uia_fallback(days)``."""
    if cdp_enabled() and probe_cdp_endpoint() is not None:
        ok, detail = set_pat_expiration_cdp(days_value)
        if ok:
            return True, f"cdp:{detail}"
        path_b_log(f"[Path B][CDP] → UIA 폴백 (expiry): {detail}")
    return uia_fallback(days_value)


def try_cdp_generate_then_uia_fallback(*, uia_fallback) -> tuple[bool, str]:
    if cdp_enabled() and probe_cdp_endpoint() is not None:
        ok, detail = click_generate_token_cdp()
        if ok:
            return True, f"cdp:{detail}"
        path_b_log(f"[Path B][CDP] → UIA 폴백 (generate): {detail}")
    return uia_fallback()
