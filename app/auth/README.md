# `app/auth/` — GitHub 로그인

**제품 기본: PAT(키)만.**  
공개 OAuth `client_id` + Device Flow는 악성 앱이 동일 승인 화면으로 토큰을 가로챌 수 있어 **기본 차단**.

| 경로 | 상태 |
|------|------|
| PAT (`login_with_pat`) | **기본** — UI 「GitHub: 로그인」 |
| Device Flow | `CLONEUP_ALLOW_DEVICE_FLOW=1` 일 때만 (개발용) |
| `ensure_valid_token` | keyring 검증만. **자동 Device Flow 시작 안 함** |

토큰은 OS **keyring**에만. `.env`·`.git/config`에 두지 않음.  
맥락: `docs/DIFFERENTIATION.md` V1.

## 파일

| 파일 | 역할 |
|------|------|
| `device_flow.py` | device/code 요청, 폴링, 브라우저 URL (코드 미리 넣기 안 함) |
| `session.py` | `ensure_valid_token`, `login_device_flow`, **`login_with_pat`**, 401 시 재인증 |
| `token_store.py` | keyring 저장/삭제/scope·**auth_kind** 확인 |
| `playwright_device.py` | 선택 실험 (`CLONEUP_PLAYWRIGHT=1`) — 기본 경로 아님 |

## 초심자: 언제 수정하나

| 증상 / 요구 | 볼 파일 |
|-------------|---------|
| 로그인 실패 메시지 | `device_flow.py`, `session.py` |
| PAT 검증·문구 | `session.py` → `login_with_pat` |
| 로그인 방식 UI | `app/ui/login_dialog.py` |
| 로그아웃이 안 됨 | UI에서 `delete_token` 호출 + `token_store.py` |
| 권한(scope) 바꾸고 싶음 | `app/config.py` 기본값 또는 `.env`의 `GITHUB_SCOPES` (일반 사용자 불필요) |

## 테스트

```powershell
.\.venv\Scripts\python.exe spike_device_flow.py
.\.venv\Scripts\python.exe spike_device_flow.py --force
# PAT (대화형 — 토큰을 환경변수로만 전달, 셸 히스토리 주의)
$env:CLONEUP_PAT = "ghp_…"; .\.venv\Scripts\python.exe -c "from app.auth.session import login_with_pat; import os; login_with_pat(os.environ['CLONEUP_PAT'])"
```

## 변경 후 배포 시

로그인 관련 수정 → Device Flow **또는** PAT로 한 번 로그인 확인 후  
루트 README 3장(커밋·병합) → 4장(Setup 빌드).

관련 UI: `app/ui/login_dialog.py`, `device_code_dialog.py`,  
`publish_worker.py` (`LoginWorker`, `PatLoginWorker`).
