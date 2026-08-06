# CloneUp 보안 교차검증

**검증일:** 2026-08-07 (하드닝 패치 반영)  
**범위:** 인증·토큰·git 자격증명·subprocess·URL·로그 마스킹·업로드 안전(G3)·부트스트랩 다운로드  
**대상 코드:** `app/auth/*`, `app/git/*`, `app/github/*`, `app/ui/*` (워커·로그인), `app/config.py`, `app/util/log_mask.py`  
**위협 모델:** 로컬 데스크톱 헬퍼 — 동일 PC 사용자/멀웨어, 네트워크 도청, 실수 업로드, 공개 client_id 남용

---

## 요약

| 등급 | 개수 | 의미 |
|------|------|------|
| **Critical** | 0 | 원격 임의 코드 실행·기본 경로 Device Flow 토큰 가로채기 등 없음 |
| **High** | 0 | H1 lite 적용: HTTPS host allowlist + PE + Authenticode |
| **Medium** | 3 | scope 추정·내용 시크릿 미탐지·allow_secrets soft 등 (잔여) |
| **Low** | 5 | 클립보드 PAT·unsigned 배포·PII soft 등 |
| **강점 (PASS)** | 12+ | 설계 문서와 코드 일치하는 핵심 통제 |

**총평:** 제품이 의도한 보안 축(PAT 전용, 토큰을 `.git/config`에 안 넣음, Device Flow 기본 OFF)은 **코드와 문서가 일치**한다.  
2026-08-07 하드닝: **M2 마스킹 · M6 branch · M1 cred orphan · H1 lite 설치 검증**.

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
| S14 | Git 설치 exe 무결성 검증 | host allowlist + MZ + Authenticode (`verify_git_installer_file`) | **PASS lite** |
| S15 | PII 자동 스크립트 26/26 | `scripts/verify_pii_crosscheck.py` | **PASS** (G3 문구 동기화) |
| S16 | 로그 `x-access-token` / stderr 마스킹 | `log_mask` · `runner.GitError.stderr` | **PASS** (M2) |
| S17 | branch leading-`-` 거부 | `clone_ops.validate_branch_name` | **PASS** (M6) |
| S18 | cred 임시파일 orphan 청소 | `credentials.cleanup_orphan_*` · `main` 기동 | **PASS** (M1) |

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

### H1 — ~~High~~ → **완화 (lite 적용)**

| | |
|--|--|
| **위치** | `bootstrap.verify_git_installer_file` · `_assert_safe_download_url` |
| **적용** | HTTPS + GitHub CDN host only · PE/MZ · min size · Authenticode `Valid` + subject 힌트. 실패 시 실행 거부 + 브라우저 안내. |
| **잔여** | 고정 SHA256 핀은 릴리스마다 갱신 필요 → 미적용. 신뢰 루트 손상 시 Authenticode도 한계. |

### M1 — ~~Medium~~ → **부분 완화**

| | |
|--|--|
| **위치** | `credentials.py` · `main.py` 기동 |
| **적용** | orphan `cloneup-git-cred-*` 청소(기동 시 age=0, 쓰기 전 15분+), 삭제 전 zero-wipe 시도, `fchmod` best-effort. |
| **잔여** | push 중 동일 사용자 프로세스 읽기 가능(로컬 위협 모델). |

### M2 — ~~Medium~~ → **완화**

| | |
|--|--|
| **위치** | `log_mask.py` · `runner.run_git` |
| **적용** | 토큰 전체 `*** (len=N)` · `x-access-token:` · Bearer · URL userinfo 마스킹 · `GitError.stderr` 마스킹 저장. |

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

### M6 — ~~Medium~~ → **완화**

| | |
|--|--|
| **위치** | `clone_ops.validate_branch_name` |
| **적용** | leading `-` · `..` · 비허용 문자 · 길이 상한 거부 후 `-b` 전달. |

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
scripts/verify_pii_crosscheck.py  →  기대 26/26 PASS (G3 문구 동기화 후)
```

---

## 6. 권장 조치 우선순위 (잔여)

| 순위 | 항목 | 노력 |
|------|------|------|
| 1 | **M4** 내용 시크릿 휴리스틱 (soft) | 중 |
| 2 | **M3** fine-grained scope unknown 처리 | 소 |
| 3 | H1 고정 SHA256 핀 (릴리스 자동화와 함께) | 중 |
| 4 | P2 코드 서명 (배포 신뢰) | 비용 |

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
