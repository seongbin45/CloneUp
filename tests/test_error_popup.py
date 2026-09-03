"""Cross-check: error_popup body policy + next_action mappings.

Policy under test
-----------------
Popup body = Korean lead (+ English restatement) + raw/detail + ``다음: …``.
OS Access-is-denied must NOT be mis-mapped to 「GitHub: 연결」.
English-only vault/git blobs get a Korean cause line + support label.
"""

from __future__ import annotations

from app.util.error_popup import (
    format_error_popup_body,
    has_next_step_mapping,
    infer_error_lead,
    korean_restatement_for_english,
)
from app.util.next_action import (
    format_next_step_line,
    is_missing_workflow_scope_error,
    next_step_for_error,
)


def test_format_always_has_lead_and_next() -> None:
    body = format_error_popup_body("알 수 없는 실패 XYZ")
    assert "요청하신 작업을 마치지 못했어요." in body
    assert "알 수 없는 실패 XYZ" in body
    assert "다음:" in body


def test_format_custom_lead_and_skips_duplicate_raw() -> None:
    lead = "폴더를 열지 못했어요."
    body = format_error_popup_body(lead, lead=lead, include_raw=True)
    # raw identical to lead → not duplicated
    assert body.count(lead) == 1
    assert "다음:" in body


def test_format_include_raw_false() -> None:
    body = format_error_popup_body(
        "technical stderr dump",
        lead="올리지 못했어요.",
        include_raw=False,
    )
    assert "올리지 못했어요." in body
    assert "technical stderr dump" not in body
    assert "다음:" in body


def test_winerror_access_denied_is_os_not_github() -> None:
    msg = "[WinError 5] Access is denied: 'C:\\\\locked\\\\file'"
    assert has_next_step_mapping(msg)
    step = next_step_for_error(msg) or ""
    assert "GitHub" not in step
    assert "폴더" in step or "권한" in step
    body = format_error_popup_body(msg, lead="폴더를 열지 못했어요.")
    assert "거부" in body or "권한" in body
    assert "자세한 내용" in body
    assert "GitHub: 연결" not in body.split("다음:")[-1]


def test_permission_denied_publickey_still_auth() -> None:
    msg = "Permission denied (publickey)."
    step = next_step_for_error(msg) or ""
    assert "GitHub" in step


def test_bare_permission_denied_is_os() -> None:
    step = next_step_for_error("Permission denied") or ""
    assert "GitHub" not in step
    assert "폴더" in step or "권한" in step


def test_vault_wrong_password_mapped() -> None:
    step = next_step_for_error("wrong master password") or ""
    assert "비밀번호" in step
    assert has_next_step_mapping("wrong master password")
    body = format_error_popup_body("wrong master password")
    assert "맞지" in body or "비밀번호" in body
    assert "자세한 내용" in body


def test_vault_dpapi_mapped() -> None:
    step = next_step_for_error(
        "DPAPI unavailable — master protection requires Windows"
    ) or ""
    assert "Windows" in step
    rest = korean_restatement_for_english(
        "DPAPI unavailable — master protection requires Windows"
    )
    assert rest is not None
    assert "Windows" in rest or "마스터" in rest


def test_security_leak_mapped() -> None:
    msg = "보안 문제: 연결 정보가 폴더 설정에 남아 있습니다. 다시 시도해 주세요."
    assert has_next_step_mapping(msg)
    step = next_step_for_error(msg) or ""
    assert "GitHub" in step or "만들고 올리기" in step


def test_workflow_scope_without_backticks() -> None:
    msg = (
        "refusing to allow a Personal Access Token to create or update "
        "workflow `.github/workflows/x.yml` without workflow scope"
    )
    assert is_missing_workflow_scope_error(msg)
    assert has_next_step_mapping(msg)
    step = next_step_for_error(msg) or ""
    assert "새 키" in step
    assert "자동 실행" in step or "workflow" in step


def test_send_failure_still_maps() -> None:
    msg = "GitHub로 보내기에 실패했습니다.\n\n(참고)\nsome unknown"
    line = format_next_step_line(msg)
    assert line is not None
    assert line.startswith("다음:")
    assert "인터넷" in line or "GitHub: 연결" in line


def test_tray_style_body_has_korean_lead() -> None:
    raw = "GitHub로 보내기에 실패했습니다.\n\nerror: failed to push"
    body = format_error_popup_body(
        raw[:800],
        lead="선택한 폴더를 GitHub에 올리지 못했어요.",
    )
    assert body.startswith("선택한 폴더를 GitHub에 올리지 못했어요.")
    assert "failed to push" in body
    assert "다음:" in body
    assert "자세한 내용" in body


def test_folder_none_phrase_maps() -> None:
    assert has_next_step_mapping("폴더 없음:\nC:/missing")
    step = next_step_for_error("폴더 없음:\nC:/missing") or ""
    assert "폴더" in step


def test_merge_conflict_phrase_maps() -> None:
    msg = "이 폴더와 GitHub 내용이 서로 달라 자동으로 합치지 못했습니다."
    step = next_step_for_error(msg) or ""
    assert "충돌 취소" in step


def test_autostart_phrase_maps() -> None:
    step = next_step_for_error("Windows 시작 항목을 등록하지 못했습니다.") or ""
    assert "시작" in step


def test_infer_lead_for_send_failure() -> None:
    assert "보내지 못" in infer_error_lead("GitHub로 보내기에 실패했습니다.")


def test_branch_error_not_github_reconnect() -> None:
    msg = "브랜치(작업 갈래) 이름이 올바르지 않습니다."
    step = next_step_for_error(msg) or ""
    assert "브랜치" in step or "갈래" in step
    assert "GitHub: 연결" not in step


def test_ssh_url_maps_to_https_hint() -> None:
    msg = "origin 이 SSH 주소입니다. CloneUp은 https://github.com/… 만 지원합니다."
    step = next_step_for_error(msg) or ""
    assert "https://github.com" in step
    assert "GitHub: 연결" not in step


def test_non_fast_forward_body_explains_in_korean() -> None:
    raw = (
        "GitHub로 보내기에 실패했습니다.\n\n(참고)\n"
        " ! [rejected] HEAD -> main (non-fast-forward)\n"
        "error: failed to push some refs"
    )
    body = format_error_popup_body(raw)
    assert "보내지 못" in body or "받아오기" in body
    assert "최신" in body or "받아오기" in body
    assert "자세한 내용" in body
