# CloneUp 0.1.18

바로가기/트레이 기동 시 검은 콘솔 깜빡임 제거.

## 주요 변경

### 검은 콘솔 (메인 앱)

- 시작 시 `ensure_scan_task`의 `schtasks` 호출에 `CREATE_NO_WINDOW` 적용
- 이미 올바른 VBS 런처로 등록된 경우 삭제·재생성 생략 (불필요한 3–4회 깜빡임 제거)
- 백그라운드 스캔 작업 TR: `wscript //B …\run_scan_hidden.vbs` (`.cmd` 직행 폐지)
- `secret_vault` icacls / browser Path B `tasklist` 폴백도 숨김

### 0.1.17에서 이어짐

- zip에 `CloneUp\` + `UpdateManager\` 포함, apply 시 ProgramData UM 동시 교체
- UM 로그인: hidden VBS, icacls/schtasks 숨김, ACL Users Modify, 진단 스팸 완화

## GitHub Release 자산

| 파일 | 용도 |
|------|------|
| `CloneUp-Setup.exe` | 설치 |
| `CloneUp-win64.zip` | 자동 업데이트 (앱 + UpdateManager) |
