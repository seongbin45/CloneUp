"""Auth-screen OCR classifiers (passkey Confirm access + email device verify)."""

from __future__ import annotations

from pathlib import Path

from app.auth.github_page_stage import (
    GitHubPageStage,
    PageSnapshot,
    detect_github_page_stage,
)
from app.ui.external_pat_guide import classify_browser_sample
from app.util.auth_ocr import (
    classify_auth_ocr_text,
    looks_like_device_email_verify,
    looks_like_github_sudo_passkey,
)
from app.util.browser_address import detect_signin_method

# Phrases observed via WinOCR on the user-provided screenshots.
_PASSKEY_OCR = """
Confirm access
Signed in as @seongbin45
Passkey
When you are ready, authenticate using the button below.
Use passkey
Having problems?
Use GitHub Mobile
Use your authenticator app
Send a code via email
Tip: You are entering sudo mode. After you've performed a sudo-protected action
"""

_EMAIL_OCR = """
Device verification
Email
We just sent your authentication code via email to
*@gmail.com The code will expire at 6:56AM KST.
Device Verification Code
Verify
Having trouble verifying via email?
Re-send the authentication code
Try GitHub Mobile for simplified device verification
"""

_VERIFY_DEVICE_OCR = """
Verify your device
Verify with a passkey
Verify with a code
We just sent a code to seongbin***@gmail.com
Enter code
Verify
Resend
"""


def test_classify_passkey_confirm_access_ocr() -> None:
    assert looks_like_github_sudo_passkey("", _PASSKEY_OCR)
    assert classify_auth_ocr_text(_PASSKEY_OCR) == "passkey"
    assert (
        detect_signin_method(
            "https://github.com/settings/tokens/new?scopes=repo",
            window_title="Confirm access",
            ui_text=_PASSKEY_OCR,
        )
        == "passkey"
    )


def test_tokens_new_url_with_sudo_passkey_is_auth_not_reached() -> None:
    """URL alone looks like PAT form; body proves Confirm access + Use passkey."""
    st = detect_github_page_stage(
        PageSnapshot(
            url="https://github.com/settings/tokens/new?scopes=repo&description=CloneUp",
            title="Confirm access",
            html=_PASSKEY_OCR,
        )
    )
    assert st == GitHubPageStage.AUTH_PASSKEY_OS
    kind, idx, meta = classify_browser_sample(
        "https://github.com/settings/tokens/new?scopes=repo",
        window_title="Confirm access",
        ui_text=_PASSKEY_OCR,
    )
    assert kind == "current" and idx == 0
    assert meta.get("method") == "passkey"


def test_classify_device_verification_email_ocr() -> None:
    assert looks_like_device_email_verify("", _EMAIL_OCR)
    assert classify_auth_ocr_text(_EMAIL_OCR) == "github_2fa"
    assert (
        detect_signin_method(
            "https://github.com/sessions/verified-device",
            window_title="Device verification · GitHub",
            ui_text=_EMAIL_OCR,
        )
        == "github_2fa"
    )
    kind, idx, meta = classify_browser_sample(
        "https://github.com/sessions/verified-device",
        window_title="Device verification · GitHub",
        ui_text=_EMAIL_OCR,
    )
    assert kind == "current" and idx == 0
    assert meta.get("method") == "github_2fa"


def test_classify_verify_your_device_variant() -> None:
    assert looks_like_device_email_verify("Verify your device · GitHub", _VERIFY_DEVICE_OCR)
    assert classify_auth_ocr_text(_VERIFY_DEVICE_OCR, window_title="Verify your device") == (
        "github_2fa"
    )


def test_plain_tokens_new_still_token_stage() -> None:
    """Without Confirm access body, tokens/new stays the PAT form."""
    st = detect_github_page_stage(
        PageSnapshot(
            url="https://github.com/settings/tokens/new?scopes=repo",
            title="New personal access token (classic)",
            html="Note Expiration Generate token repo",
        )
    )
    assert st == GitHubPageStage.TOKEN_CLASSIC_NEW


def test_live_screenshot_ocr_if_present() -> None:
    """Optional: run real OCR on user screenshots when files exist."""
    from PIL import Image

    from app.util.expiry_ocr import ocr_image_windows, windows_ocr_available

    if not windows_ocr_available():
        return

    passkey_path = Path(r"C:\Users\seong\Pictures\Screenshots") / (
        "스크린샷 2026-08-22 113041.png"
    )
    email_path = Path(r"C:\Users\seong\Downloads") / (
        "session-attachment-2026-09-02-055832.png"
    )
    if passkey_path.is_file():
        img = Image.open(passkey_path).convert("RGB")
        w, h = img.size
        crop = img.crop((int(w * 0.15), int(h * 0.1), int(w * 0.85), int(h * 0.9)))
        text, _ = ocr_image_windows(crop)
        assert classify_auth_ocr_text(text) == "passkey", text[:200]
    if email_path.is_file():
        img = Image.open(email_path).convert("RGB")
        w, h = img.size
        crop = img.crop((int(w * 0.15), int(h * 0.08), int(w * 0.85), int(h * 0.95)))
        text, _ = ocr_image_windows(crop)
        assert classify_auth_ocr_text(text) == "github_2fa", text[:200]
