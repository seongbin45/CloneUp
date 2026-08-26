# `app/auth/` — GitHub 연결

**제품 기본: 키(PAT)만.**  
공개 OAuth `client_id` + Device Flow는 악성 앱이 동일 승인 화면으로 토큰을 가로챌 수 있어 **기본 차단**.

| 경로 | 상태 |
|------|------|
| 키 / PAT (`login_with_pat`) | **기본** — UI 「GitHub: 연결」 |
| Device Flow | `CLONEUP_ALLOW_DEVICE_FLOW=1` 일 때만 (개발용) |
| `ensure_valid_token` | keyring 검증만. **자동 Device Flow 시작 안 함** |

토큰은 OS **keyring**에만. `.env`·`.git/config`에 두지 않음.  
선택: 설정 → 안전 **마스터 비밀번호 보호** — keyring에는 `enc.v1.…`만,  
일상 사용은 Windows DPAPI로 DEK 해제 (마스터 비번은 디스크에 안 둠).  
상세: [`docs/MASTER_PASSWORD_VAULT.md`](../../docs/MASTER_PASSWORD_VAULT.md).  
맥락: `docs/DIFFERENTIATION.md` V1.

## 파일

| 파일 | 역할 |
|------|------|
| `session.py` | `login_with_pat`, `ensure_valid_token` (제품 핵심) |
| `token_store.py` | keyring 저장/삭제/scope·auth_kind·연결 시각 · 마스터 보호 마이그레이션 |
| `secret_crypto.py` | 마스터 암호 순수 헬퍼 (AES-GCM · PBKDF2 · WrappedDek) |
| `secret_vault.py` | `%LOCALAPPDATA%\CloneUp\secret\` · DPAPI DEK · `enc.v1.` |
| `dpapi_win.py` | Windows CryptProtectData / CryptUnprotectData |
| `pat_urls.py` | classic PAT 생성 URL · Note |
| `token_expiry.py` | 연결·만료 표시 문구 |
| `device_flow.py` | Device Flow 프로토콜 (개발 옵션) |
| `playwright_device.py` | 선택 실험 (`CLONEUP_PLAYWRIGHT=1`) — 기본 경로 아님 |

## 초심자: 언제 수정하나

| 증상 / 요구 | 볼 파일 |
|-------------|---------|
| 키 연결 실패 메시지 | `session.py` → `login_with_pat` |
| 연결 방식 UI (마법사) | `app/ui/login_dialog.py` |
| 로그아웃이 안 됨 | UI `on_logout` + `token_store.delete_token` |
| 권한(scope) 기본값 | `app/config.py` (`repo`) — 일반 사용자 `.env` 불필요 |
| 마스터 비밀번호 켜기/끄기 | `token_store` API + `app/ui/settings_dialog.py` (안전 탭) |
| 암호·vault 버그 | `secret_crypto` / `secret_vault` / `docs/MASTER_PASSWORD_VAULT.md` |

## 테스트

### 제품 경로 (권장)

```powershell
.\.venv\Scripts\python.exe main.py
# 상태줄 「GitHub: 연결」→ 키 붙여넣기
# (선택) 설정 → 안전 → 「보호 켜기」
```

암호·vault 단위 테스트:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_secret_crypto.py tests/test_secret_vault.py tests/test_master_protection_settings.py -q
```

### 개발자 전용 (일반 사용자 불필요)

```powershell
# 키 검증만 (셸 히스토리에 토큰이 남을 수 있음 — 주의)
$env:CLONEUP_PAT = "ghp_…"; .\.venv\Scripts\python.exe -c "from app.auth.session import login_with_pat; import os; login_with_pat(os.environ['CLONEUP_PAT'])"

# Device Flow (기본 꺼짐 — 명시적으로 켤 때만)
$env:CLONEUP_ALLOW_DEVICE_FLOW = "1"
.\.venv\Scripts\python.exe spike_device_flow.py --force
```

## 변경 후 배포 시

연결 관련 수정 → 앱에서 키로 한 번 연결 확인 후  
루트 README 3장(커밋·병합) → 4장(Setup 빌드).

관련 UI: `app/ui/login_dialog.py`, `device_code_dialog.py`(개발),  
`publish_worker.py` (`PatLoginWorker`).
