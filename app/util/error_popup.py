"""User-facing error popup body builder (cross-checked with next_action).

Policy
------
- **Log** may keep raw/technical detail (git stderr, exception repr).
- **Popup** must always include:
  1. Short Korean lead (what happened in plain words)
  2. The original message (kept for support / exact cause)
  3. A ``다음: …`` line when ``next_action`` can map it, else a soft default

Callers that already have a dedicated beginner dialog (missing repo /
workflow scope) should keep those and skip this helper.
"""

from __future__ import annotations

from app.util.next_action import format_next_step_line, next_step_for_error

_DEFAULT_NEXT = (
    "다음: 위 내용을 확인한 뒤 다시 시도해 보세요. "
    "계속 안 되면 창 위쪽 「GitHub: 연결」에서 키를 다시 연결해 보세요."
)

_DEFAULT_LEAD = "작업을 끝내지 못했어요."


def format_error_popup_body(
    message: str,
    *,
    lead: str | None = None,
    include_raw: bool = True,
) -> str:
    """
    Build a popup body: lead + optional raw message + next-step.

    ``include_raw=False`` shows only lead + next (when the lead already
    restates the cause fully).
    """
    raw = (message or "").strip()
    lead_s = (lead or _DEFAULT_LEAD).strip() or _DEFAULT_LEAD
    hint = format_next_step_line(raw) or _DEFAULT_NEXT
    parts: list[str] = [lead_s]
    if include_raw and raw and raw not in lead_s:
        parts.append(raw)
    if hint and hint not in "\n".join(parts):
        parts.append(hint)
    return "\n\n".join(parts)


def has_next_step_mapping(message: str) -> bool:
    """True when ``next_action`` knows a specific next step (not only default)."""
    return next_step_for_error(message) is not None
