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
| 가드 | 메인 창이 **보이면** zip은 pending에 두고 **적용만 미룸** (Tier 2) |
| 적용 | pending zip → apply-gate 전체 sha256 → 추출 → CloneUp.exe 종료 → 파일 교체 (`unins*` 보존) |
| 이후 | HKCU `CloneUpTray`가 있으면 `CloneUp.exe --tray` 재실행 |
| UI | 트레이/설정 **업데이트 관리자 확인** + 상태 폴링 (`status/current.json`) |
| pending | `%PROGRAMDATA%\CloneUp\UpdateManager\pending\` (machine) / LocalAppData (user) |

## 설치 경로 찾는 순서

1. 환경 변수 `CLONEUP_INSTALL_DIR` (테스트·수동 지정)
2. 제어판/앱 제거 레지스트리 (Inno AppId · DisplayName `CloneUp`)
3. 기본 후보: `%LOCALAPPDATA%\Programs\CloneUp` 등 (`CloneUp.exe` 존재 확인)

업데이트 관리자 자신은  
`%PROGRAMDATA%\CloneUp\UpdateManager\CloneUp_update_manager.exe`  
(관리자 설치 / 전체 사용자)에 두어 앱 onedir과 파일이 겹치지 않습니다.  
예전(0.1.11 이하) 설치는 `%LOCALAPPDATA%\CloneUp\UpdateManager\` 일 수 있습니다.

## 설치 / 자동시작

| 항목 | 동작 |
|------|------|
| **파일** | Setup이 **항상** `%PROGRAMDATA%\CloneUp\UpdateManager\CloneUp_update_manager.exe` 를 설치합니다. (작업 항목과 무관, **관리자 Setup**) |
| **자동시작** | Setup 작업 **「로그인 시 자동 업데이트 관리자 실행」** (기본 선택) → **작업 스케줄러** `CloneUpUpdateManager` (`SYSTEM` + `HIGHEST` + ONLOGON + **Parallel**) |
| **수동 확인** | 트레이 「업데이트 한 번 확인」→ `schtasks /Run` 우선 (Parallel 원샷) → `status/runs/{run_id}.json` 폴링 (15초 시작 대기 / 최대 15분) |
| 트레이 | CloneUp 트레이 자동시작(`CloneUpTray`)과는 **별개** |

### 일부 PC에 안 깔리던 원인 (수정됨)

1. **`checkedonce` + Tasks로 파일 게이트** — 이전 버전이 있으면 업그레이드 시 작업이 기본 해제되어 **exe 자체가 복사되지 않음**
2. **UPX 패킹** — 일부 Defender/백신에서 onefile 업데이터가 격리되어 “설치 안 됨”처럼 보임
3. **관리자 전용 Setup** — `PrivilegesRequired=admin`. UM은 ProgramData + schtasks(SYSTEM). 예전 lowest/HKCU 설치는 LocalAppData에 남을 수 있음.

### 특정 PC 심층 조사 (증상 분리)

“업데이터가 없다”는 말이 실제로는 서로 다른 층일 수 있습니다.

| 층 | 의미 | 확인 |
|----|------|------|
| L1 파일 | `CloneUp_update_manager.exe` 없음 | `%PROGRAMDATA%\CloneUp\UpdateManager\` (구버전은 LocalAppData) |
| L2 자동시작 | 파일은 있는데 로그인 시 안 뜸 | 작업 스케줄러 `CloneUpUpdateManager` (구버전 HKCU Run) |
| L3 실행 | 작업은 있는데 프로세스가 안 뜸 / 로그 없음 | 작업 관리자 + `logs\update_manager.log` |
| L4 탐지 | 프로세스는 도는데 앱을 못 찾음 | 로그의 `install dir not found` / `no_install` |
| L5 네트워크 | 앱은 찾지만 릴리즈 zip 없음 | 로그의 `no_release` / `no zip asset` |

영향 PC에서 **CloneUp을 쓰는 그 사용자 세션**으로:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\diagnose_update_manager.ps1 -OutFile "$env:USERPROFILE\Desktop\cloneup-um-diag.txt"
```

스크립트가 L1–L5와 “다른 프로필에만 설치됨 / AV 격리 / 작업 항목 해제” 패턴을 분류합니다.

## 트레이 자동 감시 → GitHub 이슈

CloneUp 트레이(`--tray`)가 주기적으로 `CloneUp_update_manager` 상태를 봅니다.

| 항목 | 내용 |
|------|------|
| 시점 | 시작 ~2분 후 1회, 이후 **1시간**마다 (백그라운드·조용히, 터미널 창 없음) |
| 관리 UI | 트레이 **업데이트 관리자 확인** 또는 설정 → 안전 → 같은 이름 버튼 → 상태·시작·1회 확인·로그 |
| 이상 조건 | exe 없음 / 프로세스 없음 / 로그에 apply·install-dir·GitHub 실패 등 |
| 복구 시도 | exe는 있는데 프로세스가 없으면 **한 번 자동 재시작** 후 재확인 |
| 전송 | 연결 키가 있으면 `seongbin45/CloneUp`에 `[auto] update-manager unhealthy…` 이슈 생성 |
| 폴백 | 키 없음·API 실패 시 `%LOCALAPPDATA%\CloneUp\logs\um_diag_pending.md` 저장 + 트레이 알림 |
| 중복 방지 | 같은 문제 서명(`signature`)은 **24시간**에 한 번 |
| 끄기 | 설정 → 안전 → **업데이트 관리자 문제 시 진단 보내기** |
| 본문 | Python 확장 프로브 + `{app}\scripts\diagnose_update_manager.ps1` 출력이 이슈에 첨부 |

이슈 라벨: `update-manager-diag`, `auto-report`.

## 로그

`%LOCALAPPDATA%\CloneUp\logs\update_manager.log`

## 끄기

- 작업 스케줄러에서 `CloneUpUpdateManager` 사용 안 함 / 삭제, 또는  
- Setup 재설치 시 **「로그인 시 자동 업데이트 관리자 실행」** 만 해제 (exe 파일은 남음), 또는  
- (구버전) `HKCU\...\Run` 의 `CloneUpUpdateManager` 삭제

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
