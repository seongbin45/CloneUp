# CloneUp 0.1.17

업데이트 관리자 배포 갭 해소 + 숨김 실행 + 진단 스팸 완화.

## 주요 변경

### 자동 업데이트 (배포 갭 해소)

- `CloneUp-win64.zip`에 **`CloneUp\` + `UpdateManager\`** 동시 포함
- apply 시 메인 앱(`{app}`) **및** `%PROGRAMDATA%\CloneUp\UpdateManager\` (exe + hidden.vbs + bat) 교체
- 실행 중 UM은 rename-while-running 후 VBS로 재기동

### 검은 콘솔

- 로그인/스케줄러: `wscript //B …_hidden.vbs`
- `icacls` / `schtasks` / `powershell`에 `CREATE_NO_WINDOW` + `SW_HIDE`

### 진단

- status ACL Users Modify (Errno 13)
- 로그 48시간 신선도, 시그니처에 사용자명, 소스 트레이 UM 미설치 토스트 억제

## GitHub Release 자산

| 파일 | 용도 |
|------|------|
| `CloneUp-Setup.exe` | 설치 (UM+VBS 포함) |
| `CloneUp-win64.zip` | 자동 업데이트 (앱 + UpdateManager) |
