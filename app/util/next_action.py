"""
G4 — map existing Korean error text to a single next-step line.

Does not invent new root-cause messages; only appends "다음: …" guidance.
"""

from __future__ import annotations

import re


def is_missing_workflow_scope_error(message: str) -> bool:
    """
    True when a push was rejected because the repo has .github/workflows/*
    files and the PAT lacks `workflow` (on top of `repo`). Reactive-only
    signal — checked after a real push fails, never used to ask for the
    scope up front (most repos don't need it).
    """
    msg = (message or "").strip()
    low = msg.lower()
    # Git's remote-rejected text usually has backticks; accept both forms.
    return (
        "without `workflow` scope" in msg
        or "without workflow scope" in low
        or (
            "personal access token" in low
            and "workflow" in low
            and "scope" in low
        )
    )


def next_step_for_error(message: str) -> str | None:
    """
    Return a plain-language next action, or None if no mapping.
    Caller should log/show as: f"다음: {hint}"
    """
    msg = (message or "").strip()
    if not msg:
        return None
    low = msg.lower()

    # Master-password vault (settings) — English VaultError strings
    if "wrong master password" in low or "wrong current master password" in low:
        return "설정 창에서 마스터 비밀번호를 다시 입력해 보세요."
    if "empty master password" in low:
        return "마스터 비밀번호를 입력한 뒤 다시 눌러 보세요."
    if "dpapi" in low:
        return "Windows에 로그인한 PC에서만 마스터 보호를 켤 수 있어요."
    if "master protection is already enabled" in low:
        return "이미 켜져 있어요. 바꾸려면 설정의 「비밀번호 바꾸기」를 누르세요."
    if (
        "master protection is not enabled" in low
        or "missing wrap.json" in low
        or "missing dek" in low
        or "failed to recover plaintext token" in low
    ):
        return "설정 → 계정에서 마스터 보호 칸을 확인한 뒤 다시 시도하세요."

    # Local OS filesystem permission — MUST precede generic "denied" auth match.
    # Otherwise WinError 5 / Access is denied falsely says 「GitHub: 연결」.
    _os_perm = bool(re.search(r"\bpermission denied\b", low)) and not any(
        k in low for k in ("publickey", "github", "remote", "push", "fetch")
    )
    if (
        "winerror" in low
        or "access is denied" in low
        or "errno 13" in low
        or _os_perm
    ):
        return (
            "다른 프로그램이 폴더를 쓰고 있지 않은지 본 뒤, "
            "권한이 있는 다른 폴더를 골라 보세요."
        )

    # Missing repo scope on PAT
    if (
        "저장소(repo) 권한" in msg
        or "저장소 권한" in msg
        or ("repo" in low and "권한" in msg and "없" in msg)
    ):
        return (
            "GitHub 키에 「저장소(repo)」권한을 켠 뒤 "
            "설정 → 권한 다시 확인을 하거나, 「GitHub: 연결」로 새 키를 넣으세요. "
            "안내 창의 「새 키 만들기」→ 복사 → 다시 연결."
        )

    # Expired / revoked PAT
    if (
        "만료" in msg
        or "취소·삭제" in msg
        or "취소되었습니다" in msg
    ):
        return (
            "창 위쪽 「GitHub: 연결」을 눌러 새 키를 만드세요. "
            "(저장소 권한 켜기, 만료일 90일 이상 권장)"
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
        return "창 위쪽 「GitHub: 연결」을 눌러 키를 붙여 넣으세요."

    # Device Flow (legacy / maintainer only)
    if "device" in low or "장치 코드" in msg or "장치 인증" in msg:
        return (
            "브라우저 장치 코드 방식은 꺼져 있어요. "
            "창 위쪽 「GitHub: 연결」에서 키로 연결하세요."
        )

    # Token leaked into local git config / remote URL (publish safety)
    if "보안 문제" in msg:
        return (
            "창 위쪽 「GitHub: 연결」을 다시 한 뒤 올려 보세요. "
            "계속되면 다른 빈 폴더로 새로 「만들고 올리기」를 시도하세요."
        )

    # Branch name (avoid defaulting to 「GitHub: 연결」)
    if "branch" in low or "브랜치" in msg:
        if "올바르지" in msg or "사용할 수 없" in msg or "너무 깁" in msg or "찾지 못" in msg:
            return (
                "브랜치(작업 갈래) 이름을 목록에서 고르거나, "
                "영문·숫자와 /, _, . 만 써서 다시 입력하세요."
            )

    # SSH / non-https / non-github host
    if "ssh" in low or "git@" in low:
        return (
            "https://github.com/사용자이름/저장소이름 형식의 주소만 붙여 넣으세요. "
            "(SSH 주소 git@… 는 아직 지원하지 않아요.)"
        )
    if "github.com 이 아닙니다" in msg or "https 원격" in low or "gitlab" in low:
        return "github.com 주소(https://github.com/…)만 지원해요. 주소를 바꿔 붙여 넣으세요."

    # Auth / permission (push denied, 401, etc.)
    # Avoid bare "denied"/"permission" — those collide with OS Access is denied.
    if (
        "permission denied (publickey)" in low
        or "403" in msg
        or "401" in msg
        or "authentication failed" in low
        or "could not read username" in low
        or "invalid credentials" in low
        or "로그인이 필요" in msg
        or (
            "denied" in low
            and (
                "push" in low
                or "fetch" in low
                or "remote" in low
                or "github" in low
                or "credential" in low
                or "authenticat" in low
            )
        )
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

    # Parent missing / folder not found
    if (
        "저장 폴더가 없습니다" in msg
        or "폴더가 없습니다" in msg
        or "폴더 없음" in msg
        or "폴더를 찾을 수 없습니다" in msg
    ):
        return "「폴더 고르기」로 실제 있는 폴더를 선택한 뒤 다시 눌러 보세요."

    # Windows autostart registration
    if "시작 항목" in msg or "시작 프로그램" in msg:
        return (
            "설정에서 스위치를 다시 켜 보거나, "
            "Windows 시작 폴더에 CloneUp 바로가기를 직접 넣으세요."
        )

    # Empty folder / nothing to commit
    if "빈 폴더" in msg or "커밋할 파일이 최소" in msg:
        return "올릴 파일을 폴더에 넣은 뒤 다시 「만들고 올리기」를 눌러 보세요."

    # Secrets by filename
    if "비밀 파일" in msg:
        return (
            "해당 파일을 폴더에서 빼거나 이름을 바꾼 뒤 다시 시도하세요. "
            "꼭 올려야 하면 「비밀 파일도 진행 (고급)」을 켠 뒤 확인 창에서 진행하세요."
        )

    # URL issues
    if "owner/repo" in msg or "저장소 주소" in msg or "주소를 입력" in msg:
        return (
            "https://github.com/사용자이름/저장소이름 형식만 붙여 넣으세요. "
            "(파일·폴더 경로가 길면 저장소 첫 화면 주소만 쓰세요.)"
        )

    # Not a git repo / no GitHub link (sync)
    if ".git" in msg and ("없" in msg or "git 저장소" in msg):
        return (
            "이 폴더는 아직 GitHub용으로 준비되지 않았어요. "
            "「받기」탭으로 받거나 「만들고 올리기」탭으로 먼저 올리세요."
        )
    if (
        "GitHub와 연결" in msg
        and (
            "없" in msg
            or "있지 않" in msg
            or "아니" in msg
        )
    ) or ("origin" in low and ("없" in msg or "없습니다" in msg or "읽을 수" in msg)):
        return (
            "「만들고 올리기」로 먼저 올리거나, "
            "「받기」로 받아 둔 폴더를 선택하세요."
        )

    # Conflict
    if "충돌" in msg or "겹쳐" in msg or "합치지 못" in msg:
        return (
            "동기화 탭의 「충돌 취소」로 되돌리거나, "
            "메모장 등에서 파일을 고친 뒤 다시 시도하세요."
        )

    # Nothing to upload
    if "staging" in low or "staged" in low or "스테이징" in msg or "올릴 파일이 없" in msg:
        return (
            "폴더에 파일이 있는지 확인하세요. "
            "있어도 안 되면, 올리지 않기로 한 목록(.gitignore)에 "
            "전부 들어갔는지 살펴보세요."
        )

    # Push rejected — local branch is behind remote (needs a pull first).
    # Checked before the generic "보내기에 실패" fallback below, since git's
    # raw stderr (always non-fast-forward here) gets embedded in the message.
    if "non-fast-forward" in low or (
        "rejected" in low and "behind" in low and ("remote" in low or "받아오기" in msg)
    ):
        return (
            "동기화 탭에서 먼저 「받아오기」를 누른 뒤, "
            "다시 「보내고 올리기」를 눌러 보세요."
        )

    # PAT lacks `workflow` scope — blocks pushing .github/workflows/*.yml.
    # Reactive only: main_window.py shows a dedicated dialog (see
    # is_missing_workflow_scope_error / show_missing_workflow_scope_help)
    # offering a new key with `workflow` added, since this repo specifically
    # needs it — the default connect flow still only ever asks for `repo`.
    if is_missing_workflow_scope_error(msg):
        return (
            "이 저장소에는 자동 실행 파일(workflow)이 있어 "
            "키에 그 권한이 더 필요해요. "
            "안내 창의 「새 키 만들기」→ 복사 → 「GitHub: 연결」로 다시 넣으세요."
        )

    # Send/receive failed (Korean lead sentences)
    if "보내기에 실패" in msg or "받아오기에 실패" in msg:
        return (
            "인터넷이 되는지 확인하고, 창 위쪽 「GitHub: 연결」 상태가 "
            "정상인지 본 뒤 다시 눌러 보세요."
        )

    # Network / generic git failure
    if "네트워크" in msg or "timed out" in low or "could not resolve" in low:
        return "Wi-Fi·인터넷이 되는지 확인한 뒤 다시 시도하세요."

    if "git" in low and "설치" in msg:
        return "브라우저에서 https://git-scm.com/download/win 을 열어 Git을 설치하세요."

    # Device flow / auth cancel already clear
    if "취소" in msg:
        return None

    # Token / config security
    if "토큰" in msg and ("config" in low or "remote" in low or "보안" in msg):
        return (
            "창 위쪽 「GitHub: 연결」을 다시 한 뒤 시도하세요. "
            "계속되면 다른 폴더로 새로 올려 보세요."
        )

    # push/pull 실패 with little detail — soft default
    if re.search(r"push\s*실패|pull\s*실패", msg, re.I):
        if "denied" in low or "permission" in low or "403" in msg:
            return "창 위쪽 「GitHub: 연결」에서 키를 다시 연결하세요."
        return (
            "창 아래 로그를 확인하세요. "
            "권한 문제로 보이면 「GitHub: 연결」을 다시 해 보세요."
        )

    return None


def format_next_step_line(message: str) -> str | None:
    """Full log line '다음: …' or None."""
    step = next_step_for_error(message)
    if not step:
        return None
    if step.startswith("다음:"):
        return step
    return f"다음: {step}"
