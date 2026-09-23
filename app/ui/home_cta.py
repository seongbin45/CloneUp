"""Home detail CTA state machine (P4a) — pure, no Qt.

SSOT: desin/CloneUp 홈.dc.html renderVals branches.
X-1: signed-out prefix also on 「GitHub에 올리기 시작」 (intentional SSOT exception).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

CtaVariant = Literal["primary", "normal", "quiet"]


class ProjectKind(str, Enum):
    NO_GIT = "no_git"
    NO_REMOTE = "no_remote"  # has .git but no origin
    NOT_MINE = "not_mine"
    DIRTY = "dirty"
    CLEAN = "clean"


class CtaActionId(str, Enum):
    PUBLISH_START = "publish_start"
    OPEN_FOLDER = "open_folder"
    FORK_COPY = "fork_copy"
    PULL = "pull"
    PUSH = "push"
    HISTORY = "history"
    LOGIN = "login"  # when primary is login-prefixed, click still runs underlying id


@dataclass(frozen=True)
class CtaAction:
    label: str
    variant: CtaVariant
    action_id: CtaActionId


@dataclass(frozen=True)
class CtaPlan:
    kind: ProjectKind
    subtitle: str
    actions: tuple[CtaAction, ...]
    note: str | None
    """True when X-1/signed-out prefix was applied to primary."""
    signed_out_prefix: bool = False


# Labels that receive 「로그인하고 」 when signed out (시안 need + X-1).
_PREFIX_LABELS = frozenset(
    {
        "올리기",
        "받아오기",
        "내 사본 만들기",
        "GitHub에 올리기 시작",  # X-1
    }
)

_NOTE_NO_GIT = (
    "이 폴더는 아직 GitHub와 연결되지 않았습니다. "
    "처음 올릴 때 공개 여부를 고르시게 됩니다."
)
_NOTE_NO_REMOTE = (
    "로컬 Git은 있지만 GitHub 주소(origin)가 없습니다. "
    "처음 올릴 때 저장소 이름·공개 여부를 고릅니다."
)
_NOTE_NOT_MINE = (
    "다른 사람의 저장소입니다. "
    "여기에 직접 올릴 수는 없고, 사본을 만들어 제안할 수 있습니다."
)


def home_project_kind(
    *,
    has_git: bool,
    is_mine: bool | None = True,
    dirty: bool | None = False,
    has_origin: bool | None = True,
) -> ProjectKind:
    """Classify project for detail CTA.

    Order: !git → no origin → !mine → dirty → clean.
    ``has_origin is None`` (unknown) does **not** select NO_REMOTE.
    ``is_mine is None`` (unknown) is treated as mine — never NOT_MINE.
    """
    if not has_git:
        return ProjectKind.NO_GIT
    if has_origin is False:
        return ProjectKind.NO_REMOTE
    if is_mine is False:
        return ProjectKind.NOT_MINE
    if dirty:
        return ProjectKind.DIRTY
    return ProjectKind.CLEAN


def _plan_for_kind(kind: ProjectKind) -> CtaPlan:
    if kind is ProjectKind.NO_GIT:
        return CtaPlan(
            kind=kind,
            subtitle="Git 없는 폴더",
            actions=(
                CtaAction("GitHub에 올리기 시작", "primary", CtaActionId.PUBLISH_START),
                CtaAction("폴더 열기", "normal", CtaActionId.OPEN_FOLDER),
            ),
            note=_NOTE_NO_GIT,
        )
    if kind is ProjectKind.NO_REMOTE:
        return CtaPlan(
            kind=kind,
            subtitle="원격 없는 Git",
            actions=(
                CtaAction("GitHub에 올리기 시작", "primary", CtaActionId.PUBLISH_START),
                CtaAction("작업 내역 보기", "normal", CtaActionId.HISTORY),
                CtaAction("폴더 열기", "quiet", CtaActionId.OPEN_FOLDER),
            ),
            note=_NOTE_NO_REMOTE,
        )
    if kind is ProjectKind.NOT_MINE:
        return CtaPlan(
            kind=kind,
            subtitle="받아온 프로젝트",
            actions=(
                CtaAction("내 사본 만들기", "primary", CtaActionId.FORK_COPY),
                CtaAction("원본에서 받아오기", "normal", CtaActionId.PULL),
                CtaAction("작업 내역 보기", "quiet", CtaActionId.HISTORY),
            ),
            note=_NOTE_NOT_MINE,
        )
    if kind is ProjectKind.DIRTY:
        return CtaPlan(
            kind=kind,
            subtitle="내 프로젝트",
            actions=(
                CtaAction("올리기", "primary", CtaActionId.PUSH),
                CtaAction("받아오기", "normal", CtaActionId.PULL),
                CtaAction("작업 내역 보기", "quiet", CtaActionId.HISTORY),
            ),
            note=None,
        )
    # 시안 L436: 받아오기 primary · 작업 내역 normal · 폴더 열기 quiet
    return CtaPlan(
        kind=kind,
        subtitle="내 프로젝트",
        actions=(
            CtaAction("받아오기", "primary", CtaActionId.PULL),
            CtaAction("작업 내역 보기", "normal", CtaActionId.HISTORY),
            CtaAction("폴더 열기", "quiet", CtaActionId.OPEN_FOLDER),
        ),
        note=None,
    )


def apply_signed_out_prefix(plan: CtaPlan, *, signed_in: bool) -> CtaPlan:
    """Prefix primary when signed out (시안 need + X-1)."""
    if signed_in or not plan.actions:
        return plan
    primary = plan.actions[0]
    if primary.label not in _PREFIX_LABELS:
        return plan
    new_primary = CtaAction(
        label=f"로그인하고 {primary.label}",
        variant=primary.variant,
        action_id=primary.action_id,
    )
    return CtaPlan(
        kind=plan.kind,
        subtitle=plan.subtitle,
        actions=(new_primary, *plan.actions[1:]),
        note=plan.note,
        signed_out_prefix=True,
    )


def build_cta_plan(
    *,
    has_git: bool,
    is_mine: bool | None = True,
    dirty: bool | None = False,
    signed_in: bool = True,
    has_origin: bool | None = True,
) -> CtaPlan:
    """Full P4a entry: kind → actions → optional signed-out prefix."""
    kind = home_project_kind(
        has_git=has_git,
        is_mine=is_mine,
        dirty=dirty,
        has_origin=has_origin,
    )
    return apply_signed_out_prefix(_plan_for_kind(kind), signed_in=signed_in)
