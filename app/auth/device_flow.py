"""GitHub OAuth 2.0 Device Authorization Grant (no embedded browser)."""

from __future__ import annotations

import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass

import requests

DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "CloneUp-spike/0.1",
}


class DeviceFlowError(Exception):
    """Device Flow failed in a way the user should see."""


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


def poll_for_token(
    client_id: str,
    device_code: str,
    interval: int,
    expires_in: int,
    *,
    on_pending: Callable[[float], None] | None = None,
) -> TokenResponse:
    """
    Poll until token or timeout.

    on_pending(seconds_remaining) is called before each sleep while waiting.
    Handles slow_down by increasing the poll interval (+5s per GitHub guidance).
    """
    deadline = time.monotonic() + expires_in
    sleep_s = interval

    while time.monotonic() < deadline:
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
            time.sleep(sleep_s)
            continue
        if err == "slow_down":
            # GitHub: increase interval when rate-limited on polling.
            sleep_s += 5
            if on_pending:
                on_pending(remaining)
            time.sleep(sleep_s)
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


def run_device_flow(
    client_id: str,
    scope: str = "repo",
    *,
    open_browser: bool = True,
) -> TokenResponse:
    """Full Device Flow: code → browser → poll → access token."""
    dc = request_device_code(client_id, scope)

    print()
    print("=" * 50)
    print("  GitHub 로그인 (Device Flow)")
    print("=" * 50)
    print("  1) 브라우저가 열리면 로그인하세요 (이미 되어 있으면 바로 다음).")
    print("  2) 아래 코드를 입력하세요:")
    print()
    print(f"      >>>  {dc.user_code}  <<<")
    print()
    print(f"  확인 URL: {dc.verification_uri}")
    print(f"  유효 시간: 약 {format_remaining(dc.expires_in)}")
    print("=" * 50)
    print()

    if open_browser:
        # App only opens the system browser — no password, no webview.
        webbrowser.open(dc.verification_uri)

    def _pending(remaining: float) -> None:
        print(f"  승인 대기 중… ({format_remaining(remaining)} 남음)", flush=True)

    return poll_for_token(
        client_id,
        dc.device_code,
        dc.interval,
        dc.expires_in,
        on_pending=_pending,
    )
