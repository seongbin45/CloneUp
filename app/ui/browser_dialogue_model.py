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


def scope_query_value(label: str) -> str:
    for lab, scopes, _rec in SCOPE_OPTIONS:
        if lab == label:
            return scopes
    return "repo"


def expires_at_for_chip(label: str) -> str:
    """ISO Z or ``none`` for keyring (chosen at chip time, not scraped)."""
    days = expiry_days_value(label)
    got = parse_expires_label(days, label)
    return got or "none"


def scene_copy(scene: DialogueScene, *, expiry_label: str = "90일") -> SceneCopy:
    if scene == DialogueScene.LOGIN_WAIT:
        return SceneCopy(
            right_tag="1 / 3",
            say="로그인만 해주시면 돼요",
            sub="브라우저를 열어 두었습니다. 편한 방법으로 로그인해 주세요. 나머지는 제가 합니다.",
            foot_note="비밀번호는 저를 거치지 않아요",
            wait_text="로그인이 끝나는 것을 지켜보고 있어요.",
        )
    if scene == DialogueScene.AUTH_WAIT:
        return SceneCopy(
            right_tag="1 / 3",
            say="이건 직접 확인해 주세요",
            sub="패스키 창이 떴습니다. 제가 대신 누를 수 없는 부분이라 잠시 기다릴게요.",
            foot_note="이메일 코드도 같은 방식이에요",
            wait_text="확인이 끝나면 알아서 이어갑니다.",
        )
    if scene == DialogueScene.ASK_EXPIRY:
        return SceneCopy(
            right_tag="2 / 3",
            say="키는 언제까지 쓸까요?",
            sub="짧게 두면 안전하고, 길게 두면 다시 만들 일이 줄어요.",
            foot_note="나중에 설정에서 바꿀 수 있어요",
        )
    if scene == DialogueScene.ASK_SCOPE:
        return SceneCopy(
            right_tag="2 / 3",
            say="권한은 어디까지 줄까요?",
            sub="올리고 받는 데는 저장소만으로 충분합니다.",
            foot_note="워크플로 파일이 있는 저장소만 두 번째가 필요해요",
        )
    if scene == DialogueScene.PRESS_GENERATE:
        exp = expiry_label or "90일"
        return SceneCopy(
            right_tag="3 / 3",
            say="초록 버튼만 눌러 주세요",
            sub=(
                "이름·권한은 채워 두었습니다. "
                f"브라우저(Chrome/Edge) 창만 골라 Expiration을 {exp}으로 "
                "맞춰 볼게요. 커서가 잠깐 움직일 수 있어요. "
                "안 바뀌면 직접 고른 뒤 Generate token을 눌러 주세요."
            ),
            foot_note="누르면 키를 알아서 받아옵니다",
            nudge_text=(
                f"Expiration이 {exp}이 아니면 직접 바꾼 뒤, "
                "아래쪽 Generate token을 눌러 주세요."
            ),
            nudge_btn="버튼이 안 보여요",
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
) -> list[HistoryRow]:
    rows: list[HistoryRow] = []
    if logged_in or int(scene) >= int(DialogueScene.ASK_EXPIRY):
        rows.append(HistoryRow("로그인했어요", editable=False))
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

    Does not skip chip questions — only login/auth → ASK_EXPIRY.
    """
    m = (method or "").strip()
    if kind in ("logged_out",) or m in ("github_logout", "github_logged_out"):
        return DialogueScene.LOGIN_WAIT

    if kind == "rejected" or m == "google_blocked":
        # Stay on login wait; UI shows reopen hint
        return DialogueScene.LOGIN_WAIT if scene != DialogueScene.LOGIN_WAIT else None

    # Auth in progress (passkey / 2FA / apple) — not a failure
    if m in ("passkey", "apple", "github_2fa"):
        if scene in (DialogueScene.LOGIN_WAIT, DialogueScene.AUTH_WAIT):
            return DialogueScene.AUTH_WAIT
        return None
    if kind == "current" and m == "github_login":
        # /sessions/two-factor also maps to github_login — treat as auth wait
        # when idx hints 2FA via meta is unavailable; stay/auth:
        if scene == DialogueScene.LOGIN_WAIT:
            # Keep waiting on login form; 2FA URLs still "current"
            return None
        if scene == DialogueScene.AUTH_WAIT:
            return None
        return None

    # Logged in / on github after auth (home, tokens list/new, …)
    # idx>=1 includes home(1) and token pages(2); both mean "past login".
    if kind == "reached" and idx is not None and idx >= 1:
        if scene in (DialogueScene.LOGIN_WAIT, DialogueScene.AUTH_WAIT):
            return DialogueScene.ASK_EXPIRY
        return None

    return None
