# CloneUp 0.1.10

0.1.9 위에 **업데이트 관리자 설치 누락 수정**, **트레이 자동 진단 → GitHub 이슈**,  
**초심자용 오류 팝업**을 묶은 패치 릴리스입니다.

## 사용자에게 알려 줄 말 (짧게)

1. 예전에 깔아 둔 PC에서도 **자동 업데이트 관리자 파일은 항상 설치**됩니다. (로그인 시 실행만 선택)
2. 업데이트 관리자가 없거나 오류가 나면, 트레이가 **진단 로그를 GitHub 이슈로 보낼 수 있습니다.** (설정 → 안전에서 끌 수 있음)
3. 오류 창이 **쉬운 한국어 안내 + 다음에 할 일**을 더 분명히 보여 줍니다.
4. Setup을 **관리자 권한으로 실행하지 마세요** — 일반 더블클릭 설치를 권장합니다.

## 설치

- `CloneUp-Setup.exe` 실행 → 약관 동의 → 설치  
- 작업 항목 **「로그인 시 자동 업데이트 관리자 실행」** 기본 선택 (파일 자체는 항상 설치)
- 0.1.9 위에 덮어쓰기 가능

## GitHub Release 자산 (필수)

| 파일 | 용도 |
|------|------|
| `CloneUp-Setup.exe` | 사람이 설치 |
| **`CloneUp-win64.zip`** | 업데이트 관리자용 (없으면 자동 업데이트 안 함) |

자세한 동작: [UPDATE_MANAGER.md](UPDATE_MANAGER.md)

## 개발자용 변경 요약 (0.1.9 → 0.1.10)

### Update manager 설치 신뢰성
- Inno: exe는 Tasks와 무관하게 항상 `%LOCALAPPDATA%\CloneUp\UpdateManager\` 에 복사
- `checkedonce` 제거 (업그레이드 시 미설치 원인)
- UPX 비활성 (백신 오탐 완화)
- `{app}\scripts\diagnose_update_manager.ps1` 동봉

### 트레이 감시 → 진단 보고
- 시작 후·매시간 `CloneUp_update_manager` 상태 확인, 필요 시 1회 재시작
- 이상 시 GitHub 이슈 (`update-manager-diag` / `auto-report`) 또는 `um_diag_pending.md`
- 이슈 본문에 Python 확장 프로브 + diagnose 스크립트 출력

### 오류 팝업 (초심자)
- `format_error_popup_body` · lead 추론 · 영어 restatement · `다음:` 매핑 보강
- WinError → GitHub 재연결 오매핑 수정

## 검증

| 항목 | 상태 |
|------|------|
| `tests/test_um_diag_report.py` | pass |
| `tests/test_error_popup.py` | pass |
| `tests/test_next_action_push_guidance.py` | pass |
