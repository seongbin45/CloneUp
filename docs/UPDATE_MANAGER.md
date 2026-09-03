# CloneUp Update Manager (독립 자동 업데이트)

`CloneUp_update_manager.exe`는 **CloneUp GUI와 완전히 분리된** 백그라운드 프로그램입니다.

## 왜 Setup.exe를 실행하지 않나요?

GitHub 릴리즈의 **설치 관리자(`CloneUp-Setup.exe`)를 그대로 실행하면**  
Inno Setup **GUI 마법사**가 뜰 수 있습니다. 자동 업데이트는 사용자에게 묻지 않아야 하므로,

1. **먼저** CloneUp이 설치된 폴더를 찾고  
2. 릴리즈의 **`CloneUp-win64.zip`(onedir)** 을 받은 뒤  
3. 설치 관리자의 `[Files]`와 같이 **파일 복사로 `{app}`을 교체**합니다.

`/VERYSILENT`로 Setup을 돌리는 방식은 쓰지 않습니다.

## 동작

| 항목 | 내용 |
|------|------|
| 주기 | 약 **10분**마다 GitHub `releases/latest` 확인 |
| 자산 | `CloneUp-win64.zip` (또는 `CloneUp.zip`) — **Setup.exe 제외** |
| 가드 | 메인 창 제목 `클론업 (CloneUp)`이 **보이면** 이번 회차 스킵 |
| 적용 | zip 다운로드·검증 **먼저** → (메인 창 재확인) → CloneUp.exe 종료 → 파일 교체 (`unins*` 보존) |
| 이후 | HKCU `CloneUpTray`가 있으면 `CloneUp.exe --tray` 재실행 |
| UI | 없음 (로그만) |

## 설치 경로 찾는 순서

1. 환경 변수 `CLONEUP_INSTALL_DIR` (테스트·수동 지정)
2. 제어판/앱 제거 레지스트리 (Inno AppId · DisplayName `CloneUp`)
3. 기본 후보: `%LOCALAPPDATA%\Programs\CloneUp` 등 (`CloneUp.exe` 존재 확인)

업데이트 관리자 자신은  
`%LOCALAPPDATA%\CloneUp\UpdateManager\CloneUp_update_manager.exe`  
에 두어 앱 onedir과 파일이 겹치지 않습니다.

## 설치 / 자동시작

| 항목 | 동작 |
|------|------|
| **파일** | Setup이 **항상** `%LOCALAPPDATA%\CloneUp\UpdateManager\CloneUp_update_manager.exe` 를 설치합니다. (작업 항목과 무관) |
| **자동시작** | Setup 작업 **「로그인 시 자동 업데이트 관리자 실행」** (기본 선택) → HKCU Run `CloneUpUpdateManager` |
| 트레이 | CloneUp 트레이 자동시작(`CloneUpTray`)과는 **별개** |

### 일부 PC에 안 깔리던 원인 (수정됨)

1. **`checkedonce` + Tasks로 파일 게이트** — 이전 버전이 있으면 업그레이드 시 작업이 기본 해제되어 **exe 자체가 복사되지 않음**
2. **UPX 패킹** — 일부 Defender/백신에서 onefile 업데이터가 격리되어 “설치 안 됨”처럼 보임
3. **관리자 권한으로 Setup 실행** — `{localappdata}` / HKCU Run 이 **그 관리자 프로필**에만 기록됨 (일반 사용자 세션에는 없음). Setup은 `PrivilegesRequired=lowest` 이므로 **더블클릭 설치**를 권장

## 로그

`%LOCALAPPDATA%\CloneUp\logs\update_manager.log`

## 끄기

- Windows **설정 → 앱 → 시작** 에서 끄기, 또는  
- `HKCU\...\Run` 의 `CloneUpUpdateManager` 삭제, 또는  
- Setup 재설치 시 **「로그인 시 자동 업데이트 관리자 실행」** 만 해제 (exe 파일은 남음)

## 릴리즈 체크리스트

```powershell
powershell -File scripts\build_exe.ps1
powershell -File scripts\build_update_manager.ps1 -ZipApp
```

GitHub Release에 **반드시** 첨부:

- `CloneUp-Setup.exe` — 사람이 설치할 때
- **`dist\CloneUp-win64.zip`** — 업데이트 관리자용 (없으면 자동 업데이트 안 함)

## 개발 실행

```powershell
.\.venv\Scripts\python.exe -m update_manager --once
.\.venv\Scripts\python.exe -m update_manager --interval 600
```
