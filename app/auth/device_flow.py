"""GitHub OAuth 2.0 Device Authorization Grant (no embedded browser)."""

from __future__ import annotations

import subprocess
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

import requests

DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "CloneUp-spike/0.1",
}


class DeviceFlowError(Exception):
    """Device Flow failed in a way the user should see."""


class DeviceFlowCancelled(DeviceFlowError):
    """User cancelled login (UI or interruption)."""

    def __init__(self, message: str = "로그인이 취소되었습니다.") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class DeviceCodeResponse:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    token_type: str
    scope: str


def format_remaining(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}시간 {m}분 {s}초"
    if m > 0:
        return f"{m}분 {s}초"
    return f"{s}초"


def request_device_code(client_id: str, scope: str) -> DeviceCodeResponse:
    resp = requests.post(
        DEVICE_CODE_URL,
        headers=DEFAULT_HEADERS,
        data={"client_id": client_id, "scope": scope},
        timeout=30,
    )
    try:
        data = resp.json()
    except ValueError as e:
        raise DeviceFlowError(
            f"device/code: non-JSON response HTTP {resp.status_code}: {resp.text[:200]}"
        ) from e

    if resp.status_code >= 400 or "error" in data:
        err = data.get("error", f"http_{resp.status_code}")
        desc = data.get("error_description") or data.get("error_uri") or resp.text[:300]
        hint = ""
        if resp.status_code == 400 or err in ("unauthorized_client", "invalid_client"):
            hint = (
                "\n힌트: OAuth App 설정에서 'Enable Device Flow'가 켜져 있는지 확인하세요."
            )
        raise DeviceFlowError(f"device/code 실패: {err} — {desc}{hint}")

    required = ("device_code", "user_code", "verification_uri", "expires_in", "interval")
    missing = [k for k in required if k not in data]
    if missing:
        raise DeviceFlowError(f"device/code 응답 필드 누락: {missing}")

    return DeviceCodeResponse(
        device_code=data["device_code"],
        user_code=data["user_code"],
        verification_uri=data["verification_uri"],
        expires_in=int(data["expires_in"]),
        interval=max(1, int(data["interval"])),
    )


def _interruptible_sleep(
    seconds: float,
    *,
    should_cancel: Callable[[], bool] | None = None,
    slice_s: float = 0.25,
) -> None:
    """Sleep in short slices so UI cancel can stop polling quickly."""
    end = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < end:
        if should_cancel and should_cancel():
            raise DeviceFlowCancelled()
        time.sleep(min(slice_s, end - time.monotonic()))


def poll_for_token(
    client_id: str,
    device_code: str,
    interval: int,
    expires_in: int,
    *,
    on_pending: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> TokenResponse:
    """
    Poll until token, timeout, or cancel.

    on_pending(seconds_remaining) is called before each sleep while waiting.
    Handles slow_down by increasing the poll interval (+5s per GitHub guidance).
    should_cancel() → DeviceFlowCancelled when the user aborts in the UI.
    """
    deadline = time.monotonic() + expires_in
    sleep_s = interval

    while time.monotonic() < deadline:
        if should_cancel and should_cancel():
            raise DeviceFlowCancelled()

        resp = requests.post(
            ACCESS_TOKEN_URL,
            headers=DEFAULT_HEADERS,
            data={
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=30,
        )
        try:
            data = resp.json()
        except ValueError as e:
            raise DeviceFlowError(
                f"access_token: non-JSON HTTP {resp.status_code}: {resp.text[:200]}"
            ) from e

        if "access_token" in data:
            return TokenResponse(
                access_token=data["access_token"],
                token_type=data.get("token_type", "bearer"),
                scope=data.get("scope", ""),
            )

        remaining = deadline - time.monotonic()
        err = data.get("error", "")
        if err == "authorization_pending":
            if on_pending:
                on_pending(remaining)
            _interruptible_sleep(sleep_s, should_cancel=should_cancel)
            continue
        if err == "slow_down":
            # GitHub: increase interval when rate-limited on polling.
            sleep_s += 5
            if on_pending:
                on_pending(remaining)
            _interruptible_sleep(sleep_s, should_cancel=should_cancel)
            continue
        if err == "expired_token":
            raise DeviceFlowError("인증 코드가 만료되었습니다. 다시 실행하세요.")
        if err == "access_denied":
            raise DeviceFlowError("사용자가 브라우저에서 승인을 거부했습니다.")
        if err == "unsupported_grant_type":
            raise DeviceFlowError(
                "Device Flow grant가 거부되었습니다. OAuth App의 Device Flow 설정을 확인하세요."
            )

        desc = data.get("error_description") or data
        raise DeviceFlowError(f"토큰 폴링 실패: {err or resp.status_code} — {desc}")

    raise DeviceFlowError("시간 초과: 브라우저에서 승인하지 않았습니다.")


def copy_text_to_clipboard(text: str) -> bool:
    """Best-effort clipboard copy (Windows clip.exe, or Qt if an app exists)."""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.clipboard().setText(text)
            return True
    except Exception:
        pass
    try:
        # Windows: clip.exe reads stdin
        r = subprocess.run(
            ["clip"],
            input=text,
            text=True,
            check=False,
            capture_output=True,
        )
        return r.returncode == 0
    except Exception:
        return False


def verification_open_url(verification_uri: str, user_code: str) -> str:
    """
    Prefer a URL that may pre-fill the user code.

    GitHub's documented verification_uri is https://github.com/login/device only;
    some clients append ?user_code= — if GitHub ignores it, user can still paste
    from clipboard. We never drive github.com DOM (no webview automation).
    """
    base = (verification_uri or "https://github.com/login/device").rstrip("?&")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}user_code={quote(user_code, safe='-')}"


def run_device_flow(
    client_id: str,
    scope: str = "repo",
    *,
    open_browser: bool = True,
    copy_code: bool = True,
    on_user_code: Callable[[str, str, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> TokenResponse:
    """
    Full Device Flow: code → browser → poll → access token.

    on_user_code(user_code, verification_uri, expires_in):
        Called on the same thread as run_device_flow (often a QThread).
        GUI should emit a Qt signal from here to show a modal on the UI thread.
        When provided, GUI typically sets open_browser=False and copy_code=False
        so the dialog can open the browser and copy on the main thread.

    should_cancel():
        Polled during waits; raise DeviceFlowCancelled when True (UI cancel).
    """
    if should_cancel and should_cancel():
        raise DeviceFlowCancelled()

    dc = request_device_code(client_id, scope)
    open_url = verification_open_url(dc.verification_uri, dc.user_code)

    if should_cancel and should_cancel():
        raise DeviceFlowCancelled()

    if on_user_code is not None:
        on_user_code(dc.user_code, dc.verification_uri, dc.expires_in)

    copied = False
    if copy_code:
        copied = copy_text_to_clipboard(dc.user_code)

    print()
    print("=" * 50)
    print("  GitHub 로그인 (Device Flow)")
    print("=" * 50)
    print("  1) 브라우저가 열리면 계정 선택·로그인하세요.")
    print("  2) 장치 코드 입력란에 아래 코드를 넣으세요:")
    print()
    print(f"      >>>  {dc.user_code}  <<<")
    print()
    if copy_code:
        if copied:
            print("  (코드가 클립보드에 복사되었습니다 → 입력란에서 Ctrl+V)")
        else:
            print("  (클립보드 복사 실패 — 위 코드를 직접 입력하세요)")
    else:
        print("  (GUI 팝업에서 복사·브라우저 열기를 처리합니다)")
    print()
    print(f"  확인 URL: {dc.verification_uri}")
    print(f"  연 주소(코드 포함 시도): {open_url}")
    print(f"  유효 시간: 약 {format_remaining(dc.expires_in)}")
    print()
    print("  기본: 수동 승인 (권장).")
    print("  실험: CLONEUP_PLAYWRIGHT=1 이면 Playwright가 Continue/코드 입력을 시도.")
    print("=" * 50)
    print()

    used_playwright = False
    try:
        from app.auth.playwright_device import playwright_enabled, try_playwright_device_fill

        # Only auto-run Playwright when we're also driving the browser ourselves.
        if playwright_enabled() and open_browser:
            print("CLONEUP_PLAYWRIGHT=1 — Playwright 실험 경로 시도…")
            used_playwright = try_playwright_device_fill(
                dc.user_code,
                dc.verification_uri,
                headless=False,
            )
            if not used_playwright:
                print("Playwright 실패 → 기본 브라우저 + 수동 입력으로 폴백")
    except Exception as e:
        print(f"Playwright 경로 예외 → 폴백: {e}")
        used_playwright = False

    if open_browser and not used_playwright:
        # System browser only — no embedded webview.
        webbrowser.open(open_url)

    def _pending(remaining: float) -> None:
        print(f"  승인 대기 중… ({format_remaining(remaining)} 남음)", flush=True)

    return poll_for_token(
        client_id,
        dc.device_code,
        dc.interval,
        dc.expires_in,
        on_pending=_pending,
        should_cancel=should_cancel,
    )
