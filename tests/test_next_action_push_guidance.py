"""
Regression: push/pull failure dialogs showed "인터넷과 연결을 확인하세요" for
non-fast-forward rejections and missing-`workflow`-scope rejections, neither
of which is actually a connectivity problem.

non-fast-forward's real fix is "pull first". The workflow-scope case is
different: this app only ever requests `repo` scope, and asking users to
widen their PAT beyond what the app needs would be requesting a broader
scope than necessary — against GitHub's API terms — so the guidance there
names the real limitation (can't touch .github/workflows/* files) instead
of suggesting a new/broader token.
"""

from __future__ import annotations

from app.util.next_action import next_step_for_error

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


def test_missing_workflow_scope_names_the_limitation_not_a_new_token() -> None:
    """Must NOT tell the user to add `workflow` scope — this app only ever
    requests `repo` (PAT_CREATE_URL), and asking for a broader scope than
    the app needs is against GitHub's API terms. The honest fix is to name
    the limitation (can't touch workflow files) rather than route around it."""
    hint = next_step_for_error(_WORKFLOW_SCOPE)
    assert hint is not None
    assert "워크플로" in hint
    assert "인터넷" not in hint
    assert "새 키" not in hint
    assert "workflow」 권한" not in hint


def test_generic_send_failure_still_falls_back() -> None:
    hint = next_step_for_error("GitHub로 보내기에 실패했습니다.\n\n(참고)\nsome unknown error")
    assert hint == "인터넷과 「GitHub: 연결」을 확인한 뒤 다시 시도하세요."
