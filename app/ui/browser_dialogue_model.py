"""Path B conversational guide — pure scene model (no Qt).

시안: ``desin/CloneUp 브라우저 안내 대화형.dc.html``
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from app.auth.token_expiry import parse_expires_label


class DialogueScene(IntEnum):
    LOGIN_WAIT = 0
    AUTH_WAIT = 1
    ASK_EXPIRY = 2
    ASK_SCOPE = 3
    PRESS_GENERATE = 4
    DONE = 5


# Chip labels (UI) → storage / GitHub
EXPIRY_OPTIONS: tuple[tuple[str, str, bool], ...] = (
    # label, days_value for parse_expires_label, recommended
    ("90일", "90", True),
    ("30일", "30", False),
    ("만료 없음", "none", False),
)

SCOPE_OPTIONS: tuple[tuple[str, str, bool], ...] = (
    # label, scopes query, recommended
    ("저장소만", "repo", True),
    ("저장소 + 워크플로", "repo,workflow", False),
)


@dataclass(frozen=True)
class SceneCopy:
    right_tag: str
    say: str
    sub: str
    foot_note: str
    wait_text: str = ""
    nudge_text: str = ""
    nudge_btn: str = ""
    show_cancel: bool = True


@dataclass(frozen=True)
class HistoryRow:
    text: str
    editable: bool
    back_to: DialogueScene | None = None


def expiry_days_value(label: str) -> str:
    for lab, days, _rec in EXPIRY_OPTIONS:
        if lab == label:
            return days
    return "90"


def expiry_label_for_days(days: str) -> str | None:
    """Map UIA/read-back days token (``90``, ``none``, ``YYYY-MM-DD``, …) → label."""
    import re

    want = (days or "").strip().lower()
    if want in ("", "no-expiration", "never"):
        want = "none"
    for lab, d, _rec in EXPIRY_OPTIONS:
        if d == want:
            return lab
    # GitHub also offers 7 / 60 — keep a readable label for receipt.
    if want.isdigit():
        return f"{want}일"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", want):
        return want
    return None


def scope_query_value(label: str) -> str:
    for lab, scopes, _rec in SCOPE_OPTIONS:
        if lab == label:
            return scopes
    return "repo"


def expires_at_for_chip(label: str) -> str:
    """ISO Z or ``none`` from a hint chip (fallback when UIA read fails)."""
    days = expiry_days_value(label)
    got = parse_expires_label(days, label)
    return got or "none"


def expires_at_for_days(days: str) -> str:
    """ISO Z or ``none`` from a UIA days token (browser is source of truth)."""
    got = parse_expires_label((days or "").strip(), "")
    return got or "none"


def _auth_wait_copy(auth_method: str = "") -> SceneCopy:
    """
    AUTH_WAIT copy tailored to the live browser/OS prompt.

    - ``passkey``: Windows 보안 「패스키로 로그인」 (QR / 이 디바이스)
    - ``github_2fa``: GitHub 「Verify your device」 email code
    - else: short combined hint
    """
    m = (auth_method or "").strip().lower()
    if m == "passkey":
        return SceneCopy(
            right_tag="2 / 4",
            say="패스키로 확인해 주세요",
            sub=(
                "「Windows 보안」창이 떴습니다. "
                "휴대폰으로 QR을 스캔하거나, 「이 디바이스」에서 확인하세요. "
                "이 단계는 제가 대신 누를 수 없어요."
            ),
            foot_note="확인이 끝나면 키 만들기로 이어져요",
            wait_text="패스키 확인이 끝나는 것을 지켜보고 있어요.",
        )
    if m in ("github_2fa", "email", "device"):
        return SceneCopy(
            right_tag="2 / 4",
            say="이메일 인증 코드를 입력해 주세요",
            sub=(
                "GitHub 「Verify your device」화면입니다. "
                "이메일로 온 숫자 코드를 칸에 입력하세요. "
                "패스키로 확인할 수도 있어요. "
                "이 단계가 끝나기 전에 키 화면으로 가면 다시 로그인으로 돌아옵니다."
            ),
            foot_note="확인이 끝나면 키 만들기로 이어져요",
            wait_text="이메일 인증이 끝나는 것을 지켜보고 있어요.",
        )
    if m == "apple":
        return SceneCopy(
            right_tag="2 / 4",
            say="Apple 로그인을 끝내 주세요",
            sub="Apple 로그인 창에서 확인을 마치면 GitHub으로 돌아옵니다.",
            foot_note="확인이 끝나면 키 만들기로 이어져요",
            wait_text="Apple 확인이 끝나는 것을 지켜보고 있어요.",
        )
    if m == "google":
        return SceneCopy(
            right_tag="2 / 4",
            say="Google 로그인을 끝내 주세요",
            sub="Google 로그인 창에서 확인을 마치면 GitHub으로 돌아옵니다.",
            foot_note="확인이 끝나면 키 만들기로 이어져요",
            wait_text="Google 확인이 끝나는 것을 지켜보고 있어요.",
        )
    return SceneCopy(
        right_tag="2 / 4",
        say="이메일·패스키 인증을 끝내 주세요",
        sub=(
            "거의 항상 한 번 더 확인합니다. "
            "이메일 코드(Verify your device) 또는 "
            "Windows 패스키(QR·이 디바이스)로 확인해 주세요. "
            "끝나기 전에 키 만들기 화면으로 가면 다시 로그인으로 돌아옵니다."
        ),
        foot_note="확인이 끝나면 키 만들기로 이어져요",
        wait_text="인증이 끝나는 것을 지켜보고 있어요.",
    )


def scene_copy(
    scene: DialogueScene,
    *,
    expiry_label: str = "90일",
    auth_method: str = "",
) -> SceneCopy:
    if scene == DialogueScene.LOGIN_WAIT:
        return SceneCopy(
            right_tag="1 / 4",
            say="로그인만 해주시면 돼요",
            sub=(
                "브라우저를 열어 두었습니다. 편한 방법으로 로그인해 주세요. "
                "곧 이메일 코드나 패스키 확인이 이어질 수 있어요."
            ),
            foot_note="비밀번호는 저를 거치지 않아요",
            wait_text="로그인이 끝나는 것을 지켜보고 있어요.",
        )
    if scene == DialogueScene.AUTH_WAIT:
        return _auth_wait_copy(auth_method)
    if scene == DialogueScene.ASK_EXPIRY:
        exp = (expiry_label or "").strip()
        if exp:
            sub = f"브라우저에서 읽은 만료일: {exp}"
        else:
            sub = (
                "GitHub에서 Expiration을 골라 주세요. "
                "고르신 만료일이 여기에 표시됩니다."
            )
        return SceneCopy(
            right_tag="3 / 4",
            say="브라우저에서 만료일을 골라 주세요",
            sub=sub,
            foot_note="맞으면 「골랐어요」를 눌러 주세요",
        )
    if scene == DialogueScene.ASK_SCOPE:
        return SceneCopy(
            right_tag="3 / 4",
            say="권한 체크를 확인해 주세요",
            sub=(
                "Select scopes에서 저장소(repo)가 켜져 있는지 보세요. "
                "워크플로 파일이 있으면 workflow도 함께 체크하세요."
            ),
            foot_note="확인 후 「확인했어요」를 눌러 주세요",
        )
    if scene == DialogueScene.PRESS_GENERATE:
        exp = expiry_label or "직접 선택"
        return SceneCopy(
            right_tag="4 / 4",
            say="초록 Generate token만 눌러 주세요",
            sub=(
                "이름(Note)은 채워 두었습니다. "
                f"만료일은 브라우저에서 고른 값({exp}) 그대로 둡니다. "
                "초록 버튼만 누르면 키를 받아올게요."
            ),
            foot_note="누르면 키를 알아서 받아옵니다",
            nudge_text=(
                "Generate token이 안 보이면 페이지를 아래로 내린 뒤 눌러 주세요. "
                "도움이 필요하면 「도와주세요」를 눌러 주세요."
            ),
            nudge_btn="도와주세요",
        )
    return SceneCopy(
        right_tag="끝",
        say="연결됐어요",
        sub="키는 이 컴퓨터에만 넣어 두었습니다. 복사하거나 적어 둘 필요 없어요.",
        foot_note="",
        show_cancel=False,
    )


def build_history(
    scene: DialogueScene,
    *,
    expiry_label: str | None,
    scope_label: str | None,
    logged_in: bool,
    got_token: bool,
    auth_done: bool = False,
) -> list[HistoryRow]:
    rows: list[HistoryRow] = []
    if logged_in or auth_done or int(scene) >= int(DialogueScene.AUTH_WAIT):
        rows.append(HistoryRow("로그인했어요", editable=False))
    if auth_done or int(scene) >= int(DialogueScene.ASK_EXPIRY):
        rows.append(HistoryRow("이메일·패스키 인증했어요", editable=False))
    if expiry_label and int(scene) >= int(DialogueScene.ASK_SCOPE):
        rows.append(
            HistoryRow(
                f"만료 {expiry_label}",
                editable=True,
                back_to=DialogueScene.ASK_EXPIRY,
            )
        )
    if scope_label and int(scene) >= int(DialogueScene.PRESS_GENERATE):
        rows.append(
            HistoryRow(
                f"권한 {scope_label}",
                editable=True,
                back_to=DialogueScene.ASK_SCOPE,
            )
        )
    if got_token or scene == DialogueScene.DONE:
        rows.append(HistoryRow("키를 받았어요", editable=False))
    return rows


def advance_from_browser_kind(
    scene: DialogueScene,
    kind: str,
    idx: int | None,
    *,
    method: str = "",
) -> DialogueScene | None:
    """
    Map classify_browser_sample → next scene, or None if no change.

    Auth (email / passkey / 2FA) is a hard gate before ASK_EXPIRY.
    If the browser falls back to login or 2FA while on a later scene,
    bounce to AUTH_WAIT / LOGIN_WAIT so we do not keep a dead token page.
    """
    m = (method or "").strip()
    past_key_steps = int(scene) >= int(DialogueScene.ASK_EXPIRY)

    if kind in ("logged_out",) or m in ("github_logout", "github_logged_out"):
        return DialogueScene.LOGIN_WAIT

    if kind == "rejected" or m == "google_blocked":
        return DialogueScene.LOGIN_WAIT if scene != DialogueScene.LOGIN_WAIT else None

    # Auth in progress — always park on AUTH_WAIT (even if we had jumped ahead).
    if m in ("passkey", "apple", "github_2fa", "google"):
        if scene != DialogueScene.AUTH_WAIT:
            return DialogueScene.AUTH_WAIT
        return None

    # Still on GitHub password / username login form
    if kind == "current" and m == "github_login":
        if past_key_steps:
            # Token URL bounced to password login — start over at login step.
            return DialogueScene.LOGIN_WAIT
        return None

    if kind == "current":
        if past_key_steps:
            return DialogueScene.AUTH_WAIT
        return None

    # Fully past auth: home / token pages. Only then leave AUTH / LOGIN.
    if kind == "reached" and idx is not None and idx >= 1:
        if scene in (DialogueScene.LOGIN_WAIT, DialogueScene.AUTH_WAIT):
            return DialogueScene.ASK_EXPIRY
        return None

    return None
