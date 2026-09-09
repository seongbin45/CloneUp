# CloneUp 0.1.15

Path B 만료일(Custom) 감지와 OCR 검은 창 수정 + 0.1.14 Tier 2 업데이트 관리자.

## 주요 변경

### Path B — Custom 만료일

- Expiration이 **Custom…** 일 때 Select date / `Expiration` Edit Value의 **YYYY-MM-DD** 읽기
- 감지 실패 시 「읽는 중」에 고정되지 않도록 안내 개선
- Chrome a11y: Select date Text는 비고, 날짜는 `Expiration` Edit에 있는 경우 대응

### Path B — OCR 검은 창

- GUI(`pythonw` / 설치본)에서 Tesseract 호출 시 Windows Terminal이 깜빡이던 문제 수정 (`CREATE_NO_WINDOW`)

### 업데이트 관리자 (0.1.14부터)

- Tier 2 pending 이어받기, UI 열림 시 적용만 미룸, schtasks Parallel + 상태 폴링

## 설치

- **`CloneUp-Setup.exe` (0.1.15)** 로 덮어 설치 (관리자 UAC)
- 자동 업데이트: 창을 닫으면 UM이 zip 적용 가능

## GitHub Release 자산

| 파일 | 용도 |
|------|------|
| `CloneUp-Setup.exe` | 설치 |
| `CloneUp-win64.zip` | 업데이트 관리자용 (필수) |
