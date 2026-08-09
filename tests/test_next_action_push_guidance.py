"""
Regression: push/pull failure dialogs showed "인터넷과 연결을 확인하세요" for
non-fast-forward rejections and missing-`workflow`-scope rejections, neither
of which is actually a connectivity problem.

non-fast-forward's real fix is "pull first". The workflow-scope case: this
app's default connect flow only ever asks for `repo` (most repos don't have
.github/workflows/*, so requesting `workflow` up front would be asking for
more than needed). But when a push actually fails for that specific reason,
the repo has proven it needs the scope — so the guidance here points at a
dedicated reactive flow (see login_dialog.show_missing_workflow_scope_help)
that creates a new key with `workflow` added, rather than telling the user
to route around it.
"""

from __future__ import annotations

from app.util.next_action import is_missing_workflow_scope_error, next_step_for_error

_NON_FAST_FORWARD = (
    "GitHub로 보내기에 실패했습니다.\n\n(참고)\n"
    "To https://github.com/seongbin45/GunSan-youth-dashboard-KOSIS.git\n"
    " ! [rejected]        HEAD -> main (non-fast-forward)\n"
    "error: failed to push some refs to "
    "'https://github.com/seongbin45/GunSan-youth-dashboard-KOSIS.git'\n"
    "hint: Updates were rejected because the tip of your current branch is behind\n"
    "hint: its remote counterpart. If you want to integrate the remote changes,\n"
    "hint: use 'git pull' before pushing again.\n"
    "hint: See the 'Note about fast-forwards' in 'git push --help' for details."
)

_WORKFLOW_SCOPE = (
    "GitHub로 보내기에 실패했습니다.\n\n(참고)\n"
    "To https://github.com/seongbin45/GunSan-youth-dashboard-KOSIS.git\n"
    " ! [remote rejected] HEAD -> main (refusing to allow a Personal Access "
    "Token to create or update workflow `.github/workflows/test.yml` "
    "without `workflow` scope)\n"
    "error: failed to push some refs to "
    "'https://github.com/seongbin45/GunSan-youth-dashboard-KOSIS.git'"
)


def test_non_fast_forward_suggests_pull_first() -> None:
    hint = next_step_for_error(_NON_FAST_FORWARD)
    assert hint is not None
    assert "받아오기" in hint
    assert "인터넷" not in hint


def test_missing_workflow_scope_is_detected() -> None:
    assert is_missing_workflow_scope_error(_WORKFLOW_SCOPE)
    assert not is_missing_workflow_scope_error(_NON_FAST_FORWARD)
    assert not is_missing_workflow_scope_error("some unrelated failure")


def test_missing_workflow_scope_points_at_a_new_key() -> None:
    """Reactive-only: this repo has just proven it needs `workflow` on top
    of `repo`, so — unlike the default connect flow — it's fine to point at
    a new key with that scope added."""
    hint = next_step_for_error(_WORKFLOW_SCOPE)
    assert hint is not None
    assert "workflow" in hint
    assert "새 키" in hint
    assert "인터넷" not in hint


def test_generic_send_failure_still_falls_back() -> None:
    hint = next_step_for_error("GitHub로 보내기에 실패했습니다.\n\n(참고)\nsome unknown error")
    assert hint == "인터넷과 「GitHub: 연결」을 확인한 뒤 다시 시도하세요."
