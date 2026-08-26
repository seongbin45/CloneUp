"""Parse / normalize GitHub PAT expiration for storage."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_expires_label(value: str = "", label: str = "") -> str | None:
    """
    Turn GitHub expiration control value/label into ISO-8601 UTC ``…Z``.

    ``none`` / empty → ``none`` (explicit no expiry).
    Relative days (``7``, ``30``, ``90``) → now + days (end of that UTC day).
    Absolute date ``YYYY-MM-DD`` → that day 23:59:59 UTC.
    """
    raw_v = (value or "").strip()
    raw_l = (label or "").strip()
    blob = f"{raw_v} {raw_l}".lower()

    if not raw_v and not raw_l:
        return None

    if raw_v in ("", "none", "no-expiration", "no expiration") or (
        "no expiration" in blob or "만료 없음" in blob or "never" in blob
    ):
        if raw_v == "" and raw_l and not any(
            x in blob for x in ("no expiration", "만료 없음", "never", "none")
        ):
            pass  # fall through — might be a date label only
        else:
            return "none"

    # Relative day count in value
    if re.fullmatch(r"\d{1,3}", raw_v):
        days = int(raw_v)
        if 1 <= days <= 366:
            dt = _utc_now() + timedelta(days=days)
            return to_iso_z(dt.replace(hour=23, minute=59, second=59))

    # Absolute date in value or label
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw_v) or re.search(
        r"(\d{4})-(\d{2})-(\d{2})", raw_l
    )
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime(y, mo, d, 23, 59, 59, tzinfo=timezone.utc)
            return to_iso_z(dt)
        except ValueError:
            return None

    # "90 days" in label
    m2 = re.search(r"(\d{1,3})\s*days?", blob)
    if m2:
        days = int(m2.group(1))
        if 1 <= days <= 366:
            dt = _utc_now() + timedelta(days=days)
            return to_iso_z(dt.replace(hour=23, minute=59, second=59))

    return None


def parse_expires_from_page_text(text: str) -> str | None:
    """Scan issued-page / form body text for an expiration cue."""
    blob = text or ""
    low = blob.lower()
    if "no expiration" in low or "만료 없음" in low:
        return "none"
    # Expires on Tue, Nov 24 2026 / Expires: 2026-11-24
    m = re.search(
        r"expires?(?:\s+on)?\s*[:\s]+([A-Za-z]{3},?\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{4}|\d{4}-\d{2}-\d{2})",
        blob,
        re.I,
    )
    if m:
        chunk = m.group(1).strip()
        iso = parse_expires_label(chunk, chunk)
        if iso:
            return iso
        # RFC-ish date
        for fmt in ("%a, %b %d %Y", "%b %d %Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(chunk.replace(",", ""), fmt.replace(",", ""))
                dt = dt.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
                return to_iso_z(dt)
            except ValueError:
                continue
    return None


def format_expires_display(raw: str | None) -> str:
    """Short Korean for UI."""
    if raw is None or not str(raw).strip():
        return "만료일 확인 불가"
    s = str(raw).strip()
    if s.lower() == "none":
        return "만료 없음"
    text = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d") + " (UTC)"
    except ValueError:
        return s


def format_connected_at_display(raw: str | None) -> str:
    """Connect / issue stamp for Settings (CloneUp stored time ≈ 발급·연결 시각)."""
    if raw is None or not str(raw).strip():
        return "기록 없음"
    s = str(raw).strip()
    text = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") + " (UTC)"
    except ValueError:
        return s
