# Git 부트스트랩 (방식 D)

초심자가 `.env` 없이 앱을 쓸 때, **Git이 없으면 앱이 안내·설치를 돕는다.**

## 단계

| 단계 | 내용 | 상태 |
|------|------|------|
| **DG1** | 기동 시 Git 감지 + **전체 창 오버레이** 안내 (큰 버튼 위주) | 완료 |
| **DG2** | 공식 설치 파일 다운로드 후 실행 (`Git-*-64-bit.exe`) | 완료 |
| **DG3** | 설치 관리자(Inno) → `CloneUp-Setup.exe` | 완료 (`scripts/build_installer.ps1`) |

### DG1 UI (초심자)

한 화면에 선택지를 많이 나열하지 않습니다.

1. **Git 설치하기** (권장) — 공식 설치 파일 받기·실행  
2. **이미 설치했어요** — 다시 찾기  
3. **나중에** — 앱은 열리지만 올리기/받기/동기화 불가  
4. **다른 방법** (접어 둠) — 브라우저 페이지 / winget  

구현: `app/ui/git_setup.py` (`GitSetupOverlay`)

### 개발자: 안내 화면 강제 보기

이 PC에 Git이 있어도 오버레이를 보려면 (PATH 제거만으로는 부족 — 앱이 설치 폴더를 자동 탐색함):

```powershell
$env:CLONEUP_FORCE_NO_GIT = "1"
.\.venv\Scripts\python.exe main.py
```

- 「이미 설치했어요」를 누르면 실제 Git을 찾아 **준비 완료**로 넘어갑니다.
- 테스트 후 환경 변수를 끄거나 터미널을 닫으면 됩니다.

### DG2 구현

- GitHub `git-for-windows/git` latest release → `Git-*-64-bit.exe` URL
- 임시 폴더에 다운로드 (진행률 표시) → 설치 프로그램 **GUI 실행** (초심자용, silent 기본 아님)
- 설치 후 일반 경로(`Program Files\Git\cmd`)를 PATH에 보강해 `probe_git` 재시도

## 원칙

- 강제 무인 설치만 하지 않음 → 사용자 동의 후 진행  
- 이미 Git 있으면 건드리지 않음  
- 실패 시 git-scm.com 링크 폴백  
- 앱은 Git 없어도 창은 띄움 (상태 줄에 「Git: 없음」)
