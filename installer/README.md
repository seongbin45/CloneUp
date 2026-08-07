# `installer/` — Windows 설치 관리자 (Inno Setup)

## 파일

| 경로 | 역할 |
|------|------|
| `CloneUp.iss` | Inno Setup 스크립트 (버전·아이콘·약관·설치 경로) |
| `license/CloneUp_Terms_ko.txt` | **설치 동의 약관** (UTF-8 BOM) |
| `Output/CloneUp-Setup.exe` | **빌드 결과** (gitignore, 재생성) |

## 이용약관

- 시안 원본: [`desin/provision/CloneUp 이용약관.dc.html`](../desin/provision/CloneUp%20이용약관.dc.html)
- 추출: `.\.venv\Scripts\python.exe scripts\export_terms_license.py`
- Inno Setup `LicenseFile` → 설치 마법사 **약관 동의** 페이지
- 설치 후에도 `{app}\legal\CloneUp_Terms_ko.txt` 로 남음

약관 HTML을 고친 뒤에는 추출 스크립트를 다시 실행한 다음 Setup을 빌드하세요.  
(`build_installer.ps1` 이 추출을 자동으로 호출합니다.)

## 아이콘 (제어판 · 바로가기)

| 용도 | 설정 |
|------|------|
| Setup 마법사 | `SetupIconFile=..\assets\icons\CloneUp.ico` |
| 제어판(앱 제거) | `UninstallDisplayIcon={app}\CloneUp.ico` |
| 시작 메뉴 / 바탕화면 | `IconFilename={app}\CloneUp.ico` (16–256 멀티 사이즈) |
| 설치 폴더 | `{app}\CloneUp.ico` + `{app}\icons\icon-*.png` |

`CloneUp.ico` 에는 16·24·32·48·64·128·256 이 들어 있습니다.  
재생성: `.\.venv\Scripts\python.exe scripts\generate_icons.py`

## 초심자: Setup 만들기 (처음부터 끝까지)

### 전제
1. 이미 `dist\CloneUp\CloneUp.exe` 가 있거나, 아래 통합 스크립트가 만들어 줌  
2. Inno Setup 6 설치  
   ```powershell
   winget install --id JRSoftware.InnoSetup -e
   ```

### 권장: 한 방에
저장소 루트에서:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

이 명령이 부르는 **`.ps1` 스크립트가 무엇인지** (exe 빌드 → Setup 컴파일 순서)는  
초심자용 설명 문서: [docs/POWERSHELL_BUILD_SCRIPTS.md](../docs/POWERSHELL_BUILD_SCRIPTS.md)

### 결과물
```
installer\Output\CloneUp-Setup.exe
```

이 파일 **하나만** 사용자에게 전달하면 설치할 수 있습니다.

### 버전 숫자 바꾸기
`CloneUp.iss` 파일 위쪽:

```iss
#define MyAppVersion "0.1.5"
```

올린 뒤 다시 `build_installer.ps1` 실행.

## Git에 올리지 않는 것

- `Output/` 폴더 전체 (Setup.exe 포함)  
→ 배포는 GitHub **Releases** 첨부 권장 (루트 README 4-4).

## Git 설치와의 관계

Setup은 **CloneUp만** 설치합니다.  
PC에 Git이 없으면 앱 **첫 실행** 때 안내합니다 ([docs/GIT_BOOTSTRAP.md](../docs/GIT_BOOTSTRAP.md)).
