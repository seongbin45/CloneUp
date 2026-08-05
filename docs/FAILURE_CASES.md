# CloneUp — 실패 케이스 체크리스트

스파이크·UI 공통. **성공 경로만 보고 넘어가지 말 것.**  
기준 코드: `app/git/safety.py`, `app/git/publish.py`, `app/auth/session.py`, `app/github/api_client.py`.

---

## 0. 확인 방법

| 방법 | 명령 예 |
|------|---------|
| Publish 스파이크 | `.\.venv\Scripts\python.exe spike_publish.py --folder <경로>` |
| 인증만 | `.\.venv\Scripts\python.exe spike_device_flow.py` |
| 저장소 생성만 | `.\.venv\Scripts\python.exe spike_create_repo.py --name ...` |

기대: **hang 없이** 끝나거나, 한국어로 원인을 말함.  
절대: 토큰이 `.git/config` / `git remote -v` / 로그 평문에 남지 않음.

---

## 1. 사전 조건 (환경)

| ID | 상황 | 기대 동작 | 구현 위치 |
|----|------|-----------|-----------|
| E1 | Git 미설치 / PATH 없음 | 설치 안내 후 중단 | `runner.require_git` |
| E2 | Git &lt; 2.28 | `init` + `symbolic-ref` 로 main 설정 | `publish._init_repo_main` |
| E3 | Git ≥ 2.28 | `git init -b main` | 동일 |
| E4 | 네트워크 없음 | API/push 실패, hang 없음 | requests / `GIT_TERMINAL_PROMPT=0` |
| E5 | `user.name`/`user.email` 없음 | global 수정 없이 `-c` 로 noreply 주입 | `resolve_commit_identity` |
| E6 | identity 이미 있음 | **덮어쓰지 않음** | 동일 |

---

## 2. 인증

| ID | 상황 | 기대 동작 | 구현 위치 |
|----|------|-----------|-----------|
| A1 | keyring 토큰 없음 | Device Flow 시작 | `ensure_valid_token` |
| A2 | 토큰 유효 | GET /user 성공, scope 표시 | 동일 |
| A3 | 토큰 401 (권한 취소 등) | keyring 삭제 → **자동** Device Flow | 동일 |
| A4 | Device Flow 미활성 OAuth App | 400 + Enable Device Flow 힌트 | `device_flow` |
| A5 | 승인 거부 / 시간 초과 | 명확한 메시지, hang 없음 | `device_flow` |
| A6 | 저장된 scope 없음 | `X-OAuth-Scopes` backfill | `session` |

---

## 3. 안전성 (Publish 전) — **필수 수동 확인**

| ID | 상황 | 기대 동작 | 구현 위치 |
|----|------|-----------|-----------|
| S1 | **빈 폴더** (파일 0개, `.git` 제외) | 중단: 「빈 폴더…」 | `safety.is_effectively_empty` |
| S2 | 폴더 경로 없음 / 파일임 | 중단 | `run_safety_checks` |
| S3 | **비밀 파일** (`.env`, `*.pem`, `id_rsa` 등) | 기본 **중단** + 목록 | `find_secret_candidates` |
| S4 | 비밀 파일 + `--allow-secrets` | 경고 후 진행 가능 | `run_safety_checks` |
| S5 | `.gitignore` 없음 | 기본 템플릿 생성 + 경고 | `ensure_gitignore` |
| S6 | 전부 gitignore 되어 staged 0 | 중단: staging 비었음 | `publish` after `add -A` |

### 수동 재현 (S1 / S3)

```powershell
# S1 빈 폴더
mkdir $env:TEMP\cloneup-empty
.\.venv\Scripts\python.exe spike_publish.py --folder $env:TEMP\cloneup-empty --name cloneup-fail-empty
# 기대: ERROR … 빈 폴더

# S3 비밀 파일
mkdir $env:TEMP\cloneup-secret
echo x > $env:TEMP\cloneup-secret\hello.txt
echo SECRET=1 > $env:TEMP\cloneup-secret\.env
.\.venv\Scripts\python.exe spike_publish.py --folder $env:TEMP\cloneup-secret --name cloneup-fail-secret
# 기대: ERROR … 비밀 파일 … .env
```

---

## 4. 로컬 Git 상태

| ID | 상황 | 기대 동작 | 구현 위치 |
|----|------|-----------|-----------|
| G1 | `.git` 없음 | `init -b main` (또는 fallback) 후 진행 | `publish` |
| G2 | **`.git` 있음 + `origin` 이미 있음** | **중단** (스파이크 3은 새 경로만) | `publish_local_to_existing_remote` |
| G3 | `.git` 있음 + origin 없음 | remote add 만 하고 커밋/push | 동일 |
| G4 | push 후 `.git/config` | 토큰 / `x-access-token` **없음** | `assert_git_config_has_no_token` |
| G5 | `git remote -v` | clean HTTPS URL 만 | push 직후 검사 |

### 수동 재현 (G2)

```powershell
# 이미 origin 있는 폴더 (예: 이 프로젝트 자체)
.\.venv\Scripts\python.exe spike_publish.py --folder . --name should-not-create
# 기대: ERROR … 이미 origin remote 가 있습니다
```

---

## 5. GitHub API (저장소 생성)

| ID | 상황 | 기대 동작 | 구현 위치 |
|----|------|-----------|-----------|
| R1 | 성공 (public, 빈 원격) | `full_name`, `html_url`, `clone_url` | `create_repo` |
| R2 | **422 이름 중복** | 이름 변경 안내 | `spike_create_repo` / PublishError |
| R3 | **403 scope 부족** | `repo` 권한 재로그인 안내 | session / API |
| R4 | **401 토큰 무효** | 세션 계층 재로그인 또는 안내 | session + API |
| R5 | `auto_init=True` 요청 | **거부** (필드 전송 안 함) | `create_repo` |
| R6 | private 생성 | `private: true` + scope `repo` (앱 기본) | `create_repo` |
| R7 | DELETE | delete_repo 없으면 웹 수동 삭제 | 문서상 제약 |

---

## 6. Push / 자격증명

| ID | 상황 | 기대 동작 | 구현 위치 |
|----|------|-----------|-----------|
| P1 | 정상 push | HEAD → origin, `-u` | `publish` |
| P2 | 임시 cred 파일 | `…@github.com/` (끝 슬래시), finally 삭제 | `_write_credential_file` |
| P3 | helper 순서 | `helper=` 클리어 후 `store --file=` | `_credential_helper_configs` |
| P4 | GCM/대화형 | 프롬프트 없이 실패 또는 성공 | `env.noninteractive_git_env` |
| P5 | 원격에 이미 커밋 (`auto_init` 실수) | non-fast-forward 실패 메시지 | (예방: auto_init 금지) |
| P6 | 토큰 argv 노출 | **금지** — 파일/env helper 만 | 설계 규칙 |

---

## 7. UI(Publish 탭) 연동 시 같은 표

버튼 **「GitHub에 만들고 올리기」** 클릭 시:

1. 입력 검증 (폴더·이름) → S2  
2. `ensure_valid_token` → A*  
3. `run_safety_checks` → **S1, S3** 실패 시 모달, 진행 안 함  
4. 백그라운드 스레드에서 publish (UI 스레드 `subprocess` 금지)  
5. 로그 창에 단계 출력 (토큰 마스킹)  
6. 실패 시 위 ID를 사용자 문구에 매핑  
7. 성공 시 `html_url` 열기 + G4 검사 결과 표시  

---

## 8. 스파이크 통과 기준 (요약)

- [ ] S1 빈 폴더 → 실패 메시지  
- [ ] S3 `.env` 포함 → 실패 메시지  
- [ ] G2 origin 이미 있음 → 실패 메시지  
- [ ] 정상 폴더 → 원격에 파일 보임  
- [ ] 성공 후 `.git/config` 에 토큰 없음  
- [ ] R5 `auto_init` 바디에 없음  

---

## 9. 테스트용 저장소 이름

DELETE 는 웹에서. 테스트 저장소 이름은 묶어서 지우기 쉽게:

- `cloneup-spike-YYYYMMDD-HHMM`
- `cloneup-publish-YYYYMMDD-HHMM`
- `cloneup-fail-*` (의도적 실패 실험, 생성 전이면 원격 없음)
