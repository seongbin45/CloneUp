"""Unit tests for read-only commit history helpers."""

from __future__ import annotations

from app.git.history import (
    format_abs_time,
    parse_log_line,
    relative_time_ko,
    repo_display_name,
)

_FS = "\x1f"


def test_parse_log_line_basic() -> None:
    line = (
        f"aabbccddeeff00112233445566778899aabbccdd{_FS}"
        f"aabbccd{_FS}"
        f"seong{_FS}"
        f"1723000000{_FS}"
        f"8/7 14:02{_FS}"
        f"버튼 색 수정"
    )
    c = parse_log_line(line)
    assert c is not None
    assert c.short_hash == "aabbccd"
    assert c.author == "seong"
    assert c.message == "버튼 색 수정"
    assert c.unix_time == 1723000000


def test_parse_log_line_rejects_short() -> None:
    assert parse_log_line("only-one-field") is None


def test_relative_time_ko() -> None:
    now = 1_000_000.0
    assert relative_time_ko(int(now) - 30, now=now) == "방금"
    assert relative_time_ko(int(now) - 120, now=now) == "2분 전"
    assert relative_time_ko(int(now) - 7200, now=now) == "2시간 전"
    assert relative_time_ko(int(now) - 86400 * 3, now=now) == "3일 전"


def test_format_abs_time() -> None:
    # fixed: 2024-08-07 05:06:40 UTC-ish depends on local TZ; just shape check
    s = format_abs_time(1_723_000_000)
    assert "/" in s and ":" in s


def test_repo_display_name() -> None:
    assert repo_display_name(r"C:\Users\me\proj\CloneUp") == "CloneUp"
