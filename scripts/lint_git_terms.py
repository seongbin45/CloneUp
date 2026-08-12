#!/usr/bin/env python3
"""용어 안내 검사기 — docs/GIT_FOR_BEGINNERS.md 원칙을 기계적으로 강제한다.

이 도구가 할 수 있는 것 / 없는 것
----------------------------------
할 수 있음:
  - 금지 비유 어휘가 사용자 대면 텍스트에 노출됐는지 (부정형 포함)
  - 집필 규칙·레포 경로가 사용자 카드로 새어나갔는지
  - 문장 길이·이중부정·의인화·빈 안심·사고 종료 문구
  - 정식 영어 용어 병기 누락
  - 미구현 UI 단어 노출
  - "비유 시험 결과 선언"의 내부 모순 (필수 실패인데 계속 사용 중 등)

할 수 없음:
  - 비유가 실제로 시험을 통과하는지에 대한 의미 판단.
    그건 사람이 METAPHORS 레지스트리에 적어야 하고, 이 도구는
    적힌 내용의 일관성만 검사한다.

사용법:
    python lint_git_terms.py app/ui/git_terms_ko.py
    python lint_git_terms.py app/ui/git_terms_ko.py --strict   # WARN도 실패 처리
    python lint_git_terms.py app/ui/git_terms_ko.py --show-rules
종료 코드: 0 = 통과, 1 = ERROR 있음
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ═════════════════════════════════════════════════════════════════
# 1. 설정 — 제품이 바뀌면 여기만 고친다
# ═════════════════════════════════════════════════════════════════

SUMMARY_MAX_CHARS = 45          # 한 줄 요약 상한 (ERROR)
SENTENCE_MAX_CHARS = 60         # 긴 설명의 문장 상한 (WARN)
LONGTEXT_MAX_SENTENCES = 6      # 긴 설명 문장 수 상한 (WARN)
MIN_EVIDENCE_CHARS = 10         # 시험 결과 근거 최소 길이 (ERROR)

# 현재 앱에 실제로 존재하는 UI 단어만 적는다.
# 여기에 없는 UI 단어가 카드에 굵게 등장하면 사용자는 화면에서 찾다가 자책한다.
# CloneUp main window tabs/buttons (ui/main_window.ui) — keep in sync with product.
IMPLEMENTED_UI: set[str] = {
    "만들고 올리기",
    "받기",
    "동기화",
    "올리고 보내기",
    "받아오기",
    "충돌",
    "충돌 취소",
    "커밋 내역",
}
PLANNED_UI: set[str] = set()  # none currently; planned names would go here

# 고정 금지 비유 6종. 목록은 늘리지 않는다(새 실패는 시험 항목으로).
# 부정형("~가 아닙니다")도 걸린다 — 부정형은 오해를 막는 게 아니라 처음 심는다.
BANNED_METAPHORS: dict[str, tuple[str, ...]] = {
    "백업/복사본 보관": ("백업", "복사본 보관", "통째 업로드", "이사"),
    "자동 클라우드 동기화": ("구글 드라이브", "드롭박스", "드라이브처럼", "클라우드 동기화"),
    "세이브포인트": ("세이브포인트", "세이브 포인트", "저장하고 불러오기", "불러오기"),
    "타임머신": ("타임머신", "타임 머신", "과거로 돌아", "과거로 감", "시간을 되돌"),
    "브랜치=폴더 복사본": ("폴더 복사본", "폴더 통째 복사", "브랜치를 복사"),
    "USB/단순 파일 전송": ("USB", "유에스비", "단순 폴더 복사", "파일 전송"),
}

# 집필 규칙 어휘. 사용자 카드에 있으면 누수다.
META_LEAK: tuple[str, ...] = (
    "부하 시험", "유효 범위", "폐기", "금지 목록", "시험 항목", "검증표",
    "원칙", "docs/", ".md", "프롬프트", "제약", "작성자", "설계 원리",
)

# 구조 표지는 파싱용으로 허용하되, 사용자에게 노출된다는 사실은 별도 WARN.
STRUCTURAL_PREFIXES: tuple[str, ...] = ("원고 비유:", "비유:", "사실:", "동작 사실:")

ANTHROPOMORPHISM: tuple[str, ...] = ("알아서", "기억해", "챙겨", "판단해 줍니다", "대신 정해")
# 정규식. "믿기 쉽습니다"(가능성)와 "쉽습니다"(난이도 안심)를 구분해야 하므로
# '-기 쉽-' 형태는 제외한다.
EMPTY_REASSURANCE: tuple[str, ...] = (
    r"걱정\s*마",
    r"어렵지\s*않",
    r"그냥\s*외우",
    r"(?<!기 )(아주 |매우 |정말 )?쉽습니다",
    r"(아주 |매우 |정말 )?간단합니다",
)
THOUGHT_STOPPERS: tuple[str, ...] = ("일단 이렇게만", "묻지 말고", "외우면 됩니다")

SYNTAX_TRAPS: tuple[tuple[str, str], ...] = (
    (r"않으면.{0,40}없습니다", "이중 부정 — 긍정 단정문으로 바꿀 것"),
    (r"아니라.{0,40}아닙니다", "부정 중첩"),
    (r"방식이면|것이면|한다면 그때", "제품 동작 미확정 조건문 — 확정 후 단정할 것"),
)

# 항목 제목 → 반드시 병기되어야 할 정식 영어 용어
TERM_PAIRING: dict[str, tuple[str, ...]] = {
    "네 자리 (가장 중요)": ("staging", "commit", "push"),
    "커밋": ("commit",),
    "GitHub": ("remote",),
    "받기": ("clone",),
    "동기화": ("push", "pull"),
    "올리고 보내기": ("push",),
    "받아오기": ("pull",),
    "충돌": ("conflict",),
    "충돌 취소": ("abort",),
    "브랜치 (이름표)": ("HEAD",),
    "커밋 내역": ("commit",),
}

# ═════════════════════════════════════════════════════════════════
# 2. 비유 레지스트리 — 사람이 직접 채운다
#    시험은 비유의 "유형"별로 다르다. 자리 비유에게 그래프 질문을
#    물으면 반드시 실패하므로, 같은 세트를 둘 다에 물리지 않는다.
# ═════════════════════════════════════════════════════════════════

REQUIRED_TESTS: dict[str, dict[str, str]] = {
    "자리": {
        "P1": "수정한 파일 5개 중 2개만 골라 커밋할 수 있는가?",
        "P2": "인터넷 없이 커밋을 쌓고 나중에 한 번에 push하는 상황이 설명되는가?",
        "P3": "Git이 존재를 모르는 파일(untracked)이 있다는 게 설명되는가?",
        "P4": "남이 먼저 push해서 내 push가 거절되는 상황이 설명되는가?",
    },
    "그래프": {
        "G1": "브랜치 2개가 동시에 같은 커밋을 가리킬 수 있는가?",
        "G2": "reset과 revert의 차이가 이 비유 안에서 구분되는가?",
        "G3": "merge가 갈래를 없애는 게 아니라 새 커밋을 하나 만드는 것임이 설명되는가?",
        "G4": "과거를 지우지 않고 새 기록을 덧붙이는 방식임이 설명되는가?",
    },
}

VALID_VERDICTS = {"통과", "실패", "미검증"}


@dataclass
class Metaphor:
    name: str
    kind: str                                   # "자리" | "그래프"
    status: str                                 # "사용" | "폐기"
    results: dict[str, tuple[str, str]]         # 시험ID -> (판정, 근거)
    demoted: dict[str, str] = field(default_factory=dict)  # 시험ID -> 강등 근거(커밋/섹션)


# ── 사람이 대입한 시험 결과 (의미 판단은 여기; 도구는 일관성만 봄) ──
METAPHORS: list[Metaphor] = [
    Metaphor(
        name="원고 제출",
        kind="자리",
        status="사용",
        results={
            "P1": (
                "통과",
                "봉투에 넣을 장만 고름 = staging/add. 5개 중 2개 선별이 그림 안에서 성립",
            ),
            "P2": (
                "통과",
                "서고에 여러 봉인(commit) 후 출판사 일괄 발송(push)으로 분리됨",
            ),
            "P3": (
                "통과",
                "책상 위 장 중 아직 봉투·서고에 안 넣은 것 = untracked/미선별",
            ),
            "P4": (
                "통과",
                "출판사 서가 상태가 바뀌면 내 발송이 거절될 수 있음(non-fast-forward)",
            ),
        },
    ),
    Metaphor(
        name="이름표(스티커)",
        kind="그래프",
        status="사용",
        results={
            "G1": (
                "통과",
                "스티커 두 장이 같은 페이지(커밋)를 동시에 가리킬 수 있음",
            ),
            "G2": (
                "통과",
                "reset≈이름표를 다른 페이지로 옮김 / revert≈되돌린 내용을 새 페이지로 덧붙임",
            ),
            "G3": (
                "통과",
                "두 이름표 줄기를 이은 뒤 새 페이지(merge commit) 한 장을 씀",
            ),
            "G4": (
                "통과",
                "과거 페이지를 찢지 않고 새 장을 덧붙이는 안전 경로와 맞음",
            ),
        },
    ),
]
# ──────────────────────────────────────────────────────────────────


# ═════════════════════════════════════════════════════════════════
# 3. 검사 엔진
# ═════════════════════════════════════════════════════════════════

ERROR, WARN = "ERROR", "WARN"


@dataclass
class Finding:
    level: str
    code: str
    where: str
    message: str
    excerpt: str = ""


class Linter:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def add(self, level: str, code: str, where: str, message: str, excerpt: str = "") -> None:
        self.findings.append(Finding(level, code, where, message, excerpt))

    # ---- 텍스트 검사 -------------------------------------------------
    @staticmethod
    def _strip_prefixes(text: str) -> str:
        out = text
        for p in STRUCTURAL_PREFIXES:
            out = out.replace(p, " ")
        return out

    @staticmethod
    def _sentences(text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _clip(text: str, needle: str, span: int = 24) -> str:
        i = text.find(needle)
        if i < 0:
            return text[:60]
        lo, hi = max(0, i - span), min(len(text), i + len(needle) + span)
        return ("…" if lo else "") + text[lo:hi].replace("\n", " ") + ("…" if hi < len(text) else "")

    def check_entry(self, title: str, summary: str, body: str) -> None:
        where = f"[{title}]"
        joined = f"{summary} {body}"
        scan = self._strip_prefixes(joined)

        # GT001 금지 비유 (부정형 포함)
        for label, tokens in BANNED_METAPHORS.items():
            for tok in tokens:
                if tok in scan:
                    self.add(ERROR, "GT001", where,
                             f"금지 비유 '{label}' 어휘 노출 — 부정형도 금지(오해를 막지 않고 심는다). "
                             f"옳은 사실을 긍정 단정문으로 쓸 것",
                             self._clip(scan, tok))
                    break

        # GT002 집필 규칙 누수 (카드당 1건으로 합침)
        leaked = [tok for tok in META_LEAK if tok in scan]
        if leaked:
            self.add(ERROR, "GT002", where,
                     f"집필 규칙/내부 경로가 사용자 카드에 노출됨 ({', '.join(leaked)}) — "
                     f"최종 사용자 대상 텍스트에서 삭제",
                     self._clip(scan, leaked[0]))

        # GT003 구조 표지 노출
        for p in STRUCTURAL_PREFIXES:
            if p in joined:
                self.add(WARN, "GT003", where,
                         f"구조 표지 '{p}'가 사용자에게 그대로 보인다 — 라벨 없이 문장으로 녹일 것")
                break

        # GT010 한 줄 요약 길이
        if len(summary) > SUMMARY_MAX_CHARS:
            self.add(ERROR, "GT010", where,
                     f"한 줄 요약 {len(summary)}자 > {SUMMARY_MAX_CHARS}자 — 주어·서술어 1쌍으로 자를 것",
                     summary)

        # GT011 문장 길이 / GT012 문단 문장 수
        for s in self._sentences(body):
            if len(s) > SENTENCE_MAX_CHARS:
                self.add(WARN, "GT011", where, f"문장 {len(s)}자 > {SENTENCE_MAX_CHARS}자", s)
        n = len(self._sentences(body))
        if n > LONGTEXT_MAX_SENTENCES:
            self.add(WARN, "GT012", where,
                     f"긴 설명 {n}문장 > {LONGTEXT_MAX_SENTENCES}문장 — 카드를 쪼갤 것")

        # GT020 구문 함정
        for pattern, why in SYNTAX_TRAPS:
            m = re.search(pattern, scan)
            if m:
                self.add(ERROR, "GT020", where, why, self._clip(scan, m.group(0)))

        # GT021 의인화 / GT022 빈 안심 / GT023 사고 종료
        for tok in ANTHROPOMORPHISM:
            if tok in scan:
                self.add(ERROR, "GT021", where,
                         "의인화 — 'Git이 ~해준다'는 부정형이어도 주체를 잘못 심는다",
                         self._clip(scan, tok))
                break
        for pat in EMPTY_REASSURANCE:
            m = re.search(pat, scan)
            if m:
                self.add(ERROR, "GT022", where, "빈 안심 문구", self._clip(scan, m.group(0)))
                break
        for tok in THOUGHT_STOPPERS:
            if tok in scan:
                self.add(ERROR, "GT023", where, "사고 종료 문구", self._clip(scan, tok))
                break

        # GT030 비유-사실 짝 (동사 비유 뒤에는 정식 서술 1문장 필수)
        has_metaphor_marker = any(p in joined for p in ("원고 비유:", "비유:"))
        has_fact_marker = any(p in joined for p in ("사실:", "동작 사실:"))
        if has_metaphor_marker and not has_fact_marker:
            self.add(ERROR, "GT030", where,
                     "비유만 있고 정식 용어로 된 사실 서술이 없다 — 사실 문장 1개 필수")

        # GT031 정식 용어 병기
        for req in TERM_PAIRING.get(title, ()):  # type: ignore[arg-type]
            if req.lower() not in joined.lower():
                self.add(ERROR, "GT031", where,
                         f"정식 용어 '{req}' 병기 누락 — 독자가 에러 메시지를 검색할 수 없게 된다")

        # GT040 미구현 UI 단어
        for word in PLANNED_UI:
            if word in joined and word not in IMPLEMENTED_UI and word != title:
                self.add(WARN, "GT040", where,
                         f"미구현 UI 단어 '{word}' 노출 — 화면에 없으면 사용자는 자기 잘못으로 받아들인다")

    # ---- 레지스트리 검사 ---------------------------------------------
    def check_registry(self) -> None:
        for m in METAPHORS:
            where = f"<비유:{m.name}>"
            required = REQUIRED_TESTS.get(m.kind)
            if required is None:
                self.add(ERROR, "MT000", where, f"알 수 없는 비유 유형 '{m.kind}'")
                continue

            missing = set(required) - set(m.results)
            for t in sorted(missing):
                self.add(ERROR, "MT001", where, f"필수 시험 {t} 결과 없음 — {required[t]}")

            unknown = set(m.results) - set(required)
            for t in sorted(unknown):
                self.add(WARN, "MT002", where, f"이 유형에 없는 시험 {t} — 다른 축의 비유에 묻고 있지 않은지 확인")

            for tid, pair in m.results.items():
                verdict, evidence = pair
                if verdict not in VALID_VERDICTS:
                    self.add(ERROR, "MT003", where, f"{tid}: 알 수 없는 판정 '{verdict}'")
                    continue

                if verdict == "미검증":
                    self.add(ERROR, "MT004", where,
                             f"{tid} 미검증 — 시험을 실제로 돌리지 않았다: {required.get(tid, '')}")
                    continue

                if len(evidence.strip()) < MIN_EVIDENCE_CHARS:
                    self.add(ERROR, "MT005", where,
                             f"{tid}: 대입 근거가 {len(evidence.strip())}자 — 형식만 채운 검증표로 간주")

                if verdict == "실패" and m.status == "사용":
                    if tid in m.demoted:
                        if len(m.demoted[tid].strip()) < MIN_EVIDENCE_CHARS:
                            self.add(ERROR, "MT007", where,
                                     f"{tid} 강등 근거 부실 — 개정 커밋/섹션을 명시할 것")
                        else:
                            self.add(WARN, "MT008", where,
                                     f"{tid} 필수 실패를 확장(B)으로 강등한 상태 — 강등 근거: {m.demoted[tid]}")
                    else:
                        self.add(ERROR, "MT006", where,
                                 f"{tid} 필수 실패인데 비유를 계속 사용 중. "
                                 f"'유효 범위 밖' 선언으로 우회할 수 없다 — "
                                 f"비유를 폐기하거나, 이 항목을 B로 강등하는 개정을 먼저 커밋할 것")

            if all(v == "통과" for v, _ in m.results.values()) and not m.results:
                self.add(ERROR, "MT009", where, "결과가 비어 있음")

    # ---- 리포트 ------------------------------------------------------
    def report(self, strict: bool) -> int:
        errors = [f for f in self.findings if f.level == ERROR]
        warns = [f for f in self.findings if f.level == WARN]

        if not self.findings:
            print("통과 — 검출된 문제 없음. (비유의 의미 타당성은 이 도구가 판정하지 않는다.)")
            return 0

        by_where: dict[str, list[Finding]] = {}
        for f in self.findings:
            by_where.setdefault(f.where, []).append(f)

        for where in by_where:
            print(f"\n{where}")
            for f in sorted(by_where[where], key=lambda x: (x.level != ERROR, x.code)):
                print(f"  {f.level:<5} {f.code}  {f.message}")
                if f.excerpt:
                    print(f"        ↳ {f.excerpt}")

        print("\n" + "─" * 68)
        print(f"ERROR {len(errors)}건 / WARN {len(warns)}건")
        if errors:
            print("ERROR가 남아 있으면 커밋하지 않는다.")
        return 1 if (errors or (strict and warns)) else 0


# ═════════════════════════════════════════════════════════════════
# 4. 진입점
# ═════════════════════════════════════════════════════════════════

def load_entries(path: Path) -> tuple[tuple[str, str, str], ...]:
    spec = importlib.util.spec_from_file_location("_glossary_under_test", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"모듈을 읽을 수 없음: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entries = getattr(module, "GLOSSARY_ENTRIES", None)
    if entries is None:
        raise SystemExit(f"{path}에 GLOSSARY_ENTRIES가 없음")
    return entries


def print_rules() -> None:
    print("검사 규칙")
    rules = [
        ("GT001", "금지 비유 6종 어휘 노출 (부정형 포함)"),
        ("GT002", "집필 규칙·레포 경로 누수"),
        ("GT003", "구조 표지('원고 비유:' 등) 사용자 노출"),
        ("GT010", f"한 줄 요약 {SUMMARY_MAX_CHARS}자 초과"),
        ("GT011", f"문장 {SENTENCE_MAX_CHARS}자 초과"),
        ("GT012", f"긴 설명 {LONGTEXT_MAX_SENTENCES}문장 초과"),
        ("GT020", "이중부정·부정중첩·제품 동작 미확정 조건문"),
        ("GT021", "의인화"),
        ("GT022", "빈 안심 문구"),
        ("GT023", "사고 종료 문구"),
        ("GT030", "비유만 있고 사실 서술 없음"),
        ("GT031", "정식 영어 용어 병기 누락"),
        ("GT040", "미구현 UI 단어 노출"),
        ("MT001", "필수 시험 결과 누락"),
        ("MT004", "미검증 — 시험을 돌리지 않음"),
        ("MT005", "대입 근거 부실 (형식만 채운 검증표)"),
        ("MT006", "필수 실패인데 비유 계속 사용 (범위 밖 우회 금지)"),
        ("MT008", "필수 실패를 B로 강등한 상태 (근거 있음)"),
    ]
    for code, desc in rules:
        print(f"  {code}  {desc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="용어 안내 검사기")
    ap.add_argument("path", nargs="?", help="app/ui/git_terms_ko.py 경로")
    ap.add_argument("--strict", action="store_true", help="WARN도 실패로 처리")
    ap.add_argument("--show-rules", action="store_true", help="규칙 목록 출력 후 종료")
    args = ap.parse_args()

    if args.show_rules:
        print_rules()
        return 0
    if not args.path:
        ap.error("검사할 파일 경로가 필요하다")

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"파일 없음: {path}")

    linter = Linter()
    linter.check_registry()
    for entry in load_entries(path):
        title, summary, body = entry[0], entry[1], entry[2]
        linter.check_entry(title, summary, body)
    return linter.report(strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
