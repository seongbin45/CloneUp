# `app/auth/` — GitHub 로그인 (Device Flow)

브라우저로 장치 코드를 승인받아 **access token**을 받고,  
OS **keyring**에 저장합니다. `.env`에 토큰을 두지 않습니다.

## 파일

| 파일 | 역할 |
|------|------|
| `device_flow.py` | device/code 요청, 폴링, 브라우저 URL (코드 미리 넣기 안 함) |
| `session.py` | `ensure_valid_token`, 강제 재로그인, 401 시 재인증 |
| `token_store.py` | keyring 저장/삭제/scope 확인 |
| `playwright_device.py` | 선택 실험 (`CLONEUP_PLAYWRIGHT=1`) — 기본 경로 아님 |

## 초심자: 언제 수정하나

| 증상 / 요구 | 볼 파일 |
|-------------|---------|
| 로그인 실패 메시지 | `device_flow.py`, `session.py` |
| 로그아웃이 안 됨 | UI에서 `delete_token` 호출 + `token_store.py` |
| 권한(scope) 바꾸고 싶음 | `app/config.py` 기본값 또는 `.env`의 `GITHUB_SCOPES` (일반 사용자 불필요) |

## 테스트

```powershell
.\.venv\Scripts\python.exe spike_device_flow.py
.\.venv\Scripts\python.exe spike_device_flow.py --force
```

## 변경 후 배포 시

로그인 관련 수정 → **반드시 실제 Device Flow로 한 번 로그인** 후  
루트 README 3장(커밋·병합) → 4장(Setup 빌드).

관련 UI: `app/ui/device_code_dialog.py`, `app/ui/publish_worker.py` (LoginWorker).
