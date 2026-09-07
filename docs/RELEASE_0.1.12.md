# CloneUp 0.1.12

관리자 권한으로 **전체 PC 설치**, 업데이트 매니저 경로·패키징 오류 수정.

## 사용자에게 알려 줄 말 (짧게)

1. Setup 실행 시 **관리자 권한(UAC)** 확인이 뜹니다. 허용하면 `Program Files`에 설치됩니다.
2. 자동 업데이트 관리자는 `%PROGRAMDATA%\CloneUp\UpdateManager\`에 두고, **작업 스케줄러**에 `SYSTEM` + **최고 권한(HIGHEST)** 으로 등록되어 로그인 시 실행됩니다.
3. 0.1.11에서 보이던 `No module named 'app.util.update_manager_health'` 오류를 고쳤습니다.
4. Setup은 **관리자 허용 후** 설치하세요. (CloneUp.exe만 단독 복사하면 안 됩니다 — `_internal` 폴더가 필요합니다.)

## 설치

- `CloneUp-Setup.exe` 실행 → UAC 허용 → 약관 동의 → 설치  
- 0.1.11 이하 위에 덮어쓰기 가능 (관리자 필요)

## GitHub Release 자산 (필수)

| 파일 | 용도 |
|------|------|
| `CloneUp-Setup.exe` | 사람이 설치 (관리자) |
| **`CloneUp-win64.zip`** | 업데이트 관리자용 |

## 개발자용 변경 요약 (0.1.11 → 0.1.12)

- Inno `PrivilegesRequired=admin` (UAC / Program Files)
- Update manager → `{commonappdata}\CloneUp\UpdateManager`
- **작업 스케줄러** `CloneUpUpdateManager`: `/RU SYSTEM /RL HIGHEST /SC ONLOGON` (+ WakeToRun, 배터리 허용)
- PyInstaller `hiddenimports`에 `app.util.update_manager_health` 등 추가
- 트레이 UM 진단: import 실패 시 soft-fail (「실패」팝업으로 안 올림)

## 참고

- **NT AUTHORITY\SYSTEM** 계정으로 GUI를 돌리지는 않습니다. SYSTEM은 대화형 데스크톱 UI에 적합하지 않습니다. 요청하신 “최고 관리자”는 **관리자 상승 설치(전체 사용자)** 로 구현했습니다.
