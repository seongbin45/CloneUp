# CloneUp 0.1.13

바로가기·제어판 **앱 아이콘 연결 깨짐** 수정.

## 교차검증에서 확인된 원인

| 항목 | 기대 | 실제 (깨진 설치) |
|------|------|------------------|
| 시작메뉴/바탕화면 `.lnk` IconLocation | `{app}\CloneUp.ico,0` 또는 exe | `{app}\CloneUp.ico,0` |
| `{app}\CloneUp.ico` 파일 | 존재 | **없음** (`IconExists=False`) |
| `_internal\assets\icons\CloneUp.ico` | Qt 런타임용 | 있음 (창 아이콘만 동작 가능) |

바로가기가 없는 `.ico`를 가리켜 기본/깨진 아이콘으로 보였습니다.

## 수정

1. `build_exe.ps1`이 `dist\CloneUp\CloneUp.ico`를 **exe 옆에** 복사
2. Inno가 `{app}\CloneUp.ico`를 명시 설치 (`DestName`)
3. 바로가기 `IconFilename` → **`{app}\CloneUp.exe`** (PyInstaller 내장 아이콘, 항상 존재)
4. `UninstallDisplayIcon` → `{app}\CloneUp.exe`

## 설치

- `CloneUp-Setup.exe` (0.1.13)로 덮어 설치 (관리자 UAC)
- 0.1.12와 동일: SYSTEM 작업 스케줄러 + Program Files

## GitHub Release 자산

| 파일 | 용도 |
|------|------|
| `CloneUp-Setup.exe` | 설치 |
| `CloneUp-win64.zip` | 업데이터 |
