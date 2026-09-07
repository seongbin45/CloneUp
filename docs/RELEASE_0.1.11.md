# CloneUp 0.1.11

0.1.10 위에 **브라우저 로그인 안내 카드 스크롤 제거**를 반영한 패치입니다.

## 사용자에게 알려 줄 말 (짧게)

1. GitHub 연결 시 왼쪽 아래 안내 카드에 **스크롤바가 더 이상 나오지 않습니다.** (내용 높이만큼 카드가 커집니다.)
2. 0.1.10을 쓰 중이면 **이 Setup으로 덮어 설치**해 주세요. (시작 메뉴의 예전 실행 파일에는 스크롤이 남아 있었습니다.)
3. Setup은 **관리자 권한 없이 더블클릭**으로 설치하는 것을 권장합니다.

## 설치

- `CloneUp-Setup.exe` 실행 → 약관 동의 → 설치  
- 0.1.10 위에 덮어쓰기 가능

## GitHub Release 자산 (필수)

| 파일 | 용도 |
|------|------|
| `CloneUp-Setup.exe` | 사람이 설치 |
| **`CloneUp-win64.zip`** | 업데이트 관리자용 |

## 개발자용 변경 요약 (0.1.10 → 0.1.11)

- Path B `ExternalBrowserPatGuide`: `QScrollArea` / sticky CTA 제거
- 스크롤 이전 `body_w` + `sizeHint` 레이아웃 복구
- 「클론업으로 돌아가기」는 DONE 영수증 블록 안으로 복귀

## 검증

| 항목 | 상태 |
|------|------|
| `ExternalBrowserPatGuide` children `QScrollArea` | 0 |
| `tests/test_path_b_assist_worker.py` 등 | pass (0.1.10 기준) |
