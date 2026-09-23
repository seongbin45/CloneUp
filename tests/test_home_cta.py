"""P4a: home CTA state machine (pure)."""

from __future__ import annotations

from app.ui.home_cta import (
    CtaActionId,
    ProjectKind,
    apply_signed_out_prefix,
    build_cta_plan,
    home_project_kind,
)
from app.ui.home_tokens import HOME_MIN_WIDTH, display_path


def test_kind_order() -> None:
    assert home_project_kind(has_git=False) is ProjectKind.NO_GIT
    assert (
        home_project_kind(has_git=True, has_origin=False, dirty=True)
        is ProjectKind.NO_REMOTE
    )
    assert (
        home_project_kind(has_git=True, is_mine=False, dirty=True)
        is ProjectKind.NOT_MINE
    )
    assert home_project_kind(has_git=True, dirty=True) is ProjectKind.DIRTY
    assert home_project_kind(has_git=True, dirty=False) is ProjectKind.CLEAN
    assert home_project_kind(has_git=True, dirty=None) is ProjectKind.CLEAN
    # Unknown origin must not force NO_REMOTE
    assert (
        home_project_kind(has_git=True, has_origin=None, dirty=False)
        is ProjectKind.CLEAN
    )


def test_no_git_actions_and_note() -> None:
    plan = build_cta_plan(has_git=False, signed_in=True)
    assert plan.kind is ProjectKind.NO_GIT
    assert len(plan.actions) == 2
    assert plan.actions[0].label == "GitHub에 올리기 시작"
    assert plan.actions[0].variant == "primary"
    assert plan.actions[1].label == "폴더 열기"
    assert plan.note and "공개 여부" in plan.note


def test_no_remote_actions_and_note() -> None:
    plan = build_cta_plan(has_git=True, has_origin=False, signed_in=True)
    assert plan.kind is ProjectKind.NO_REMOTE
    assert plan.subtitle == "원격 없는 Git"
    assert plan.actions[0].action_id is CtaActionId.PUBLISH_START
    assert plan.actions[0].label == "GitHub에 올리기 시작"
    assert [a.action_id for a in plan.actions] == [
        CtaActionId.PUBLISH_START,
        CtaActionId.HISTORY,
        CtaActionId.OPEN_FOLDER,
    ]
    assert plan.actions[1].label == "작업 내역 보기"
    assert plan.actions[1].variant == "normal"
    assert plan.actions[2].variant == "quiet"
    assert plan.note and "origin" in plan.note
    # No push/pull for local-only repos
    assert CtaActionId.PUSH not in {a.action_id for a in plan.actions}
    assert CtaActionId.PULL not in {a.action_id for a in plan.actions}


def test_no_remote_signed_out_prefix() -> None:
    plan = build_cta_plan(has_git=True, has_origin=False, signed_in=False)
    assert plan.signed_out_prefix is True
    assert plan.actions[0].label == "로그인하고 GitHub에 올리기 시작"
    # HISTORY / OPEN_FOLDER are not prefix targets
    assert [a.label for a in plan.actions[1:]] == ["작업 내역 보기", "폴더 열기"]


def test_not_mine_dirty_clean() -> None:
    nm = build_cta_plan(has_git=True, is_mine=False, signed_in=True)
    assert nm.actions[0].action_id is CtaActionId.FORK_COPY
    assert len(nm.actions) == 3
    dirty = build_cta_plan(has_git=True, dirty=True, signed_in=True)
    assert dirty.actions[0].label == "올리기"
    assert len(dirty.actions) == 3
    clean = build_cta_plan(has_git=True, dirty=False, signed_in=True)
    assert len(clean.actions) == 3
    assert clean.actions[0].label == "받아오기"
    assert clean.actions[1].label == "작업 내역 보기"
    assert clean.actions[1].variant == "normal"
    assert clean.actions[2].label == "폴더 열기"
    assert clean.actions[2].variant == "quiet"


def test_x1_prefix_includes_publish_start() -> None:
    """X-1: 「GitHub에 올리기 시작」 also gets 로그인하고 prefix."""
    plan = build_cta_plan(has_git=False, signed_in=False)
    assert plan.signed_out_prefix is True
    assert plan.actions[0].label == "로그인하고 GitHub에 올리기 시작"
    # secondary unchanged (시안 L441–442: primary only)
    assert [a.label for a in plan.actions[1:]] == ["폴더 열기"]


def test_prefix_on_sian_need_labels_secondary_unchanged() -> None:
    push = build_cta_plan(has_git=True, dirty=True, signed_in=False)
    assert push.actions[0].label == "로그인하고 올리기"
    assert [a.label for a in push.actions[1:]] == ["받아오기", "작업 내역 보기"]
    pull = build_cta_plan(has_git=True, dirty=False, signed_in=False)
    assert pull.actions[0].label == "로그인하고 받아오기"
    assert [a.label for a in pull.actions[1:]] == ["작업 내역 보기", "폴더 열기"]
    fork = build_cta_plan(has_git=True, is_mine=False, signed_in=False)
    assert fork.actions[0].label == "로그인하고 내 사본 만들기"
    assert [a.label for a in fork.actions[1:]] == [
        "원본에서 받아오기",
        "작업 내역 보기",
    ]


def test_apply_prefix_idempotent_when_signed_in() -> None:
    base = build_cta_plan(has_git=True, dirty=True, signed_in=True)
    again = apply_signed_out_prefix(base, signed_in=True)
    assert again.actions[0].label == "올리기"
    assert again.signed_out_prefix is False


def test_home_tokens_basics() -> None:
    assert HOME_MIN_WIDTH == 1180
    assert display_path(r"C:\Users\a\b") == "C:/Users/a/b"
