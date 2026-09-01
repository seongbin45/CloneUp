# CloneUp 0.1.9

0.1.8 위에 **부팅「안 올린 수정」알림**, **시작 프로그램 동기화**,  
**독립 자동 업데이트 관리자**를 묶은 패치 릴리스입니다.

## 사용자에게 알려 줄 말 (짧게)

1. 컴퓨터에 로그인한 뒤, 최근 폴더에 GitHub로 안 보낸 변경이 있으면 **작은 알림**으로 물어봅니다. (설정 → 안전에서 끌 수 있습니다.)
2. 「Windows 시작 시 트레이에서 대기」를 켜 두면 로그온 때 트레이만 뜹니다. 설정 ON과 시작 프로그램 등록이 맞춰집니다.
3. (선택) **자동 업데이트 관리자**를 설치하면, 메인 창이 열려 있지 않을 때 백그라운드에서 새 버전 zip을 받아 **설치 관리자 화면 없이** 파일을 교체합니다.
4. 알림에서 올려도 **비밀 파일 점검은 그대로**입니다.

## 설치

- `CloneUp-Setup.exe` 실행 → 약관 동의 → 설치  
- 작업 항목 **「백그라운드 자동 업데이트 관리자」** 기본 선택
- 0.1.8 위에 덮어쓰기 가능

## GitHub Release 자산 (필수)

| 파일 | 용도 |
|------|------|
| `CloneUp-Setup.exe` | 사람이 설치 |
| **`CloneUp-win64.zip`** | 업데이트 관리자용 (없으면 자동 업데이트 안 함) |

자세한 동작: [UPDATE_MANAGER.md](UPDATE_MANAGER.md) · [BOOT_NOTIFY.md](BOOT_NOTIFY.md)

## 개발자용 변경 요약 (0.1.8 → 0.1.9)

### 시작 알림 (boot notify)
- 트레이 `--tray` · 토스트 UI · recent dirty/ahead 스캔 · snooze/하루 1회
- 업로드 시 `allow_secrets=False`, `hide_real_email` 반영

### Autostart
- `boot_autostart_enabled` ↔ HKCU `CloneUpTray` 기동·설정 시 동기화

### Update manager (독립)
- `CloneUp_update_manager.exe` — 앱과 분리 설치·자동시작
- 10분마다 GitHub Releases zip 확인 → 메인 창 없으면 kill 후 파일 복사
- Setup.exe 미실행 (GUI 방지) · `unins*` 보존 · tasklist cp949 안전

## 검증

| 항목 | 상태 |
|------|------|
| `tests/test_boot_scan.py` | pass |
| `tests/test_autostart_win.py` | pass |
| `tests/test_update_manager.py` | pass |
| 실측: 설치 경로·ARP·zip 없으면 `no_release` | OK |
