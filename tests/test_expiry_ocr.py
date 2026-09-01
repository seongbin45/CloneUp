"""Pure unit tests for Expiration OCR parsing (no Tesseract binary required)."""

from __future__ import annotations

from app.util.expiry_ocr import parse_expiration_from_ocr_text


def test_parse_near_expiration_label() -> None:
    text = """
New personal access token (classic)
Note
CloneUp-20260902-061741
Expiration
30 days
Custom...
No expiration
"""
    got, detail = parse_expiration_from_ocr_text(text)
    assert got == "30"
    assert "near-label" in detail or "line-only" in detail


def test_parse_no_expiration() -> None:
    text = "Expiration\nNo expiration\nGenerate token"
    got, _detail = parse_expiration_from_ocr_text(text)
    assert got == "none"


def test_parse_ninety_days_line() -> None:
    text = "Something\n90 days\nGenerate"
    got, detail = parse_expiration_from_ocr_text(text)
    assert got == "90"


def test_parse_iso_custom() -> None:
    text = "Expiration\n2026-12-01\nGenerate token"
    got, _detail = parse_expiration_from_ocr_text(text)
    assert got == "2026-12-01"


def test_parse_korean_custom_date() -> None:
    """Screenshot: Custom calendar → opener shows 「2027년 1월 1일」."""
    text = "Note\nExpiration\n2027년 1월 1일\nGenerate token"
    got, detail = parse_expiration_from_ocr_text(text)
    assert got == "2027-01-01"
    assert "ko" in detail or "near-label" in detail or "custom" in detail


def test_parse_dot_custom_date() -> None:
    text = "Expiration\n2027. 1. 1.\nGenerate"
    got, _detail = parse_expiration_from_ocr_text(text)
    assert got == "2027-01-01"


def test_parse_en_custom_date() -> None:
    text = "Expiration\nJan 1, 2027\nGenerate token"
    got, _detail = parse_expiration_from_ocr_text(text)
    assert got == "2027-01-01"


def test_parse_bare_day_near_label() -> None:
    """Windows OCR sometimes drops the word 'days'."""
    text = "Expiration\n30\nCustom"
    got, detail = parse_expiration_from_ocr_text(text)
    assert got == "30"
    assert "bare" in detail or "near-label" in detail


def test_parse_empty() -> None:
    got, detail = parse_expiration_from_ocr_text("")
    assert got is None
    assert "empty" in detail
