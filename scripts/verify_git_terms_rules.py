#!/usr/bin/env python3
"""
Cross-check: beginner Git copy rules (docs/GIT_FOR_BEGINNERS.md).

Checks user-facing glossary + tab tips + onboarding product words.
Author docs may still list banned metaphors (that is OK).

Run:
  .\\.venv\\Scripts\\python.exe scripts\\verify_git_terms_rules.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
WARN = 0
OUT: list[str] = []


def ok(sec: str, name: str, detail: str = "") -> None:
    global PASS
    PASS += 1
    OUT.append(f"PASS  [{sec}] {name}" + (f" — {detail}" if detail else ""))


def fail(sec: str, name: str, detail: str) -> None:
    global FAIL
    FAIL += 1
    OUT.append(f"FAIL  [{sec}] {name} — {detail}")


def warn(sec: str, name: str, detail: str) -> None:
    global WARN
    WARN += 1
    OUT.append(f"WARN  [{sec}] {name} — {detail}")


def main() -> int:
    from app.ui.git_terms_ko import GLOSSARY_ENTRIES
    from app.ui.onboarding_dialog import _STEPS

    terms_blob = "\n".join(f"{t}\n{a}\n{b}" for t, a, b in GLOSSARY_ENTRIES)
    mw = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    tip_i = mw.find("_install_tab_tip_cards")
    tip_chunk = mw[tip_i : tip_i + 3000] if tip_i >= 0 else ""
    ob = (ROOT / "app" / "ui" / "onboarding_dialog.py").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "GIT_FOR_BEGINNERS.md").read_text(encoding="utf-8")
    ui = (ROOT / "ui" / "main_window.ui").read_text(encoding="utf-8")

    # R1 product cards
    sec = "R1"
    for n in (
        "만들고 올리기",
        "받기",
        "동기화",
        "충돌 취소",
        "커밋 내역",
        "올리고 보내기",
        "받아오기",
        "네 자리 (가장 중요)",
        "브랜치 (이름표)",
    ):
        if any(t == n for t, _, _ in GLOSSARY_ENTRIES):
            ok(sec, f"카드: {n}")
        else:
            fail(sec, f"카드 없음: {n}", "")

    # R2 banned seeds in user glossary + tips
    sec = "R2"
    banned = [
        ("구글 드라이브", "gdrive"),
        ("드롭박스", "dropbox"),
        ("타임머신", "timemachine"),
        ("세이브포인트", "savepoint"),
        ("게임 세이브", "games save"),
        ("USB", "usb"),
        ("백업 업로드", "backup upload"),
        ("자동 클라우드", "auto cloud"),
        ("클라우드 동기화", "cloud sync"),
        ("폴더 복사본", "folder copy"),
    ]
    for pat, name in banned:
        if pat in terms_blob:
            fail(sec, f"glossary 시드: {name}", pat)
        else:
            ok(sec, f"glossary clean: {name}")
        if pat in tip_chunk:
            fail(sec, f"tips 시드: {name}", pat)
        else:
            ok(sec, f"tips clean: {name}")
    if re.search(r"백업", terms_blob):
        fail(sec, "glossary 백업", "user-facing backup metaphor")
    else:
        ok(sec, "glossary no 백업")

    # R2b author meta not in glossary
    sec = "R2b"
    for needle in (
        "GIT_FOR_BEGINNERS",
        "docs/",
        "6개월",
        "부하 시험",
        "집필",
        "프롬프트",
        "폐기",
    ):
        if needle in terms_blob:
            fail(sec, f"작성자 메타: {needle}", "")
        else:
            ok(sec, f"no meta: {needle}")

    # R3 one-line length ≤45 (spaces stripped)
    sec = "R3"
    for t, a, _b in GLOSSARY_ENTRIES:
        n = len(a.replace(" ", ""))
        if n <= 45:
            ok(sec, f"한 줄 {n}자: {t}")
        else:
            fail(sec, f"한 줄 초과 {n}자: {t}", a)
        if re.search(r"않으면.*없습니다|없으면.*없습니다", a):
            fail(sec, f"이중부정: {t}", a)
        else:
            ok(sec, f"이중부정 없음: {t}")

    # R3 body sentence soft: 60 chars
    sec = "R3body"
    long_n = 0
    for t, _a, b in GLOSSARY_ENTRIES:
        for s in re.split(r"(?<=\.)\s+", b):
            s = s.strip()
            if not s:
                continue
            n = len(s.replace(" ", ""))
            if n > 60:
                long_n += 1
                warn(sec, f"긴 문장 {n}자: {t}", s[:48] + "…")
    if long_n == 0:
        ok(sec, "본문 문장 60자 이내")
    else:
        warn(sec, f"본문 긴 문장 {long_n}개", "권장 60자 — WARN only")

    # R4 no soft product conditionals
    sec = "R4"
    for t, _a, b in GLOSSARY_ENTRIES:
        if "방식이면" in b or re.search(r"되돌리기가.{0,24}이면", b):
            fail(sec, f"조건문: {t}", b[:80])
        else:
            ok(sec, f"단정: {t}")
    hist = next(b for t, _a, b in GLOSSARY_ENTRIES if t == "커밋 내역")
    if "새 커밋" in hist and "방식이면" not in hist:
        ok(sec, "커밋 내역 새 커밋 단정")
    else:
        fail(sec, "커밋 내역 동작", hist[:100])

    # R5 formal terms
    sec = "R5"
    low = terms_blob.lower()
    for term in ("commit", "push", "git add", "staging", "remote", "merge"):
        if term in low or term in terms_blob:
            ok(sec, f"정식 용어: {term}")
        else:
            fail(sec, f"정식 용어 없음: {term}", "")

    # R6 design doc structure
    sec = "R6"
    for needle in (
        "유형 P",
        "유형 G",
        "P1",
        "G1",
        "필수(A) 실패",
        "B(확장)로 강등",
        "부정형으로도 언급하지 않는다",
        "45자",
    ):
        if needle in doc:
            ok(sec, f"원칙 문서: {needle}")
        else:
            fail(sec, f"원칙 문서 누락: {needle}", "")

    # R7 fact sentences
    sec = "R7"
    with_fact = sum(
        1
        for _t, _a, b in GLOSSARY_ENTRIES
        if re.search(r"git (add|commit|push|clone|pull|merge)", b, re.I)
    )
    if with_fact >= 5:
        ok(sec, f"git 사실 문장 카드 {with_fact}개")
    else:
        fail(sec, "사실 문장 부족", str(with_fact))

    # R8 UI exists
    sec = "R8"
    for name in (
        "btnCloneHistory",
        "btnSyncHistory",
        "btnSyncAbort",
        "tabPublish",
        "tabClone",
        "tabSync",
    ):
        if name in ui:
            ok(sec, f"UI {name}")
        else:
            fail(sec, f"UI 없음 {name}", "")

    # R9 onboarding
    sec = "R9"
    for word in ("만들고 올리기", "받아오기", "커밋", "충돌 취소", "커밋 내역"):
        if word in ob:
            ok(sec, f"온보딩: {word}")
        else:
            fail(sec, f"온보딩 누락: {word}", "")
    for pat, name in (
        ("구글 드라이브", "gdrive"),
        ("타임머신", "tm"),
        ("세이브포인트", "sp"),
    ):
        if pat in ob:
            fail(sec, f"온보딩 시드: {name}", pat)
        else:
            ok(sec, f"온보딩 clean: {name}")

    # R10 tips no 백업 metaphor
    sec = "R10"
    if "백업" in tip_chunk:
        fail(sec, "탭 팁 백업", "found")
    else:
        ok(sec, "탭 팁 백업 없음")

    # R11 onboarding steps include loop
    sec = "R11"
    keys = [s.key for s in _STEPS]
    if "loop" in keys and keys[0] == "folders":
        ok(sec, f"온보딩 단계 {len(keys)}", str(keys))
    else:
        fail(sec, "온보딩 단계", str(keys))

    print("\n".join(OUT))
    print(f"\nTOTAL  PASS={PASS}  FAIL={FAIL}  WARN={WARN}")
    if FAIL:
        print("GIT_TERMS_RULES_FAIL")
        return 1
    print("GIT_TERMS_RULES_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
