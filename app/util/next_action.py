"""
G4 — map existing Korean error text to a single next-step line.

Does not invent new root-cause messages; only appends "다음: …" guidance.
"""

from __future__ import annotations

import re


def next_step_for_error(message: str) -> str | None:
    """
    Return a plain-language next action, or None if no mapping.
    Caller should log/show as: f"다음: {hint}"
    """
    msg = (message or "").strip()
    if not msg:
        return None
    low = msg.lower()

    # Missing repo scope on PAT
    if (
        "저장소(repo) 권한" in msg
        or "저장소 권한" in msg
        or ("repo" in low and "권한" in msg and "없" in msg)
    ):
        return (
            "저장소 권한을 켠 새 키를 만드세요. "
            "안내 창의 「새 키 만들기」→ 복사 → 다시 연결."
        )

    # Expired / revoked PAT
    if (
        "만료" in msg
        or "취소·삭제" in msg
        or "취소되었습니다" in msg
    ):
        return (
            "GitHub에서 새 키를 만드세요 (저장소 권한, 만료일 90일 이상 권장). "
            "그다음 「GitHub: 연결」에서 붙여 넣으세요."
        )

    # Need user to paste a key (no auto Device Flow)
    if (
        "연결이 필요" in msg
        or "키를 붙여" in msg
        or "키가 비어" in msg
        or "키가 너무 짧" in msg
        or "키가 올바르지" in msg
        or "장치 코드 로그인" in msg
        or "브라우저(장치 코드)" in msg
    ):
        return "창 위쪽 「GitHub: 연결」에서 GitHub 키를 붙여 넣으세요."

    # Device Flow (legacy / maintainer only)
    if "device" in low or "장치 코드" in msg or "장치 인증" in msg:
        return "브라우저 장치 코드 방식은 꺼져 있습니다. 「GitHub: 연결」에서 키를 사용하세요."

    # Auth / permission (push denied, 401, etc.)
    if (
        "denied" in low
        or "permission" in low
        or "403" in msg
        or "401" in msg
        or "authentication failed" in low
        or "could not read username" in low
        or "invalid credentials" in low
        or "로그인이 필요" in msg
        or ("권한" in msg and ("없" in msg or "부족" in msg or "실패" in msg))
    ):
        return "창 위쪽 「GitHub: 연결」에서 키를 다시 연결하세요."

    # Clone path already exists
    if "이미 존재하는 경로" in msg or (
        "already exists" in low and ("path" in low or "dest" in low or "폴더" in msg)
    ):
        return "폴더 이름을 바꾸거나, 비어 있는 다른 위치를 고르세요."

    # Bad folder name for clone
    if "폴더 이름이 올바르지 않" in msg:
        return "폴더 이름에서 특수문자(<>:\"/\\|?*)를 빼 보세요."

    # Parent missing
    if "저장 폴더가 없습니다" in msg or "폴더가 없습니다" in msg:
        return "존재하는 로컬 폴더를 선택한 뒤 다시 시도하세요."

    # Empty folder / nothing to commit
    if "빈 폴더" in msg or "커밋할 파일이 최소" in msg:
        return "올릴 파일을 폴더에 넣은 뒤 다시 시도하세요."

    # Secrets by filename
    if "비밀 파일" in msg:
        return (
            "해당 파일을 빼거나 이름을 바꾼 뒤 다시 시도하세요. "
            "정말 포함하려면 고급 옵션을 켠 뒤 확인 창에서 진행하세요."
        )

    # URL issues
    if "owner/repo" in msg or "저장소 주소" in msg or "주소를 입력" in msg:
        return "GitHub 저장소 루트 주소(…/owner/repo)만 붙여넣으세요."

    # Not a git repo / no GitHub link (sync)
    if ".git" in msg and ("없" in msg or "git 저장소" in msg):
        return "「받기」또는 「만들고 올리기」로 먼저 연결하세요."
    if (
        "GitHub와 연결" in msg
        and (
            "없" in msg
            or "있지 않" in msg
            or "아니" in msg
        )
    ) or ("origin" in low and ("없" in msg or "없습니다" in msg)):
        return "「만들고 올리기」로 먼저 올리거나, 「받기」로 받은 폴더를 선택하세요."

    # Conflict
    if "충돌" in msg or "겹쳐" in msg:
        return "「충돌 취소」로 되돌리거나, 다른 프로그램에서 파일을 고친 뒤 다시 시도하세요."

    # Nothing to upload
    if "staging" in low or "staged" in low or "스테이징" in msg or "올릴 파일이 없" in msg:
        return "폴더에 파일을 넣었는지, 무시 목록에 전부 들어가지 않았는지 확인하세요."

    # Push rejected — local branch is behind remote (needs a pull first).
    # Checked before the generic "보내기에 실패" fallback below, since git's
    # raw stderr (always non-fast-forward here) gets embedded in the message.
    if "non-fast-forward" in low or (
        "rejected" in low and "behind" in low and ("remote" in low or "받아오기" in msg)
    ):
        return "먼저 「받아오기」로 GitHub의 최신 내용을 받은 뒤 다시 보내세요."

    # PAT lacks `workflow` scope — blocks pushing .github/workflows/*.yml.
    # This app only ever requests `repo` (see PAT_CREATE_URL in
    # login_dialog.py) — asking users to add `workflow` on top of that
    # would be requesting a broader scope than the app needs, which is
    # against GitHub's API terms. So: name the real limitation instead of
    # routing around it.
    if "without `workflow` scope" in msg or (
        "personal access token" in low and "workflow" in low and "scope" in low
    ):
        return (
            "이 앱의 GitHub 키로는 워크플로 파일(.github/workflows/…)을 바꿀 수 없습니다. "
            "그 파일은 GitHub 웹사이트에서 직접 고치거나, 이번에는 커밋에서 빼고 다시 시도하세요."
        )

    # Send/receive failed (Korean lead sentences)
    if "보내기에 실패" in msg or "받아오기에 실패" in msg:
        return "인터넷과 「GitHub: 연결」을 확인한 뒤 다시 시도하세요."

    # Network / generic git failure
    if "네트워크" in msg or "timed out" in low or "could not resolve" in low:
        return "인터넷 연결을 확인한 뒤 다시 시도하세요."

    if "git" in low and "설치" in msg:
        return "https://git-scm.com/download/win 에서 Git을 설치하세요."

    # Device flow / auth cancel already clear
    if "취소" in msg:
        return None

    # Token / config security
    if "토큰" in msg and ("config" in low or "remote" in low or "보안" in msg):
        return "로그를 확인한 뒤 재로그인하고, 문제가 계속되면 폴더의 remote URL을 점검하세요."

    # push/pull 실패 with little detail — soft default
    if re.search(r"push\s*실패|pull\s*실패", msg, re.I):
        if "denied" in low or "permission" in low or "403" in msg:
            return "「GitHub: 연결」에서 키를 다시 연결하세요."
        return "로그를 확인하세요. 권한 문제면 「GitHub: 연결」을 다시 해 보세요."

    return None


def format_next_step_line(message: str) -> str | None:
    """Full log line '다음: …' or None."""
    step = next_step_for_error(message)
    if not step:
        return None
    if step.startswith("다음:"):
        return step
    return f"다음: {step}"
