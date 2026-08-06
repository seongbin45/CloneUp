# CloneUp 패키징 (P1 + DG3)

## PowerShell 빌드 스크립트(`.ps1`)를 먼저 이해하려면

exe / Setup 을 만들기 **전에**, `scripts\build_exe.ps1` · `build_installer.ps1` 이  
무엇인지·왜 있는지·줄마다 무엇을 하는지는 아래 문서를 보세요.

→ **[POWERSHELL_BUILD_SCRIPTS.md](POWERSHELL_BUILD_SCRIPTS.md)** (초심자용 상세 설명)

한 줄 요약: `.ps1` 은 Windows에서 빌드 명령을 **순서대로 대신 실행해 주는 레시피 파일**입니다.

## 단계

| 단계 | 내용 | 상태 |
|------|------|------|
| **P1** | PyInstaller onedir → `dist/CloneUp/CloneUp.exe` | 완료 |
| **DG3** | Inno Setup → `installer/Output/CloneUp-Setup.exe` | 완료 (빌드 검증) |
| **P2** | 코드서명 / 자동 릴리스 | 대기 |

## 한 번에 빌드 (exe + Setup)

```powershell
cd CloneUp
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

- Inno Setup 6 필요: `winget install --id JRSoftware.InnoSetup -e`
- 결과:
  - `dist\CloneUp\CloneUp.exe`
  - `installer\Output\CloneUp-Setup.exe`

## P1 만 (exe)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

- 아이콘: `assets/icons/CloneUp.ico`
- 포함: `ui/main_window.ui`, `assets/icons/*`
- Git / `.env` **미포함** — 첫 실행 DG1/DG2

## DG3 — 설치 관리자

- 스크립트: `installer/CloneUp.iss`
- 언어: 한국어 + 영어
- **이용약관:** `LicenseFile=installer/license/CloneUp_Terms_ko.txt`  
  (원본 `desin/provision/CloneUp 이용약관.dc.html` → `scripts/export_terms_license.py`)
- **아이콘:** `SetupIconFile` / `UninstallDisplayIcon` / 바로가기 모두 `CloneUp.ico` (16–256)
- 설치 시 Git 강제 설치 없음 (방식 D: 앱 첫 실행 시 안내)

## 동결 경로

`app/paths.py` → `app_root()` 가 개발 트리 / `sys._MEIPASS` 를 구분.

## 검은 콘솔 창이 깜빡일 때

`cloneup.spec` 은 `console=False`(창 전용)입니다.  
그래도 `git.exe` / `clip.exe` / `winget` 자식 프로세스가 잠깐 검은 창을 띄울 수 있어,
`app/util/winproc.py` 의 `CREATE_NO_WINDOW` 로 숨깁니다.

수정 후에는 **Setup을 다시 빌드**해야 설치본에 반영됩니다:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

