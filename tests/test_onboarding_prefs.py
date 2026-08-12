"""Onboarding preference flags (QSettings)."""

from __future__ import annotations

from app.ui.settings_dialog import (
    SECRET_SCAN_OFF_PHRASE,
    phrase_matches_secret_scan_off,
)
from app.ui.settings_store import (
    clear_recent_folders,
    load_history_revert_enabled,
    load_onboarding_done,
    load_recent_folders,
    load_secret_pii_scan_enabled,
    save_history_revert_enabled,
    save_onboarding_done,
    save_secret_pii_scan_enabled,
    _settings,
)


def test_onboarding_done_roundtrip() -> None:
    s = _settings()
    key = "onboarding_done"
    prev = s.value(key)
    try:
        s.remove(key)
        assert load_onboarding_done() is False
        save_onboarding_done(True)
        assert load_onboarding_done() is True
        save_onboarding_done(False)
        assert load_onboarding_done() is False
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)


def test_onboarding_steps_count() -> None:
    from app.ui.onboarding_dialog import _STEPS

    assert len(_STEPS) == 7
    keys = [st.key for st in _STEPS]
    assert keys == [
        "folders",
        "commits",
        "loop",
        "history_mode",
        "cost",
        "undo",
        "safety",
    ]
    hist = next(st for st in _STEPS if st.key == "history_mode")
    # Headline should read like other steps (not a thin "골라 보세요" only)
    assert "커밋 내역" in hist.title
    assert "기본" in hist.lead or "확인" in hist.lead
    folders = next(st for st in _STEPS if st.key == "folders")
    # Step 1 = two places only; no staging entrance fee
    assert "두 곳" in folders.title
    assert "staging" not in folders.title + folders.lead
    loop = next(st for st in _STEPS if st.key == "loop")
    assert "staging" not in loop.title + loop.lead

def test_glossary_has_core_product_words() -> None:
    """용어 안내 keeps real CloneUp labels (no renaming)."""
    from app.ui.git_terms_ko import GLOSSARY_ENTRIES

    terms = {t for t, _a, _b in GLOSSARY_ENTRIES}
    for need in (
        "왜 쓰나요?",
        "네 자리 (가장 중요)",
        "커밋",
        "만들고 올리기",
        "받기",
        "동기화",
        "충돌 취소",
        "커밋 내역",
        "공개 / 비공개",
        "브랜치 (이름표)",
    ):
        assert need in terms
    assert len(GLOSSARY_ENTRIES) >= 12
    blob = " ".join(a + b for _t, a, b in GLOSSARY_ENTRIES)
    # User-facing: do not plant banned metaphors even as "not X"
    for banned in (
        "구글 드라이브",
        "타임머신",
        "백업 업로드",
        "USB",
        "GIT_FOR_BEGINNERS",
        "6개월",
    ):
        assert banned not in blob
    # Product revert: definitive new-commit wording when enabled
    hist = next(b for t, _a, b in GLOSSARY_ENTRIES if t == "커밋 내역")
    assert "새 커밋" in hist
    assert "방식이면" not in hist


def test_history_revert_enabled_default_off() -> None:
    s = _settings()
    key = "history_revert_enabled"
    prev = s.value(key)
    try:
        s.remove(key)
        assert load_history_revert_enabled() is False
        save_history_revert_enabled(True)
        assert load_history_revert_enabled() is True
        save_history_revert_enabled(False)
        assert load_history_revert_enabled() is False
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)


def test_clear_recent_folders() -> None:
    s = _settings()
    key = "recent_folders"
    prev = s.value(key)
    try:
        s.setValue(key, [r"C:\fake\a", r"C:\fake\b"])
        assert len(load_recent_folders()) >= 1
        clear_recent_folders()
        assert load_recent_folders() == []
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)


def test_secret_pii_scan_default_on() -> None:
    s = _settings()
    key = "secret_pii_scan_enabled"
    prev = s.value(key)
    try:
        s.remove(key)
        assert load_secret_pii_scan_enabled() is True
        save_secret_pii_scan_enabled(False)
        assert load_secret_pii_scan_enabled() is False
        save_secret_pii_scan_enabled(True)
        assert load_secret_pii_scan_enabled() is True
    finally:
        if prev is None:
            s.remove(key)
        else:
            s.setValue(key, prev)


def test_secret_scan_off_phrase_exact() -> None:
    assert phrase_matches_secret_scan_off(SECRET_SCAN_OFF_PHRASE)
    assert phrase_matches_secret_scan_off(f"  {SECRET_SCAN_OFF_PHRASE}  ")
    assert not phrase_matches_secret_scan_off("")
    assert not phrase_matches_secret_scan_off("이해했습니다")
    assert not phrase_matches_secret_scan_off(SECRET_SCAN_OFF_PHRASE + ".")
