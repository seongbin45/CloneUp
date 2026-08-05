# 개인정보 검증 — 교차검증 (재검증)

**재검증일:** 2026-08-06  
**참고:** `Codyssey_2+1_ProJect/Command-to-commit-changes-from-Git`  
- `README(한글_가이드).md` §1-4 (grep 사전 조사)  
- `anonymize.py` (지정 문자열 치환 · 바이너리 스킵)  
**CloneUp:** `app/git/safety.py`, G3 `MainController._confirm_upload_g3`  
**자동 검사:** `.\.venv\Scripts\python.exe scripts\verify_pii_crosscheck.py`  
**결과:** **26 / 26 PASS** (`CROSS_VERIFY_OK`)

---

## 1. 참고 프로젝트가 하는 일

| 역할 | 내용 | 위치 |
|------|------|------|
| **탐지 (수동)** | 전화·이메일 정규식으로 저장소 전체 검색 | README grep |
| **탐지 (수동)** | 팀원 실명·로마자 id 문자열 검색 | README grep |
| **치환** | 사용자가 넣은 문자열 → 역할명 등 | `anonymize.py` / README 인라인 스크립트 |
| **스킵** | `.git`, `__pycache__`, `node_modules` + 바이너리 확장자 | `anonymize.py` |
| **재검증** | 치환 후 실명 grep 재실행 | README §1-6 |

전화 패턴 (README 그대로):

```text
01[0-9]-?[0-9]{3,4}-?[0-9]{4}
```

이메일 패턴 (README 그대로):

```text
[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}
```

학번: “확인함”만 있고 **고정 정규식 없음**.

---

## 2. 항목별 대조

| # | 항목 | 참고 | CloneUp | 판정 |
|---|------|------|---------|------|
| 1 | 전화 regex | README grep | `_PHONE_RE` **동일 문자열** | **일치** |
| 2 | 이메일 regex | README grep | `_EMAIL_RE` **동일 문자열** | **일치** |
| 3 | 전화 샘플 `010-1234-5678` / `01012345678` / `011-123-4567` | 매칭 | 매칭 | **일치** |
| 4 | 유선 `02-…` | 미매칭 | 미매칭 | **일치** |
| 5 | 바이너리 확장자 | anonymize 집합 | **상위호환** (포함 + 추가) | **충족** |
| 6 | 스킵 디렉터리 | `.git` 등 3종 | 3종 포함 + `.venv` 등 | **충족** |
| 7 | UTF-8 디코드 실패 시 스킵 | anonymize | 동일 | **일치** |
| 8 | 파일명 비밀 (`.env`, key…) | 없음 | `find_secret_candidates` | **CloneUp 전용 (더 강함)** |
| 9 | 내용 전화/이메일 스캔 | 수동 grep | `scan_pii_in_contents` 자동 | **목표 충족** |
| 10 | G3 UI 노출 | 없음 | 비밀 파일 + 내용 PII + 커밋 이메일 | **충족** |
| 11 | `allow_secrets` 없을 때 `.env` 차단 | 없음 | `run_safety_checks` 실패 | **CloneUp 전용** |
| 12 | 내용 PII 시 하드 차단 | 없음 (확인만) | **차단 안 함** · 확인 대화 + warning | **참고와 같은 soft 성격** |
| 13 | 실명·로마자 id 자동 탐지 | 수동 지정 문자열 | 없음 | **의도적 미구현** |
| 14 | 일괄 치환 (`anonymize`) | 있음 | 없음 | **의도적 미구현** |
| 15 | 학번 고정 패턴 | 없음 | 없음 | **동일 (공백)** |
| 16 | 스캔 범위 | 보통 전체/`git ls-files` | 디스크 walk (tracked 한정 아님) | **차이 (문서화)** |
| 17 | `.*` 숨김 디렉터리 | grep은 `.git`만 제외 | **모든 `.*` 디렉터리 스킵** | **차이** |
| 18 | 예시 이메일 필터 | 없음 (전부 표시) | `example.com` 등 무시 | **차이 (오탐 완화)** |
| 19 | `sync_ops` 워커 | — | 파일명 비밀만; 내용 PII는 **UI G3** | **경로 분리 OK** |

---

## 3. 동작 시나리오 (자동 테스트)

임시 폴더:

| 파일 | 기대 | 결과 |
|------|------|------|
| `.env` | 파일명 비밀 | 차단 (allow 없으면) |
| `note.txt` 안 `010-9999-8888` | 내용 전화 | G3/report hit |
| `note.txt` 안 `real@univ.ac.kr` | 내용 이메일 | hit |
| `test@example.com` | 무시 | hit 없음 |
| `img.png` 바이너리 속 전화 문자열 | 스캔 안 함 | hit 없음 |
| `.cache/x.txt` 전화 | `.*` 디르 스킵 | hit 없음 |

---

## 4. 잔여 차이 (버그 아님 · 제품 선택)

1. **치환 도구 없음** — CloneUp은 “올리기 전 경고”; 참고는 “커밋 전 비식별화 편집”.  
2. **숨김 폴더** — CloneUp이 더 공격적으로 스킵 (`.github` 등도 제외). 참고 grep은 `.git`만 제외.  
3. **이메일 무시 목록** — 오탐 줄이려 `github.com` / `example.com` 등 필터. 참고는 전부 나열.  
4. **tracked-only 아님** — ignore된 로컬 파일도 스캔 가능 (보수적).

---

## 5. 재실행

```powershell
cd CloneUp
.\.venv\Scripts\python.exe scripts\verify_pii_crosscheck.py
```

기대 출력 끝: `CROSS_VERIFY_OK`
