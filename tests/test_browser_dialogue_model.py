"""Path B conversational guide — pure scene model."""

from __future__ import annotations

from app.ui.browser_dialogue_model import (
    DialogueScene,
    advance_from_browser_kind,
    build_history,
    expires_at_for_chip,
    expiry_days_value,
    scene_copy,
    scope_query_value,
)


def test_chip_maps() -> None:
    assert expiry_days_value("90일") == "90"
    assert expiry_days_value("만료 없음") == "none"
    assert scope_query_value("저장소만") == "repo"
    assert scope_query_value("저장소 + 워크플로") == "repo,workflow"


def test_expires_at_for_chip() -> None:
    assert expires_at_for_chip("만료 없음") == "none"
    z = expires_at_for_chip("90일")
    assert z.endswith("Z")
    assert "T" in z


def test_scene_copy_tags() -> None:
    assert scene_copy(DialogueScene.LOGIN_WAIT).right_tag == "1 / 3"
    assert scene_copy(DialogueScene.ASK_EXPIRY).right_tag == "2 / 3"
    assert scene_copy(DialogueScene.PRESS_GENERATE).right_tag == "3 / 3"
    assert scene_copy(DialogueScene.DONE).right_tag == "끝"
    assert "Generate" in scene_copy(DialogueScene.PRESS_GENERATE).nudge_text


def test_history_change_targets() -> None:
    rows = build_history(
        DialogueScene.PRESS_GENERATE,
        expiry_label="90일",
        scope_label="저장소만",
        logged_in=True,
        got_token=False,
    )
    texts = [r.text for r in rows]
    assert texts[0] == "로그인했어요"
    assert "만료 90일" in texts[1]
    assert "권한 저장소만" in texts[2]
    assert rows[1].back_to == DialogueScene.ASK_EXPIRY
    assert rows[2].back_to == DialogueScene.ASK_SCOPE


def test_advance_login_and_auth() -> None:
    nxt = advance_from_browser_kind(
        DialogueScene.LOGIN_WAIT, "current", 0, method="passkey"
    )
    assert nxt == DialogueScene.AUTH_WAIT

    nxt2 = advance_from_browser_kind(
        DialogueScene.AUTH_WAIT, "reached", 1, method="token_list"
    )
    assert nxt2 == DialogueScene.ASK_EXPIRY

    nxt3 = advance_from_browser_kind(
        DialogueScene.ASK_EXPIRY, "reached", 2, method=""
    )
    assert nxt3 is None  # chips gate further progress


def test_advance_logout_resets() -> None:
    nxt = advance_from_browser_kind(
        DialogueScene.ASK_SCOPE, "logged_out", 0, method="github_logout"
    )
    assert nxt == DialogueScene.LOGIN_WAIT
