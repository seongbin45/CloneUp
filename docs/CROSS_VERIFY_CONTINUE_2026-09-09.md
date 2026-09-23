# CloneUp 교차검증 계속 (2026-09-09, 이어하기)

**대상:** 소스 `main.py` (개발 실행) + 설치본 UM `0.1.12`  
**빌드/릴리스:** 없음 (승인 전 금지)

---

## Pass 결과 요약

| Pass | 내용 | 결과 |
|------|------|------|
| **G** | GitHub 연결 표시 · 설정 진입 · UM 관리 UI | **PASS** — `연결됨 (seongbin45)` · Settings · UpdateManagerDialog |
| **G-tabs** | 만들고 올리기 / 받기 / 동기화 탭 | **조건부 PASS** — a11y `Select`로 받기·동기화 페이지(`tabClone`/`tabSync`) 확인됨. 자동화 왕복은 불안정(잘못된 인덱스·SelectionItem 패턴 실패). **마우스 실사용 탭 전환은 별도 수기 권장** |
| **H** | UM 조용히 실행 (콘솔 숨김) | **PASS** — `CREATE_NO_WINDOW` 단위테스트 2건 |
| **I** | 토큰 · orphan cred · security/PII | **PASS** — token 있음(len=40) · orphan 0 · 53/53 · 34/34 |
| **J** | 업데이트 연기 · “이중 UM” | **PASS (설명 포함)** — 창 열림 시 `main window visible — defer update` 확인. 프로세스 2개 = **PyInstaller onefile 부모+자식**(동일 시작 시각·부모-자식), 별도 관리자 2개가 아님 |

---

## 실사용 관점 디테일

### 잘 되는 것
- 메인 창 제목·Git 표시·GitHub 연결 상태
- 설정 → 안전 → **업데이트 관리자 확인** → 관리 UI (크기 563×546 실측)
- UM이 메인 창이 열려 있으면 **업데이트 연기** (사용자 작업 보호)
- 보안/PII 자동 교차검증 회귀 없음
- push용 임시 자격 증명 고아 파일 없음

### 주의 / 잔여
| 항목 | 사용자에게 보이는 것 | 메모 |
|------|----------------------|------|
| 설치 버전 0.1.12 vs 릴리스 0.1.13 | 아직 자동 반영 안 됨 | 창 닫힌 뒤 UM이 적용 시도. 과거 `apply failed: timed out` 로그 있음 |
| 관리 UI 요약 | `apply failed` 있으면 위험 문구 | 의도된 하드 실패 표시 |
| 탭 자동화 | a11y만으로 왕복 불안정 | 앱 버그로 단정하지 말 것 — 수기 클릭으로 재확인 |
| 설치본 vs 소스 | Setup exe는 옛 코드 | UM UI·콘솔 수정은 소스에만 있음 |

### “UM이 두 개” 오해 해소
```
PID 5000  parent=…  CloneUp_update_manager.exe   ← bootloader
PID  152  parent=5000  (동일 경로)              ← onefile 실제 페이로드
```
`--once`가 `another instance is running`을 낸 것은 **이미 상주 중인 부모**가 뮤텍스를 잡고 있어서였고, 종료 후 `--once`는 정상적으로 **defer**까지 수행함.

---

## 권장 다음 수기 스모크 (에이전트 대행 무효 — SMOKE_CHECKLIST)
1. 탭 세 개 마우스 클릭으로 화면이 바뀌는지  
2. 창을 닫고 UM이 0.1.13 zip을 적용하는지 (네트워크 안정 시)  
3. classic PAT로 만들고 올리기 1회  

---

## 이번 라운드에서 하지 않은 것
- 빌드 / Setup / GitHub Release  
- 실제 publish/push (저장소 변경)
