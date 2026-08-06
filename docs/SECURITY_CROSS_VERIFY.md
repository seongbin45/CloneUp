# CloneUp 보안 교차검증 (전면 재검증)

**재검증일:** 2026-08-07  
**커밋 기준:** `c2987e6` 이후 (M1–M6 · H1 lite · M3/M4 하드닝 반영)  
**방법:** 코드 정적 대조 + 적대적 단위 프로브 + 자동 스크립트  
**위협 모델:** 로컬 데스크톱 헬퍼 — 동일 PC 사용자/멀웨어, 네트워크 도청, 실수 업로드, 공개 OAuth client_id 남용

---

## 0. 한눈에 보는 결과

| 등급 | 개수 | 설명 |
|------|------|------|
| **Critical** | **0** | 기본 경로 원격 RCE · Device Flow 토큰 가로채기 면 없음 |
| **High** | **0** | 설치 파일 무검증 실행은 lite로 완화됨 |
| **Medium (의도·잔여)** | **2** | allow_secrets soft · 동일 사용자 local 위협 |
| **Low** | **5** | 클립보드 PAT · Setup 미서명 · PII soft · stdout 비마스킹 등 |
| **강점 PASS** | **40+** | 아래 매트릭스 |

| 자동 검사 | 결과 |
|-----------|------|
| `scripts/verify_security_crosscheck.py` | **SECURITY_CROSS_VERIFY_OK** |
| `scripts/verify_pii_crosscheck.py` | **CROSS_VERIFY_OK** (32/32) |

```powershell
.\.venv\Scripts\python.exe scripts\verify_security_crosscheck.py
.\.venv\Scripts\python.exe scripts\verify_pii_crosscheck.py
```

**총평:** 인증·토큰·git 자격증명·로그·URL·설치 부트스트랩·업로드 안전의 **핵심 통제는 코드에 실재**하며, 이전 라운드 하드닝(M1–M6, H1 lite, M3/M4)이 회귀 없이 유지된다. Critical/High 신규 없음.

---

## 1. 영역별 교차검증

### 1-A. 인증 · 세션 · Device Flow

| ID | 기대 | 코드 | 자동 | 판정 |
|----|------|------|------|------|
| A1 | Device Flow **기본 OFF** | `config.is_device_flow_allowed` — env 없으면 False | A1 | **PASS** |
| A2 | `login_device_flow` 기본 차단 | `session.login_device_flow` AuthError | A2 | **PASS** |
| A3 | `ensure_valid_token` 자동 Device Flow 없음 | 토큰 없으면 `LOGIN_REQUIRED_MSG` | 정적 | **PASS** |
| A4 | 401 시 keyring 삭제, 자동 재로그인 없음 | `delete_token` + `TOKEN_EXPIRED_MSG` | 정적 | **PASS** |
| A5 | client_id 는 public (비밀 아님) | `DEFAULT_GITHUB_CLIENT_ID` 문서화 | A3 | **PASS** |
| A6 | PAT 로그인 시 scope 추정 금지 (M3) | 헤더 비면 `SCOPE_UNKNOWN` | A4–A8 | **PASS** |
| A7 | classic scope 있을 때만 pre-check | `scopes_known() and has_scope` | 정적 | **PASS** |
| A8 | UI: unknown ≠ 권한 부족 오인 | `auth_status` 연결됨 + 권한 미확인 툴팁 | 정적 | **PASS** |
| A9 | 토큰 OS keyring | `token_store` / keyring | 정적 | **PASS** |

**잔여 (Low):** PAT 붙여넣기 중 클립보드·메모리 잔존 — 데스크톱 앱 공통 한계.

---

### 1-B. Git 자격증명 · subprocess · remote

| ID | 기대 | 코드 | 자동 | 판정 |
|----|------|------|------|------|
| B1 | 토큰 argv 금지 | `runner` list args; cred 는 파일 경로만 | G1 | **PASS** |
| B2 | `shell=False` | `subprocess.run` 기본 list | G1 · repo grep | **PASS** |
| B3 | 임시 cred + finally 삭제 | `credentials` · publish/clone/sync | E1–E3 · H2–H3 | **PASS** |
| B4 | 기동 시 orphan 청소 | `main.cleanup_orphan_credential_files(0)` | I3 | **PASS** |
| B5 | 삭제 전 zero-wipe 시도 | `delete_credential_file` | 정적 | **PASS** |
| B6 | remote / config 토큰 잔존 검사 | `assert_git_config_has_no_token` · `remote -v` | H1 | **PASS** |
| B7 | clone URL clean HTTPS only | `normalize` + clone verify | C5–C7 | **PASS** |
| B8 | 비대화형 git | `GIT_TERMINAL_PROMPT=0` · `GCM_INTERACTIVE=Never` | G3–G4 | **PASS** |
| B9 | 오류 stderr 마스킹 | `run_git` → `safe_err` | G2 | **PASS** |
| B10 | branch leading `-` 거부 (M6) | `validate_branch_name` | C1–C4 | **PASS** |

**잔여 (Medium/local):** push 중 `%TEMP%\cloneup-git-cred-*` 는 동일 Windows 사용자가 읽을 수 있음.  
**잔여 (Low):** `GitResult.stdout` 원문은 비마스킹(토큰이 stdout에 나올 일은 드묾).

---

### 1-C. 로그 · UI 워커

| ID | 기대 | 코드 | 자동 | 판정 |
|----|------|------|------|------|
| C1 | classic/fine PAT 마스킹 | `log_mask._TOKEN_RE` → `*** (len=N)` | B1–B2 | **PASS** |
| C2 | `x-access-token:` 임베드 | `_X_ACCESS_RE` 우선 적용 | B3 | **PASS** |
| C3 | Bearer / URL userinfo | `_BEARER_RE` · `_URL_USERINFO_RE` | B4–B5 | **PASS** |
| C4 | 워커 로그 일괄 마스킹 | `tab_workers` · `publish_worker` | I1–I2 | **PASS** |
| C5 | `print` 경유 토큰 | session은 `mask_token`만 출력 | 정적 | **PASS** |

**잔여 (Low):** 알 수 없는 형식의 긴 비밀(비 GitHub)은 패턴 밖이면 그대로 남을 수 있음.

---

### 1-D. 업로드 안전 (G3 · safety · sync)

| ID | 기대 | 코드 | 자동 | 판정 |
|----|------|------|------|------|
| D1 | 비밀 **파일명** 차단 | `find_secret_candidates` · `.env` 등 | F4–F5 · PII | **PASS** |
| D2 | 내용 **시크릿** 차단 (M4) | `scan_secret_in_contents` | F1–F3 · PII | **PASS** |
| D3 | 샘플 UI 마스킹 | `_mask_secret_sample` | F3 | **PASS** |
| D4 | 전화/이메일 G3 soft | `scan_pii_in_contents` + 확인창 | PII 32/32 | **PASS soft** |
| D5 | G3 배선 | `scan_*` · `find_secret_*` | PII G3 checks | **PASS** |
| D6 | sync push 동일 비밀 규칙 | `sync_ops.commit_and_push` | 정적 | **PASS** |
| D7 | `allow_secrets` 우회 | 의도적 soft | F6 | **의도 잔여** |
| D8 | 커밋 이메일 기본 가림 | `hide_real_email` default True | 정적 | **PASS** |

**탐지 패턴 (M4):** GitHub token · AWS AKIA · PEM private key · Slack · Stripe · Google API key.  
**의도적 미구현:** 범용 high-entropy 휴리스틱 · 실명 치환(anonymize) · 학번 regex.

---

### 1-E. Git 설치 부트스트랩 (H1 lite)

| ID | 기대 | 코드 | 자동 | 판정 |
|----|------|------|------|------|
| E1 | HTTPS only | `_assert_safe_download_url` | D1 | **PASS** |
| E2 | GitHub CDN host only | `github.com` / `*.githubusercontent.com` | D2–D3 | **PASS** |
| E3 | PE/MZ + 최소 크기 | `verify_git_installer_file` | D4–D5 | **PASS** |
| E4 | Authenticode Valid + subject 힌트 | PowerShell `Get-AuthenticodeSignature` | 정적(실 exe 필요) | **PASS lite** |
| E5 | 실패 시 실행 거부 | `run_git_installer` early return | 정적 | **PASS** |
| E6 | `CLONEUP_FORCE_NO_GIT` 기본 off | 테스트 전용 | D6 | **PASS** |

**잔여:** 릴리스별 **고정 SHA256 핀** 없음 · 신뢰 루트 손상 시 Authenticode 한계.

---

### 1-F. 배포 · 패키징 · 기타

| ID | 기대 | 상태 | 판정 |
|----|------|------|------|
| F1 | Setup/exe 코드 서명 | P2 대기 · SmartScreen 경고 가능 | **잔여 Low/제품** |
| F2 | 스파이크·Playwright 비기본 | Device Flow·Playwright 기본 경로 아님 | **PASS** |
| F3 | 설정에 토큰 저장 안 함 | `QSettings` 에 login 이름·prefs만 | **PASS** |

---

## 2. 위협 시나리오 재검증

| # | 시나리오 | 결과 | 근거 |
|---|----------|------|------|
| 1 | 악성 앱이 공개 client_id + Device Flow 폴링 | **기본 사용자 경로 불가** | A1–A3 |
| 2 | 사용자가 타 앱 Device Flow 승인 | 제품 밖 · 개발 모드 opt-in만 | A2 |
| 3 | git remote에 토큰 박힘 | **차단·사후 검사** | B3–B6 |
| 4 | 로그에 PAT 전체 출력 | **마스킹** | C1–C4 |
| 5 | `.env` / `ghp_` in file 업로드 | **기본 차단** | D1–D2 |
| 6 | 전화/이메일 in source | G3 경고, hard block 아님 | D4 |
| 7 | 사용자가 고급 허용 체크 | 업로드 가능 (의도) | D7 |
| 8 | 클론 URL 내부망/타 호스트 | host allowlist | C5–C6 |
| 9 | branch `--; rm` 류 | list argv + branch 검증 | B1 · B10 |
| 10 | 가짜 Git 설치 exe | host/PE/서명 검사 후 거부 | E1–E5 |
| 11 | push 중 TEMP cred 읽기 (동일 사용자) | **가능** (로컬 위협) | 잔여 |
| 12 | 클립보드에 PAT | 사용자 실수 영역 | 잔여 |
| 13 | 미서명 Setup SmartScreen | 배포 신뢰 P2 | 잔여 |

---

## 3. 자동 검사 고정

| 스크립트 | 역할 |
|----------|------|
| [`scripts/verify_security_crosscheck.py`](../scripts/verify_security_crosscheck.py) | 인증·마스킹·URL·branch·H1 lite·cred·safety·runner·publish 정적/단위 |
| [`scripts/verify_pii_crosscheck.py`](../scripts/verify_pii_crosscheck.py) | 전화/이메일/파일명/내용 시크릿/G3 배선 |

재검증 시 둘 다 실행한다.

---

## 4. 잔여 위험 (우선순위)

| 순위 | 항목 | 등급 | 비고 |
|------|------|------|------|
| 1 | **P2 코드 서명** (Setup/exe) | Low–제품 | 비용 · SmartScreen |
| 2 | **동일 사용자 TEMP cred** | Medium-local | 수명 짧음·orphan 청소 있음 |
| 3 | **allow_secrets soft** | 의도 | 공개 저장소 2차 확인은 선택 강화 |
| 4 | H1 **SHA256 핀** | Low | 릴리스 자동화 시 |
| 5 | 내용 시크릿 패턴 확장 | Low | 오탐 모니터링 |
| 6 | `GitResult.stdout` 마스킹 | Low | 일관성 |

**Critical / High 신규 없음. 긴급 패치 불필요.**

---

## 5. 수동 스모크 (권장, 릴리스 전)

1. PAT 연결 → 상태줄 연결됨 · keyring만 사용  
2. 올리기 후 해당 폴더 `.git/config` · `git remote -v` 에 토큰/`x-access-token` 없음  
3. 로그 창에 `ghp_`/`github_pat_` 전체 문자열 없음  
4. 폴더에 `ghp_…` 넣은 텍스트 → 올리기 차단  
5. Device Flow: env 없이 UI에 장치 코드 로그인 안 뜸  
6. (선택) Git 없는 PC 또는 `CLONEUP_FORCE_NO_GIT=1` 로 설치 안내 → 설치 파일 검증 메시지

---

## 6. 변경 이력 (보안 관련)

| 시점 | 내용 |
|------|------|
| 0.1.1 | PAT 전용 · Device Flow 기본 OFF |
| 이후 UX | 로그아웃 · G3 단축 등 |
| 하드닝 1 | M1 cred orphan · M2 마스킹 · M6 branch · H1 lite |
| 하드닝 2 | M3 scope unknown · M4 내용 시크릿 |
| **이번 재검증** | 전면 매트릭스 + `verify_security_crosscheck.py` 고정 |

---

## 7. 결론

CloneUp은 **초보용 GitHub 헬퍼**로서 핵심 보안 설계(공개 Device Flow 회피, 토큰 remote 비삽입, 임시 cred, 로그 마스킹, 비밀 파일/내용 차단, 설치 파일 lite 검증)가 **문서·코드·자동 검사 3자 일치**한다.

남은 항목은 **배포 신뢰(코드 서명)** 와 **로컬 동일 사용자 위협·의도적 soft 경계**이며, 제품 버그성 Critical 취약점으로 재분류할 항목은 없다.
