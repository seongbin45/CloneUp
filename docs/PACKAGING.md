# CloneUp 패키징 (P1 + DG3)

## 단계

| 단계 | 내용 | 상태 |
|------|------|------|
| **P1** | PyInstaller onedir → `dist/CloneUp/CloneUp.exe` | 완료 (빌드 검증) |
| **DG3** | Inno Setup 스크립트 `installer/CloneUp.iss` | 초안 (컴파일은 Inno 설치 후) |
| **P2** | 코드서명 / 자동 릴리스 | 대기 |

## P1 — exe 빌드

```powershell
cd CloneUp
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

결과: `dist\CloneUp\CloneUp.exe` (+ 의존 DLL 폴더)

- 아이콘: `assets/icons/CloneUp.ico`
- 포함 데이터: `ui/main_window.ui`, `assets/icons/*`
- 콘솔 없음 (windowed)
- Git / `.env` **미포함** — 기동 시 DG1/DG2로 Git 안내

## DG3 — 설치 관리자

1. P1 빌드 완료
2. [Inno Setup 6](https://jrsoftware.org/isinfo.php) 설치
3. `installer/CloneUp.iss` 컴파일
4. 산출물: `installer/Output/CloneUp-Setup.exe`

설치 시 Git을 강제로 넣지 않음. **첫 실행** 때 앱이 Git 없으면 설치를 돕는다 (방식 D).

## 동결 경로

`app/paths.py` → `app_root()` 가 개발 트리 / `sys._MEIPASS` 를 구분.
