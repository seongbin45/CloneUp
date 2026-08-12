# CloneUp (클론업)

Windows용 **GitHub 도우미** 데스크톱 앱입니다.  
폴더를 GitHub에 **만들고 올리기** · **받기** · **동기화** 할 수 있습니다.

| 항목 | 내용 |
|------|------|
| 현재 버전 | **0.1.6** (`VERSION`, `app/__init__.py`, `installer/CloneUp.iss`) |
| 실행 (개발) | `.\.venv\Scripts\python.exe main.py` |
| 설치 파일 빌드 | `powershell -File scripts\build_installer.ps1` |
| GitHub | https://github.com/seongbin45/CloneUp |
| 라이선스 | [Apache License 2.0](LICENSE) |
| 초심자 안내 4층 | [docs/UX_GUIDANCE.md](docs/UX_GUIDANCE.md) |
| 패키징 | [docs/PACKAGING.md](docs/PACKAGING.md) |
| Git 없을 때 | [docs/GIT_BOOTSTRAP.md](docs/GIT_BOOTSTRAP.md) |

### 왜 Git을 쓰게 하나요?

클론업은 Git 명령을 버튼으로만 감추는 앱이 아닙니다. 초심자가 Git을 쓰는 **이유**를  
탭과 안내에 남깁니다.

1. **커밋** — 지금 폴더를 “돌아올 수 있는 점”으로 남김  
2. **올리기** — 그 기록을 GitHub에도 맞춰 백업·공유  
3. **받아오기** — 원격의 새 기록을 이 PC에 맞춤  
4. **다시 수정** — 1번으로 돌아감  

「충돌 취소」는 받아오기 중 **겹침을 포기**하는 비상 버튼이고,  
「커밋 내역」은 **지난 점**을 보거나 되돌리는 도구입니다 (서로 다릅니다).  

더 긴 설계 메모: [docs/DIFFERENTIATION.md](docs/DIFFERENTIATION.md) 「왜 Git인가」.

**`.env` 파일은 일반 사용자에게 필요 없습니다.**  
OAuth client id·scope 기본값이 코드에 들어 있고, 로그인 토큰은 OS keyring에 저장됩니다.

로그인: **GitHub에서 만든 키(PAT)만** (기본).  
브라우저 장치 코드(Device Flow)는 공개 client_id 남용 위험으로 **기본 비활성**입니다.  
(개발자만 `CLONEUP_ALLOW_DEVICE_FLOW=1`)  
차별화·보안: [docs/DIFFERENTIATION.md](docs/DIFFERENTIATION.md)

---

## 1. 이 저장소 폴더 지도 (어디를 만지나)

```
CloneUp/
├── README.md                 ← 지금 이 파일 (전체 절차)
├── main.py                   ← 앱 시작점
├── requirements.txt          ← Python 패키지 목록
├── cloneup.spec              ← exe 빌드 설정 (PyInstaller)
├── app/                      ← 프로그램 로직 (기능 수정은 주로 여기)
│   ├── auth/                 ← GitHub 로그인 (Device Flow)
│   ├── git/                  ← clone / publish / sync / 안전 검사
│   ├── github/               ← GitHub API
│   ├── ui/                   ← 화면·버튼·팝업
│   └── util/                 ← 로그 마스킹, 「다음:」 안내
├── ui/                       ← Qt Designer 화면 파일 (.ui)
├── assets/icons/             ← 앱 아이콘
├── scripts/                  ← 빌드·검증·아이콘 생성 스크립트
├── installer/                ← 설치 관리자 (Inno Setup)
├── docs/                     ← 설계·검증·단계 문서
├── desin/                    ← UI 시안 (디자인 참고)
├── dist/                     ← 빌드 결과 (Git에 안 올림)
└── installer/Output/         ← Setup.exe (Git에 안 올림)
```

각 폴더 안에도 **README.md**가 있습니다.  
「이 폴더는 뭐 하는 곳인가 / 언제 만지나 / 다음에 어디를 보라」를 적어 두었습니다.

---

## 2. 처음 한 번: 개발 환경 준비

Windows + PowerShell 기준입니다.

### 2-1. 필요한 것
1. [Git](https://git-scm.com/download/win) (없으면 앱이 안내하기도 함)
2. [Python 3.12+](https://www.python.org/downloads/)
3. (Setup 만들 때) [Inno Setup 6](https://jrsoftware.org/isinfo.php)  
   - 또는: `winget install --id JRSoftware.InnoSetup -e`

### 2-2. 저장소 받기
```powershell
git clone https://github.com/seongbin45/CloneUp.git
cd CloneUp
```

### 2-3. 가상환경 + 패키지
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2-4. 개발 모드로 실행
```powershell
.\.venv\Scripts\python.exe main.py
```

---

## 3. 코드가 바뀌었을 때 — 차근차근 (개발 → 병합)

초심자용 **최소 Git 흐름**입니다.

### 3-1. 작업 전에 최신 코드 받기
```powershell
cd CloneUp
git checkout main
git pull origin main
```

### 3-2. (권장) 기능 하나당 브랜치 하나
```powershell
git checkout -b feature/내가-고칠-내용
```
예: `feature/fix-login-message`, `feature/sync-hint`

### 3-3. 파일 수정
- 화면 문구·버튼 → 보통 `app/ui/` 또는 `ui/main_window.ui`
- clone/push 동작 → `app/git/`
- 로그인 → `app/auth/`
- 자세한 위치는 **각 폴더 README** 참고

### 3-4. 로컬에서 확인
```powershell
.\.venv\Scripts\python.exe main.py
```
탭 전환, 로그인, 해당 기능만 꼭 눌러 봅니다.

### 3-5. 커밋 (변경 기록)
```powershell
git status
git add .
git commit -m "무엇을 왜 바꿨는지 한 줄로"
```
메시지 예: `fix(ui): 로그아웃 완료 안내 문구 수정`

### 3-6. GitHub에 올리기 (push)
```powershell
git push -u origin feature/내가-고칠-내용
```

### 3-7. 병합 (merge) — 두 가지 방법

**방법 A. GitHub 웹 (초심자 추천)**  
1. https://github.com/seongbin45/CloneUp 접속  
2. 방금 push한 브랜치에 대해 **Compare & pull request**  
3. 제목/설명 적고 **Create pull request**  
4. 검토 후 **Merge pull request**  
5. 로컬에서:
```powershell
git checkout main
git pull origin main
```

**방법 B. 로컬에서 main에 바로 합치기** (혼자 작업할 때)
```powershell
git checkout main
git pull origin main
git merge feature/내가-고칠-내용
git push origin main
```

### 3-8. 충돌이 나면
1. `git status`로 빨간 파일 확인  
2. 에디터에서 `<<<<<<<` / `=======` / `>>>>>>>` 구간을 직접 정리  
3. 정리 후:
```powershell
git add .
git commit -m "merge: 충돌 해결"
```
앱 안 **동기화** 탭의 「충돌 취소」는 **작업 중인 git 저장소**용이고,  
**CloneUp 소스 코드 병합 충돌**과는 별개입니다.

---

## 4. 배포 (사용자에게 새 버전 주기)

코드가 `main`에 합쳐진 뒤입니다.

### 4-1. 버전 숫자 올리기
지금 설치 프로그램 버전은 여기에 적혀 있습니다.

- 파일: [`installer/CloneUp.iss`](installer/CloneUp.iss)  
- 줄: `#define MyAppVersion "0.1.6"`  
→ 예: `0.1.6` (버그 수정), `0.2.0` (기능 추가)

(선택) 태그:
```powershell
git tag v0.1.6
git push origin v0.1.6
```

### 4-2. 설치 파일 만들기 (한 번에)

`scripts\build_installer.ps1` 은 **PowerShell 스크립트(`.ps1`)** 입니다.  
(직접 긴 빌드 명령을 치지 않도록 적어 둔 레시피입니다.)

- **무엇을 하는지·줄 단위 설명:** [docs/POWERSHELL_BUILD_SCRIPTS.md](docs/POWERSHELL_BUILD_SCRIPTS.md)  
- **짧은 목록:** [scripts/README.md](scripts/README.md)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

| 부분 | 의미 |
|------|------|
| `powershell` | Windows PowerShell 실행 |
| `-ExecutionPolicy Bypass` | 이 실행에 한해 스크립트 실행 정책 완화 (우리가 만든 스크립트용) |
| `-File scripts\...ps1` | 해당 레시피 파일 실행 |

| 결과물 | 경로 | 설명 |
|--------|------|------|
| 실행 폴더 | `dist\CloneUp\` | 개발·테스트용 (폴더 통째로 필요) |
| **설치 관리자** | `installer\Output\CloneUp-Setup.exe` | **일반 사용자에게 줄 파일** |

### 4-3. 사용자에게 전달
1. **`CloneUp-Setup.exe` 하나만** 전달 (이메일, USB, GitHub Releases 등)  
2. `CloneUp.exe`만 단독 복사하지 말 것 → `_internal` 폴더가 없어져 깨짐  
3. 사용자는 Setup 실행 → 설치 → 실행  
4. PC에 Git이 없으면 앱이 **설치 안내** (방식 D)

### 4-4. GitHub Releases에 올리기 (권장)
1. https://github.com/seongbin45/CloneUp/releases/new  
2. Tag: `v0.1.6`  
3. 제목: `CloneUp 0.1.6`  
4. 설명에 변경 요약 적기  
5. **`CloneUp-Setup.exe` 첨부** 후 Publish  

`dist/` · `installer/Output/` 은 Git 커밋에 넣지 않습니다 (용량·중복).

---

## 5. 「어디부터 어디까지」 한눈에

| 하고 싶은 일 | 어디서부터 | 어디까지 | 어떻게 |
|--------------|------------|----------|--------|
| 버튼 글자만 수정 | `app/ui/` 또는 `ui/main_window.ui` | 커밋·push | 3장 흐름 |
| 로그인 동작 수정 | `app/auth/` | 커밋·push + 로그인 테스트 | Device Flow 확인 |
| clone/push 버그 | `app/git/` | 커밋·push + 해당 탭 테스트 | `docs/FAILURE_CASES.md` 참고 |
| 아이콘 다시 만들기 | `scripts/render_icons.py` | `assets/icons/` 생성 | 스크립트 실행 후 커밋 |
| 사용자용 설치 파일 | `scripts/build_installer.ps1` | `installer/Output/*.exe` | 4장 배포 |
| 시안과 UI 맞추기 | `desin/` 참고 | `app/ui/theme.py` 등 | 디자인 단계 문서 |

---

## 6. 하지 말아야 할 것 (초심자)

| 하지 말 것 | 이유 |
|------------|------|
| `.env`에 토큰 저장 | 토큰은 keyring 사용 |
| `dist/` · `Output/` 을 git add | 용량 크고 재생성 가능 |
| `.venv/` 커밋 | 각자 PC에서 만듦 |
| Setup 없이 `CloneUp.exe`만 배포 | 의존 파일 누락 |
| `main`에 검증 없이 큰 수정 push | 가능하면 브랜치 + PR |

---

## 7. 더 읽기 (폴더 README 목록)

| 폴더 | README |
|------|--------|
| [app/](app/README.md) | 프로그램 본체 구조 |
| [app/auth/](app/auth/README.md) | GitHub 로그인 |
| [app/git/](app/git/README.md) | Git 작업·안전 검사 |
| [app/github/](app/github/README.md) | GitHub REST API |
| [app/ui/](app/ui/README.md) | 화면·워커 |
| [app/util/](app/util/README.md) | 공용 유틸 |
| [ui/](ui/README.md) | `.ui` 화면 파일 |
| [assets/](assets/README.md) | 정적 자원 |
| [assets/icons/](assets/icons/README.md) | 아이콘 |
| [scripts/](scripts/README.md) | 빌드·검증 스크립트 |
| [installer/](installer/README.md) | 설치 관리자 |
| [docs/](docs/README.md) | 설계·검증 문서 색인 |
| [desin/](desin/README.md) | UI 시안 |

---

## 8. 문제 해결 빠른 링크

- Git 없음 → [docs/GIT_BOOTSTRAP.md](docs/GIT_BOOTSTRAP.md)  
- 로그인 실패 → Device 코드는 팝업에서 복사 후 `github.com/login/device`에 붙여넣기  
- 비밀 파일·개인정보 검사 → [docs/PII_CROSS_VERIFY.md](docs/PII_CROSS_VERIFY.md)  
- 실패 케이스 표 → [docs/FAILURE_CASES.md](docs/FAILURE_CASES.md)  

질문·이슈: GitHub Issues에 증상 + 로그 창 내용을 적어 주세요.
