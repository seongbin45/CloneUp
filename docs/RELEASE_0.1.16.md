# CloneUp 0.1.16

홈 UI 크롬·스캔·작업표시줄 안전 레이아웃 묶음.

## 주요 변경

### 홈 크롬

- 검색 상자·뒤로가기 등 Windows QSS radius 미적용 구간을 직접 페인팅(알약/5px 칩)
- 테마 카드색 툴팁, 긴 제목·툴팁 호버 마퀴(RTL)
- 스크롤바 호버 시에만 표시 + 필 핸들
- 기본(비최대화) 창이 `availableGeometry` 작업 영역을 채움

### 안정성·스캔

- 홈 스캔 캐시 / 대용량 파일 경로, 로컬 revert·NO_REMOTE 등 이어서 정리
- 이용약관 등 긴 문서는 스크롤·작업표시줄 안전 대화상자

### 설치

- **`CloneUp-Setup.exe` (0.1.16)** 로 덮어 설치 (관리자 UAC)

## GitHub Release 자산 (업로드 시)

| 파일 | 용도 |
|------|------|
| `CloneUp-Setup.exe` | 설치 |
| `CloneUp-win64.zip` | 업데이트 관리자용 |
