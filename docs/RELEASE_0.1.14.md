# CloneUp 0.1.14

**업데이트 관리자 Tier 2** — 끊긴 다운로드를 다음 회차에서도 이어받고, 메인 창이 열려 있어도 zip은 받아 두며, 「한 번 확인」이 작업 스케줄러로 올바르게 피드백됩니다.

## 주요 변경

### 업데이트 관리자 (Tier 2)

| 항목 | 내용 |
|------|------|
| pending 캐시 | `%PROGRAMDATA%\CloneUp\UpdateManager\pending\` (또는 LocalAppData)에 zip·`.part` 보관 → **회차 간 이어받기** |
| UI 열림 | 메인 창이 보이면 **적용만 미룸** (다운로드는 유지) |
| 적용 직전 | 항상 **전체 sha256** 재검증 |
| 상태 파일 | `status/current.json` + `status/runs/{run_id}.json` (동시 실행에도 결과 안 섞임) |
| 한 번 확인 | `schtasks /Run` 우선 → 15초 응답 대기 / 최대 15분 폴링 (진행 중이면 백그라운드 안내) |
| 작업 스케줄러 | `MultipleInstances=Parallel` + 일반 사용자 `/Run` ACL |

### 그 외 (0.1.13 이후 포함)

- Tier 1: 한 번의 다운로드 시도 안에서의 Range/ETag 이어받기, digest 필수(fail-closed)
- 네트워크 타임아웃 재시도 · 자동 이슈 완화
- 업데이트 관리자 확인 UI (트레이·설정)

## 설치

- **`CloneUp-Setup.exe` (0.1.14)** 로 덮어 설치 (관리자 UAC)
- 기존과 동일: Program Files + SYSTEM 작업 `CloneUpUpdateManager`
- 이미 0.1.12+ 이고 자동 업데이트가 켜져 있으면, 창을 닫은 뒤 UM이 zip을 적용할 수 있습니다

## GitHub Release 자산

| 파일 | 용도 |
|------|------|
| `CloneUp-Setup.exe` | 사람이 설치할 때 |
| `CloneUp-win64.zip` | 업데이트 관리자용 (필수) |

## 개발 메모

- 계획: `docs/UPDATE_TIER2_PENDING_PLAN.md` (rev.9)
- 코드: `update_manager/pending.py`, `status_io.py`, `task_migrate.py`, 다이얼로그 폴링
