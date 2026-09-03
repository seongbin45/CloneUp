"""User-facing error popup body builder (cross-checked with next_action).

Policy
------
- **Log** may keep raw/technical detail (git stderr, exception repr).
- **Popup** must always include:
  1. Short Korean lead (what happened in plain words)
  2. Optional Korean restatement when raw is English-only
  3. The original message under a support-friendly label when technical
  4. A ``다음: …`` line when ``next_action`` can map it, else a soft default

Callers that already have a dedicated beginner dialog (missing repo /
workflow scope) should keep those and skip this helper.
"""

from __future__ import annotations

import re

from app.util.next_action import format_next_step_line, next_step_for_error

_DEFAULT_NEXT = (
    "다음: 위 안내를 확인한 뒤 같은 버튼을 다시 눌러 보세요. "
    "계속 안 되면 창 아래 로그를 보거나, 창 위쪽 「GitHub: 연결」을 다시 해 보세요."
)

_DEFAULT_LEAD = "요청하신 작업을 마치지 못했어요."

_DETAIL_LABEL = "자세한 내용(지원·로그용):"

# Mostly-ASCII technical blobs that scare beginners if shown unlabeled.
_TECH_MARKERS = re.compile(
    r"(winerror|access is denied|permission denied|traceback|"
    r"non-fast-forward|failed to push|fatal:|error:|exception|"
    r"dpapi|wrap\.json|dek\.dpapi|wrong master password|"
    r"staging area|refs/heads|head ->|could not|errno\s*\d+)",
    re.I,
)


def infer_error_lead(message: str) -> str:
    """Pick a plain Korean lead when the caller did not supply one."""
    msg = (message or "").strip()
    if not msg:
        return _DEFAULT_LEAD
    low = msg.lower()

    if "wrong master password" in low:
        return "마스터 비밀번호가 맞지 않아요."
    if "empty master password" in low:
        return "마스터 비밀번호가 비어 있어요."
    if "dpapi" in low:
        return "마스터 보호를 이 PC에서 켤 수 없어요."
    if "winerror" in low or "access is denied" in low:
        return "이 폴더나 파일을 열 권한이 없어요."
    if "보내기에 실패" in msg:
        return "GitHub로 보내지 못했어요."
    if "받아오기에 실패" in msg:
        return "GitHub에서 받아오지 못했어요."
    if "합치지 못" in msg or "충돌" in msg or "겹쳐" in msg:
        return "컴퓨터와 GitHub 내용이 달라서 합치지 못했어요."
    if "보안 문제" in msg:
        return "안전을 위해 작업을 멈췄어요."
    if "올릴 파일이 없" in msg or "staging" in low or "빈 폴더" in msg:
        return "올릴 파일이 없어요."
    if "branch" in low or "브랜치" in msg:
        return "브랜치(작업 갈래) 이름을 확인하지 못했어요."
    if "ssh" in low or "git@" in low:
        return "이 주소 형식은 CloneUp에서 쓸 수 없어요."
    if "저장소 주소" in msg or "주소를 입력" in msg or "github.com" in low:
        return "GitHub 주소를 확인하지 못했어요."
    if "폴더" in msg and ("없" in msg or "없습" in msg or "찾을 수" in msg):
        return "폴더를 찾지 못했어요."
    if "git" in low and "설치" in msg:
        return "이 PC에 Git이 아직 없어요."
    if "만료" in msg or "취소·삭제" in msg:
        return "GitHub 연결 키가 더 이상 유효하지 않아요."
    if "연결이 필요" in msg or "키를 붙여" in msg:
        return "GitHub 연결이 필요해요."
    if "비밀 파일" in msg:
        return "비밀처럼 보이는 파일이 있어 막았어요."
    if "origin" in low and ("없" in msg or "읽을 수" in msg):
        return "이 폴더가 GitHub와 아직 연결되지 않은 것 같아요."
    if is_missing_workflowish(msg):
        return "자동 실행 파일(workflow)을 올릴 권한이 키에 없어요."
    return _DEFAULT_LEAD


def is_missing_workflowish(message: str) -> bool:
    from app.util.next_action import is_missing_workflow_scope_error

    return is_missing_workflow_scope_error(message)


def korean_restatement_for_english(message: str) -> str | None:
    """
    When raw is English-only jargon, add one Korean cause line so beginners
    are not left staring at DPAPI / WinError / staging alone.
    """
    msg = (message or "").strip()
    if not msg:
        return None
    low = msg.lower()

    # Already mostly Korean — no extra restatement needed.
    hangul = sum(1 for ch in msg if "가" <= ch <= "힣")
    if hangul >= 8:
        return None

    if "wrong master password" in low:
        return "지금 입력한 마스터 비밀번호가 저장된 것과 달라요."
    if "empty master password" in low:
        return "비밀번호 칸이 비어 있어요."
    if "dpapi" in low:
        return "Windows 로그인 보호 기능을 쓰지 못해 마스터 보호를 켤 수 없어요."
    if "master protection is already enabled" in low:
        return "마스터 보호가 이미 켜져 있어요."
    if "master protection is not enabled" in low:
        return "마스터 보호가 꺼져 있어요."
    if "winerror" in low or "access is denied" in low:
        return "Windows가 이 폴더·파일 접근을 거부했어요."
    if "permission denied (publickey)" in low:
        return "GitHub 로그인(키)이 맞지 않아요."
    if re.search(r"\bpermission denied\b", low):
        return "이 폴더·파일을 쓸 권한이 없어요."
    if "staging" in low:
        return "GitHub로 보내기 직전에 넣을 파일이 비어 있어요."
    if "non-fast-forward" in low:
        return "GitHub에 더 최신 내용이 있어서, 지금 상태로는 덮어쓸 수 없어요."
    if "could not resolve" in low or "timed out" in low:
        return "인터넷으로 GitHub에 닿지 못했어요."
    if "authentication failed" in low or "invalid credentials" in low:
        return "GitHub 키가 맞지 않거나 만료된 것 같아요."
    return None


def _looks_technical(raw: str) -> bool:
    if not raw:
        return False
    if _TECH_MARKERS.search(raw):
        return True
    hangul = sum(1 for ch in raw if "가" <= ch <= "힣")
    ascii_letters = sum(1 for ch in raw if ch.isascii() and ch.isalpha())
    # English-heavy blob with almost no Korean
    return ascii_letters >= 12 and hangul < 6


def format_error_popup_body(
    message: str,
    *,
    lead: str | None = None,
    include_raw: bool = True,
) -> str:
    """
    Build a popup body: lead + optional Korean restatement + raw + next-step.

    ``include_raw=False`` shows only lead + next (when the lead already
    restates the cause fully).
    """
    raw = (message or "").strip()
    lead_s = (lead or infer_error_lead(raw)).strip() or _DEFAULT_LEAD
    hint = format_next_step_line(raw) or _DEFAULT_NEXT
    parts: list[str] = [lead_s]

    restated = korean_restatement_for_english(raw)
    if restated and restated not in lead_s:
        parts.append(restated)

    if include_raw and raw and raw not in lead_s and raw not in (restated or ""):
        if _looks_technical(raw) or restated:
            parts.append(f"{_DETAIL_LABEL}\n{raw}")
        else:
            parts.append(raw)

    if hint and hint not in "\n".join(parts):
        parts.append(hint)
    return "\n\n".join(parts)


def has_next_step_mapping(message: str) -> bool:
    """True when ``next_action`` knows a specific next step (not only default)."""
    return next_step_for_error(message) is not None
