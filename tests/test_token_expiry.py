"""PAT expiration parse / display."""

from __future__ import annotations

from app.auth.token_expiry import (
    format_expires_display,
    parse_expires_from_page_text,
    parse_expires_label,
)


def test_parse_relative_days() -> None:
    iso = parse_expires_label("90", "90 days")
    assert iso is not None
    assert iso.endswith("Z")


def test_parse_no_expiration() -> None:
    assert parse_expires_label("none", "No expiration") == "none"
    assert parse_expires_from_page_text("No expiration") == "none"


def test_parse_absolute_date() -> None:
    iso = parse_expires_label("2026-12-31", "Custom")
    assert iso is not None
    assert iso.startswith("2026-12-31")


def test_format_display() -> None:
    assert "만료 없음" in format_expires_display("none")
    assert "확인 불가" in format_expires_display(None)
    assert "2026" in format_expires_display("2026-12-31T23:59:59Z")
