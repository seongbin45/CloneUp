"""User-added glossary terms (설정 → 용어 안내 +)."""

from __future__ import annotations

from app.ui.settings_store import (
    add_user_glossary_entry,
    load_user_glossary,
    remove_user_glossary_entry,
    save_user_glossary,
    _settings,
)


def test_user_glossary_roundtrip() -> None:
    s = _settings()
    key = "user_glossary_entries"
    prev = s.value(key)
    try:
        s.remove(key)
        assert load_user_glossary() == []
        assert add_user_glossary_entry("staging", "다음에 넣을 자리", "git add")
        rows = load_user_glossary()
        assert len(rows) == 1
        assert rows[0][0] == "staging"
        assert rows[0][1] == "다음에 넣을 자리"
        # duplicate name rejected
        assert not add_user_glossary_entry("Staging", "다른 요약")
        assert remove_user_glossary_entry("staging")
        assert load_user_glossary() == []
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)


def test_user_glossary_empty_rejected() -> None:
    s = _settings()
    key = "user_glossary_entries"
    prev = s.value(key)
    try:
        s.remove(key)
        assert not add_user_glossary_entry("", "요약")
        assert not add_user_glossary_entry("용어", "")
        assert load_user_glossary() == []
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)


def test_user_glossary_no_count_cap() -> None:
    """Count is unlimited; only empty/duplicate names fail."""
    s = _settings()
    key = "user_glossary_entries"
    prev = s.value(key)
    try:
        s.remove(key)
        bulk = [(f"t{i}", f"요약 {i}", "") for i in range(50)]
        save_user_glossary(bulk)
        assert len(load_user_glossary()) == 50
        assert add_user_glossary_entry("extra", "더 추가 가능")
        assert len(load_user_glossary()) == 51
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)
