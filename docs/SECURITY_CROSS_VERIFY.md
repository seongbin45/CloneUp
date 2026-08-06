# CloneUp 보안 교차검증

**검증일:** 2026-08-07  
**범위:** 인증·토큰·git 자격증명·subprocess·URL·로그 마스킹·업로드 안전(G3)·부트스트랩 다운로드  
**대상 코드:** `app/auth/*`, `app/git/*`, `app/github/*`, `app/ui/*` (워커·로그인), `app/config.py`, `app/util/log_mask.py`  
**위협 모델:** 로컬 데스크톱 헬퍼 — 동일 PC 사용자/멀웨어, 네트워크 도청, 실수 업로드, 공개 client_id 남용

---

## 요약

| 등급 | 개수 | 의미 |
|------|------|------|
| **Critical** | 0 | 원격 임의 코드 실행·기본 경로 Device Flow 토큰 가로채기 등 없음 |
| **High** | 1 | (잔여) Git 설치 파일 서명 미검증 후 실행 |
| **Medium** | 6 | 임시 cred 파일 창·마스킹 잔여·scope 추정·비밀 내용 미탐지 등 |
| **Low** | 5 | 클립보드 PAT·unsigned 배포·PII soft 등 |
| **강점 (PASS)** | 12+ | 설계 문서와 코드 일치하는 핵심 통제 |

**총평:** 제품이 의도한 보안 축(PAT 전용, 토큰을 `.git/config`에 안 넣음, Device Flow 기본 OFF)은 **코드와 문서가 일치**한다.  
남은 이슈는 대부분 **로컬 동일 사용자 위협**, **공급망(설치 파일)**, **초보 실수 완화의 soft 경계**이다.

---

## 1. 통제 매트릭스 (문서 ↔ 코드)

| # | 주장 / 기대 | 코드 위치 | 판정 |
|---|-------------|-----------|------|
| S1 | Device Flow **기본 OFF** | `config.is_device_flow_allowed` · `session.login_device_flow` · `ensure_valid_token` | **PASS** |
| S2 | 무효 토큰 시 **자동 Device Flow 재시작 없음** | `ensure_valid_token` → `AuthError` + keyring 삭제(401) | **PASS** |
| S3 | 토큰 OS keyring 저장 | `token_store.save_token` / `keyring` | **PASS** |
| S4 | remote URL에 토큰 없음 | `publish` clean `origin` · `clone_ops` clean URL · `assert_git_config_has_no_token` | **PASS** |
| S5 | push/clone 시 임시 credential helper + finally 삭제 | `credentials.py` · publish/clone/sync | **PASS** |
| S6 | git `subprocess` list argv, `shell=False` | `runner.run_git` | **PASS** |
| S7 | clone URL host allowlist (`github.com`) | `url_utils.normalize_github_clone_url` | **PASS** |
| S8 | 워커/UI 로그 토큰 마스킹 | `log_mask` · `tab_workers` · `publish_worker` | **PASS** (잔여 M2) |
| S9 | 비대화형 git (프롬프트 hang 방지) | `env.noninteractive_git_env` | **PASS** |
| S10 | 비밀 **파일명** 차단 (allow 없으면) | `safety.run_safety_checks` | **PASS** |
| S11 | 내용 전화/이메일 G3 확인 | `scan_pii_in_contents` + UI | **PASS soft** (하드 차단 아님) |
| S12 | client_id는 public, 비밀 아님 문서화 | `config.py` docstring · ORG_OAUTH | **PASS** |
| S13 | 커밋 이메일 기본 가림 | `hide_real_email` default True | **PASS** |
| S14 | Git 설치 exe 무결성 검증 | `bootstrap.download_*` | **FAIL / High 잔여** |
| S15 | PII 자동 스크립트 26/26 | `scripts/verify_pii_crosscheck.py` | **DRIFT** (24/26, G3 문구 변경) |

---

## 2. 강점 (유지할 것)

### A. 인증 (V1 Trust)

- 공개 OAuth `client_id` + Device Flow 조합의 **토큰 가로채기 면**을 제품 기본 경로에서 제거함.
- 엔드유저: **PAT 붙여넣기만**. 멀웨어가 “같은 승인 화면”으로 폴링해도 사용자가 Device Flow를 쓰지 않으면 가로챌 세션이 없음.
- `CLONEUP_ALLOW_DEVICE_FLOW=1` 은 개발 전용 — 문서·코드 일치.

### B. 자격증명 취급

- 토큰은 **argv / 환경변수 / remote URL**에 넣지 않음.
- `https://x-access-token:…@github.com/` 한 줄은 **임시 파일**에만 기록 후 `finally` 삭제.
- push/clone 후 `.git/config`·`remote -v`에 토큰/`x-access-token` 잔존 검사.

### C. 명령 실행

- `subprocess.run(list, …)` — 셸 주입 경로 없음.
- `CREATE_NO_WINDOW` 로 콘솔 노출 완화 (비밀 노출보다는 UX, 부수 효과).

### D. 네트워크 대상 제한

- clone URL은 `github.com` / `www.github.com` 만.
- API는 `https://api.github.com` 고정.

### E. 업로드 실수 완화 (G3)

- `.env` 등 파일명 패턴 → 기본 **차단**.
- 전화/이메일 내용 → **확인 대화** (의도적 soft).
- 기본 `.gitignore` 자동 생성.

---

## 3. 발견 사항 (취약·잔여 위험)

### H1 — High: Git 설치 파일 다운로드 후 서명 미검증

| | |
|--|--|
| **위치** | `app/git/bootstrap.py` `download_and_run_git_installer` |
| **내용** | GitHub Releases API로 `.exe` URL 받아 임시 폴더에 저장 후 **그대로 실행**. Authenticode/해시 고정 검증 없음. |
| **공격** | (이론) Releases/CDN 공급망 또는 MITM(시스템 신뢰 저장소 손상 시) → 악성 설치 파일 실행. |
| **완화 현황** | HTTPS + 공식 org `git-for-windows/git` 에셋 이름 필터. |
| **권장** | (1) 게시된 SHA256과 대조 (2) Windows Authenticode 게시자 확인 후 실행 (3) 실패 시 브라우저 안내만. |

### M1 — Medium: 임시 credential 파일 수명·가시성

| | |
|--|--|
| **위치** | `app/git/credentials.write_credential_file` (`tempfile.mkstemp` in `%TEMP%`) |
| **내용** | push/clone 동안 평문 토큰이 디스크에 존재. 동일 Windows 사용자 프로세스·백업·포렌식에 노출 가능. 크래시 시 `finally` 미실행 시 잔존 가능. |
| **권장** | 짧은 수명 유지(현재) + 가능하면 `os.O_TEMPORARY`/`DeleteOnClose` 패턴, 시작 시 `cloneup-git-cred-*` orphan 청소, Windows ACL 명시. |

### M2 — Medium: 로그 마스킹 불완전

| | |
|--|--|
| **위치** | `app/util/log_mask.py` |
| **내용** | `ghp_/gho_/…`·`github_pat_` 형태는 마스킹. **앞 4·뒤 4자 남김**. `x-access-token:` 단독·임의 긴 비밀·classic이 아닌 형식은 약함. `GitError.stderr` 원문은 필드에 비마스킹 보관. |
| **권장** | URL 내 `x-access-token:[^@]+` 전체 치환; 오류 객체 stderr도 mask; 가능하면 토큰 전체 `***` (길이만). |

### M3 — Medium: Fine-grained PAT scope 추정 저장

| | |
|--|--|
| **위치** | `session.login_with_pat` — `X-OAuth-Scopes` 비어 있으면 `store_scope = want` |
| **내용** | 실제 권한이 더 좁아도 keyring에 `repo` 등이 있다고 기록될 수 있음 → 이후 `has_scope` 가 낙관적. 실제 API/git 단계에서 실패. |
| **권장** | 헤더 없으면 scope를 비우거나 `unknown` 처리; 작업 직전 API로 재확인. |

### M4 — Medium: 파일 **내용** 시크릿 미탐지

| | |
|--|--|
| **위치** | `safety.py` |
| **내용** | 파일명 패턴 + 전화/이메일. AWS 키·`ghp_` in source·Slack token 등 **내용 시크릿 스캐너 없음**. |
| **권장** | 공통 high-entropy / known-prefix 시크릿 휴리스틱 (G3 soft 또는 hard). |

### M5 — Medium: `allow_secrets` 우회는 사용자 선택

| | |
|--|--|
| **위치** | G3 확인 · `run_safety_checks(allow_secrets=True)` |
| **내용** | 초보가 확인만 누르고 `.env` 업로드 가능. 설계상 soft. |
| **권장** | 공개 저장소일 때 2차 확인 강화; 기본 체크 해제 유지. |

### M6 — Medium: git branch 인자 검증 약함

| | |
|--|--|
| **위치** | `clone_ops.clone_repository` `-b {branch}` |
| **내용** | argv 리스트라 셸 주입은 없음. 그러나 branch가 `-`로 시작하면 git 옵션으로 해석될 여지(일반적 argv injection). UI는 목록 선택이지만 URL suggested / API 이상값 가능. |
| **권장** | `^[.\w\-/]+$` 및 leading `-` 거부, 또는 `git clone --branch --` 패턴 사용. |

### L1 — Low: PAT 클립보드

사용자가 키를 붙여 넣는 동안 클립보드·클립보드 히스토리에 잔존. 제품 한계 — 안내(“붙여 넣은 뒤 클립보드 지우기”) 가능.

### L2 — Low: 배포 바이너리 미서명

SmartScreen “신뢰할 수 없음”. 코드 서명(P2) 대기. 실행 파일 변조 탐지는 OS/사용자 몫.

### L3 — Low: PII soft + 스캔 한도

`_MAX_FILES_SCANNED=2000`, `_MAX_FILE_BYTES=512KiB`, 바이너리 스킵 → 대용량·바이너리 내 PII 누락. 의도적.

### L4 — Low: 로컬 keyring = 로그인 사용자 보호 수준

동일 사용자 멀웨어가 keyring/UI 자동화로 토큰 읽기 가능. OS 계정 분리·디스크 암호화가 전제.

### L5 — Low: 실험 코드 경로

`playwright_device.py`, spikes, `CLONEUP_ALLOW_DEVICE_FLOW` — 제품 기본 경로 아님. 릴리스 빌드에 실험 의존성 최소화 확인 유지.

---

## 4. 위협 시나리오 교차

| 시나리오 | 결과 | 근거 |
|----------|------|------|
| 악성 앱이 공개 client_id로 Device Flow 폴링 | **기본 사용자 경로에서 불가** (Device Flow OFF) | S1 |
| 사용자가 악성 앱의 Device Flow를 승인 | 가능 — 사용자가 켠 개발 모드 또는 타 앱 | 제품 밖 |
| git remote에 토큰 박힘 | **차단·사후 검사** | S4–S5 |
| 로그에 전체 PAT 출력 | **대부분 마스킹** / 잔여 M2 | S8 |
| `.env` 실수 업로드 | **기본 차단**, 확인 시 가능 | S10, M5 |
| 전화/이메일이 소스에 있음 | G3 경고, 하드 차단 아님 | S11, L3 |
| 클론 URL로 내부망 강제 | host allowlist | S7 |
| 명령 주입 (`"; rm` in path) | list argv | S6 |
| 가짜 Git 설치 실행 | **서명 미검증** | H1 |
| PAT 탈취 (피싱 사이트에 붙여넣기) | 사용자 실수 — 앱 검증은 GitHub API | 교육/UI |

---

## 5. 자동 검사 현황

```text
scripts/verify_pii_crosscheck.py  →  24 PASS / 2 FAIL  (2026-08-07)
FAIL: G3 shows content PII copy   (문구 "파일 내용에서 개인정보" 없음 — 초보 카피 단축)
FAIL: G3 shows commit email       (문구 "커밋에 기록" 없음)
```

→ **보안 로직 회귀라기보다 교차검증 스크립트 ↔ UI 문구 불일치.**  
조치: 스크립트 기대 문자열을 현재 G3 카피에 맞추거나, G3에 한 줄 핵심 문구 복구.

---

## 6. 권장 조치 우선순위

| 순위 | 항목 | 노력 |
|------|------|------|
| 1 | **H1** Git 설치 exe 해시/Authenticode 검증 | 중 |
| 2 | **M2** `x-access-token:` URL·stderr 마스킹 강화 | 소 |
| 3 | **M6** branch 이름 검증 | 소 |
| 4 | **M1** cred 임시파일 orphan 청소·ACL | 소~중 |
| 5 | **M4** 내용 시크릿 휴리스틱 (soft) | 중 |
| 6 | **M3** fine-grained scope unknown 처리 | 소 |
| 7 | PII 스크립트 ↔ G3 문구 재동기화 | 소 |
| 8 | P2 코드 서명 (배포 신뢰) | 비용 |

---

## 7. 결론

CloneUp의 **핵심 보안 설계는 코드에 실재**하며, Desktop 대비 차별점(공개 Device Flow 회피, 토큰 remote 비삽입, 비밀 파일명 G3)은 교차검증 **PASS**.

**즉시 패치가 필요한 Critical은 없음.**  
다음 보안 스프린트 후보: **설치 파일 무결성(H1)** + **마스킹/branch 하드닝(M2·M6)** + **교차검증 스크립트 동기화**.

---

## 재검증 방법 (개발자)

```powershell
# PII/safety 교차
.\.venv\Scripts\python.exe scripts\verify_pii_crosscheck.py

# 수동 스모크
# - 로그인 후 .git/config 에 토큰 없는지
# - 공개 저장소 클론 URL에 토큰 없는지
# - 로그 창에 ghp_/github_pat_ 전체가 안 보이는지
# - Device Flow: CLONEUP_ALLOW_DEVICE_FLOW 미설정 시 UI에 안 뜸
```
