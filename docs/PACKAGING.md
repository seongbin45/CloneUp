# CloneUp 패키징 (P1 + DG3)

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

