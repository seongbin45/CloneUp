# 마스터 비밀번호로 키 보호

기준: Phase 1–3 구현 (`secret_crypto` · `secret_vault` · `token_store` · 설정 → 안전 UI).

CloneUp은 GitHub 키(PAT)를 **OS keyring**에 둡니다.  
추가로 **마스터 비밀번호 보호**를 켜면, keyring에는 평문 키가 아니라 암호문만 남고  
일상 사용(올리기·받기·동기화)에서는 비밀번호를 **다시 묻지 않습니다**.

---

## 사용자 안내

### 켜는 방법

1. 설정 → **안전**
2. 「마스터 비밀번호로 키 보호」에서 **보호 켜기**
3. 새 비밀번호(최소 8자) + 확인 입력

이미 연결해 둔 키가 있으면 그때 암호화됩니다.  
키가 없어도 보호만 먼저 켤 수 있고, 다음에 연결하는 키가 자동으로 암호화됩니다.

### 일상 사용

- 올리기 / 받기 / 동기화 / 권한 다시 확인 → **마스터 비밀번호 없음**
- Windows에 로그인한 **같은 사용자**로 CloneUp을 쓰면 DPAPI가 DEK를 풀어 줍니다

### 바꾸기 · 끄기

| 동작 | 설정 → 안전 | 비고 |
|------|-------------|------|
| 비밀번호 바꾸기 | **비밀번호 바꾸기** | 현재 비밀번호 검증 후 재포장 |
| 보호 끄기 | **보호 끄기** | 키를 다시 keyring 평문으로 되돌림 (OS keyring은 유지) |

### 잊어버렸을 때

- 마스터 비밀번호는 **디스크에 저장되지 않으며 복구 수단이 없습니다**
- **같은 Windows 계정**이면 앱은 계속 키를 쓸 수 있습니다 (DPAPI)
- 보호를 끄거나 비밀번호를 바꾸려면 마스터 비밀번호가 필요합니다
- 끄지 못하고 Windows 계정도 잃었다면: GitHub에서 해당 키를 폐기하고 CloneUp에서 **다시 연결**

---

## 무엇이 보호되고, 무엇이 아닌가

### 보호하는 것

- keyring을 덤프했을 때 **평문 PAT가 바로 보이지 않음** (`enc.v1.…` 암호문)
- 마스터 비밀번호 없이 vault 파일만 훔쳐도 DEK를 바로 얻지 못함 (DPAPI는 **현재 Windows 사용자**에 묶임)
- `%LOCALAPPDATA%\CloneUp\secret\` 디렉터리 ACL을 현재 사용자로 조이는 **최선의 시도** (`icacls`)

### 보호하지 않는 것 (한계)

| 상황 | 설명 |
|------|------|
| 동일 Windows 사용자로 실행되는 악성코드 | DPAPI를 호출해 DEK를 풀 수 있음 |
| 실행 중 메모리 | 복호화된 PAT는 다른 데스크톱 앱과 같은 한계 |
| 클립보드에 붙여 넣은 순간 | 연결 마법사 중 평문이 잠깐 존재 |
| “앱 exe를 암호화해 키를 심는” 방식 | **안전하지 않음** — 배포 바이너리에서 키가 추출됨. CloneUp은 이 방식을 쓰지 않음 |
| 마스터 비밀번호 분실 + Windows 계정 이전 | 보호 끄기/변경 불가 → 키 재발급 |

기본 상태(보호 꺼짐)에서도 토큰은 OS keyring에만 두고 `.env` / `.git/config`에는 두지 않습니다.

---

## 저장 구조

```
OS keyring (서비스 CloneUp)
  github_oauth_access_token
    · 보호 OFF → 평문 PAT
    · 보호 ON  → enc.v1.<urlsafe-base64(AES-GCM 암호문)>
  (+ scope / note / expires … 메타 — 암호화 대상 아님)

%LOCALAPPDATA%\CloneUp\secret\
  wrap.json    WrappedDek (PBKDF2 + AES-GCM) — Settings 검증·변경용
  dek.dpapi    DEK를 Windows DPAPI(CryptProtectData)로 감싼 바이트
```

**마스터 비밀번호 파일은 없습니다.**

---

## 암호 흐름 (개발자)

| 단계 | 모듈 | 요약 |
|------|------|------|
| DEK 생성 | `secret_crypto.generate_dek` | 32바이트 |
| PAT 봉인 | `encrypt_token` / AAD `CloneUp-pat-v1` | AES-GCM, wire = nonce\|\|ct+tag |
| 마스터로 DEK 포장 | `wrap_dek_with_password` | PBKDF2-HMAC-SHA256 **600k**, salt 16B |
| 일상 잠금 해제 | `dpapi_win` + `secret_vault.load_dek` | CryptUnprotectData (+ entropy) |
| 저장/로드 | `token_store.save_token` / `load_token` | 보호 ON이면 `enc.v1.` 자동 |

Settings API (UI 없음 호출도 가능):

- `enable_master_protection(password)`
- `change_master_password(old, new)`
- `disable_master_protection(password)`
- `master_protection_enabled()` / `is_token_encrypted()`

UI: `app/ui/settings_dialog.py` — 안전 탭 카드 + `prompt_master_password_*`.

---

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_secret_crypto.py tests/test_secret_vault.py tests/test_master_protection_settings.py -q
```

| 파일 | 범위 |
|------|------|
| `test_secret_crypto.py` | Phase 1 순수 암호 (keyring/DPAPI 없음) |
| `test_secret_vault.py` | vault 파일 · DPAPI roundtrip · token_store 마이그레이션 |
| `test_master_protection_settings.py` | 비밀번호 최소 길이 헬퍼 |

Windows에서 DPAPI 테스트가 돌아갑니다. 비-Windows는 해당 케이스가 skip됩니다.

---

## 관련 문서 · 코드

| 위치 | 내용 |
|------|------|
| [app/auth/README.md](../app/auth/README.md) | 인증 폴더 지도 |
| [DIFFERENTIATION.md](DIFFERENTIATION.md) V1 | PAT 기본 · Device Flow 회피 |
| [SECURITY_CROSS_VERIFY.md](SECURITY_CROSS_VERIFY.md) | 보안 교차검증 (keyring A9 등) |
| `app/auth/secret_crypto.py` | 순수 암호 |
| `app/auth/secret_vault.py` | vault + DPAPI + `enc.v1.` |
| `app/auth/dpapi_win.py` | CryptProtect/Unprotect |
| `app/auth/token_store.py` | 저장/로드/마이그레이션 API |
| `app/ui/settings_dialog.py` | 설정 → 안전 UI |
