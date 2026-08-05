# Git 부트스트랩 (방식 D)

초심자가 `.env` 없이 앱을 쓸 때, **Git이 없으면 앱이 안내·설치를 돕는다.**

## 단계

| 단계 | 내용 | 상태 |
|------|------|------|
| **DG1** | 기동 시 Git 감지 + 안내 대화상자 (페이지 열기 / winget 시도 / 다시 확인) | 완료 |
| **DG2** | 공식 설치 파일 다운로드 후 실행 (`Git-*-64-bit.exe`) | 완료 |
| **DG3** | 설치 관리자(Inno 등)와 연동 | 초안 (`installer/CloneUp.iss`, 빌드 후 컴파일) |

### DG2 구현

- GitHub `git-for-windows/git` latest release → `Git-*-64-bit.exe` URL
- 임시 폴더에 다운로드 (진행률 표시) → 설치 프로그램 **GUI 실행** (초심자용, silent 기본 아님)
- 설치 후 일반 경로(`Program Files\Git\cmd`)를 PATH에 보강해 `probe_git` 재시도

## 원칙

- 강제 무인 설치만 하지 않음 → 사용자 동의 후 진행  
- 이미 Git 있으면 건드리지 않음  
- 실패 시 git-scm.com 링크 폴백  
- 앱은 Git 없어도 창은 띄움 (상태 줄에 「Git: 없음」)
