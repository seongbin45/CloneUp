"""
Experimental: fill GitHub Device Flow code with Playwright.

Enable only when:
  CLONEUP_PLAYWRIGHT=1

Requires:
  pip install playwright
  playwright install chromium

Based on a saved snapshot of /login/device/select_account (Device Activation):
  - page title area "Device Activation"
  - submit: input.btn-primary[type=submit][value=Continue]
    or input[aria-label^="Continue as"]
  - then typically /login/device for user_code entry (not in the zip; selectors are defensive)

On any failure, returns False so the caller falls back to manual browser + clipboard.
"""

from __future__ import annotations

import os
import re
import time
from urllib.parse import quote


def playwright_enabled() -> bool:
    v = (os.getenv("CLONEUP_PLAYWRIGHT") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def try_playwright_device_fill(
    user_code: str,
    verification_uri: str,
    *,
    headless: bool = False,
    timeout_ms: int = 120_000,
) -> bool:
    """
    Open Chromium, handle select_account Continue, fill user_code if present.

    Returns True if we believe the code was submitted (or only Continue was needed
    and page advanced). False → use manual path.
    """
    try:
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright 미설치 — 수동 로그인으로 진행합니다.\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install playwright\n"
            "  .\\.venv\\Scripts\\python.exe -m playwright install chromium\n"
            "  set CLONEUP_PLAYWRIGHT=1"
        )
        return False

    base = (verification_uri or "https://github.com/login/device").rstrip("?&")
    # Start at device page with code in query (best effort) OR select_account
    start = base
    if "user_code=" not in start:
        sep = "&" if "?" in start else "?"
        start = f"{start}{sep}user_code={quote(user_code, safe='-')}"

    print(f"Playwright 실험: {start}")
    print(f"  user_code={user_code}  headless={headless}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            page.goto(start, wait_until="domcontentloaded")

            # --- step: select_account (from provided HTML snapshot) ---
            _maybe_click_continue_as(page)

            # --- step: enter user code (defensive selectors) ---
            filled = _maybe_fill_user_code(page, user_code)
            if filled:
                _maybe_submit_code(page)
                print("Playwright: 코드 입력·제출 시도 완료")
            else:
                # Maybe still on select_account only, or already past code
                print("Playwright: 코드 입력란을 못 찾음 — Continue 만 처리했을 수 있음")

            # --- step: authorize app if button visible ---
            _maybe_click_authorize(page)

            # Leave browser open briefly so user can finish passkey / authorize
            # if automation could not complete every step.
            print(
                "Playwright: 브라우저를 잠시 열어둡니다. "
                "Authorize / passkey 가 남았으면 직접 완료하세요."
            )
            # Keep open ~45s while poll continues in main thread... 
            # Actually run_device_flow polls after this returns; keep browser open
            # by not closing immediately — poll happens outside. Close after short wait
            # or leave open until process ends.
            deadline = time.time() + 90
            while time.time() < deadline:
                # if redirected away from login/device, success likely
                url = page.url
                if "/login/device" not in url and "oauth" not in url.lower():
                    # might have finished
                    pass
                if "error" in url.lower():
                    print(f"Playwright: 오류 URL 감지 {url}")
                    break
                time.sleep(1)
                # user may close window
                if page.is_closed():
                    break

            context.close()
            browser.close()
            return filled or True  # Continue-only still counts as "attempted assist"
    except Exception as e:
        print(f"Playwright 실패 → 수동 경로: {type(e).__name__}: {e}")
        return False


def _maybe_click_continue_as(page) -> bool:
    """
    Snapshot: Device Activation +
      <input class="btn btn-sm btn-primary" type="submit" value="Continue"
             aria-label="Continue as seongbin45" />
    """
    candidates = [
        'input[type="submit"][value="Continue"]',
        'input.btn-primary[type="submit"]',
        'input[aria-label^="Continue as"]',
        'button:has-text("Continue")',
        'input[type="submit"][value^="Continue"]',
    ]
    for sel in candidates:
        loc = page.locator(sel)
        try:
            if loc.count() > 0 and loc.first.is_visible():
                print(f"Playwright: select_account Continue 클릭 ({sel})")
                loc.first.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(0.5)
                return True
        except Exception:
            continue
    # role-based
    try:
        btn = page.get_by_role("button", name=re.compile(r"Continue", re.I))
        if btn.count() > 0:
            print("Playwright: Continue (role) 클릭")
            btn.first.click()
            page.wait_for_load_state("domcontentloaded")
            return True
    except Exception:
        pass
    return False


def _maybe_fill_user_code(page, user_code: str) -> bool:
    selectors = [
        'input[name="user_code"]',
        "input#user_code",
        'input[autocomplete="one-time-code"]',
        'input[name="otp"]',
        'input[id*="user_code"]',
        'input[name*="user_code"]',
        'input[placeholder*="code" i]',
        'input[type="text"]',
    ]
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() == 0:
                continue
            el = loc.first
            if not el.is_visible():
                continue
            # avoid authenticity_token and other hidden fields
            name = (el.get_attribute("name") or "").lower()
            if name in ("authenticity_token", "utf8", "commit"):
                continue
            el.click()
            el.fill("")
            el.fill(user_code)
            print(f"Playwright: user_code 입력 ({sel})")
            return True
        except Exception:
            continue
    return False


def _maybe_submit_code(page) -> None:
    for sel in (
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Continue")',
        'button:has-text("Next")',
    ):
        loc = page.locator(sel)
        try:
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click()
                page.wait_for_load_state("domcontentloaded")
                print(f"Playwright: 제출 ({sel})")
                return
        except Exception:
            continue


def _maybe_click_authorize(page) -> None:
    for name in (
        re.compile(r"Authorize", re.I),
        re.compile(r"Authorize.*CloneUp", re.I),
        re.compile(r"Continue", re.I),
    ):
        try:
            btn = page.get_by_role("button", name=name)
            if btn.count() > 0 and btn.first.is_visible():
                print(f"Playwright: Authorize/Continue 클릭 시도")
                btn.first.click()
                time.sleep(1)
                return
        except Exception:
            continue
    # green primary authorize often input submit
    try:
        loc = page.locator('input[type="submit"][value*="Authorize"], button:has-text("Authorize")')
        if loc.count() > 0:
            loc.first.click()
            print("Playwright: Authorize submit")
    except Exception:
        pass
