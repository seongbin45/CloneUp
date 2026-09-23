# CloneUp 취약점·기본동작 교차검증 (2026-09-09)

**기준:** 소스 `0.1.13` @ `main` (`552a84f`) · GitHub Release `v0.1.13`  
**이 PC 설치본:** `%LOCALAPPDATA%\Programs\CloneUp` = **0.1.12** (per-user / HKCU Run UM — **admin+SYSTEM 경로 미적용**)  
**빌드/릴리스:** 이번 라운드에서 **실행하지 않음** (규칙: 사용자 승인 필수)

---

## 0. 규칙화 (완료)

| 위치 | 내용 |
|------|------|
| `AGENTS.md` | 빌드·릴리스 전 **항상 사용자에게 물어볼 것** |
| `.grok/rules/ask-before-build-release.md` | 프로젝트 규칙 |
| `~/.grok/rules/ask-before-build-release.md` | 전역 규칙 |

금지(승인 전): `build_exe.ps1` / `build_update_manager.ps1` / `build_installer.ps1` / PyInstaller·Inno / GitHub Release·태그·Setup 업로드.  
허용: 소스 수정, pytest, verify/diagnose, 비배포 점검.

---

## 1. 가장 취약한 부분 (우선순위)

### P0 — 0.1.12+ admin Setup 경로 (SYSTEM Update Manager)

이 PC에는 아직 SYSTEM 작업이 없지만, **0.1.13 Setup 코드에 그대로 있음**. 신규 admin 설치 시 즉시 노출.

| ID | 문제 | 근거 | 실측 |
|----|------|------|------|
| **P0-1** | SYSTEM(Session 0)에서 `EnumWindows`로 메인창을 못 봄 → UI 가드 실패 → 사용 중 `taskkill /IM CloneUp.exe /F` 가능 | `process_win.py` `main_window_visible` · `__main__.py` defer/kill · `CloneUp.iss` `/RU SYSTEM` | 코드 확인. **유저 컨텍스트 UM**에서는 창 열림 시 `deferred_ui` 정상 (아래 Pass E2) |
| **P0-2** | 업데이트 후 트레이 재시작이 SYSTEM의 HKCU / Session 0 기준 | `is_tray_autostart_registered` → `HKCU` · `restart_cloneup_tray` `Popen --tray` | 코드 확인 |
| **P0-3** | UM 로그가 SYSTEM 프로필 LOCALAPPDATA에 쌓이고, 트레이 health는 사용자 LOCALAPPDATA를 봄 → 오진·재시작 폭주 가능 | `logutil.py` · `update_manager_health.py` | 코드 확인 |
| **P0-4** | 미서명 zip + `digest` **옵션** + `ZipFile.extractall` (Zip-Slip 미차단) + SYSTEM이 Program Files 덮어쓰기 → 공급망 피해 반경 확대 | `apply.py` `if digest:` · `extractall` · iss admin | `digest_gate_is_optional=True`, `extractall_unsanitized=True`. v0.1.13 zip에는 digest 있음(완화이나 게이트는 여전히 옵션) |
| **P0-5** | 뮤텍스가 `Local\…` → SYSTEM UM과 사용자 UM이 동시 가능 | `__main__.py` | `Local\CloneUpUpdateManagerMutex` 확인 |

**한 줄 결론:** Program Files에 못 쓰는 문제가 아니라, **SYSTEM이 GUI 앱 업데이터 주체로는 잘못된 보안 주체**다.

### P1 — 이 PC에서도 이미 해당 / 제품 전반

| ID | 문제 | 실측 |
|----|------|------|
| **P1-1** | PAT 클립보드 자동감지 후 **clear 없음** | `CLIPBOARD_CLEAR_NOT_FOUND` (login_dialog / external_pat_guide) |
| **P1-2** | 기본 토큰 저장 = keyring 평문 (마스터 보호 옵트인) | 설계 잔여 (보안 문서와 동일) |
| **P1-3** | push 중 temp cred 동일 사용자 가독 | 설계 잔여; 고아 파일 **0개** (Pass E1) |
| **P1-4** | Path B UIA/OCR 화면·접근성 의존 | 릴리스에서 CDP soft-fail; OCR/UIA는 남음 |
| **P1-5** | `UPDATE_MANAGER.md` 가 여전히 `PrivilegesRequired=lowest` / HKCU L1–L2 중심 | 문서 줄 50·58–59 vs iss admin+schtasks — **문서 드리프트** |
| **P1-6** | 설치본 0.1.12 vs 릴리스 0.1.13 — 이 PC 미업그레이드 | VERSION 불일치 FAIL (의도적: 창 연 동안 defer) |
| **P1-7** | 본체 UPX=`True` (UM은 False) — 일부 AV 오탐 여지 | `cloneup.spec` |

### P2 — 낮음 / 운영

| ID | 내용 |
|----|------|
| P2-1 | ARP DisplayVersion(0.1.11) ≠ VERSION 파일(0.1.12) — 업그레이드 메타 불일치 |
| P2-2 | UM 상시 프로세스 없음(Run 키는 있음) — 로그인/수동 기동 의존 |
| P2-3 | GitHub SSL handshake timeout 간헐 → `no usable release` |
| P2-4 | Setup/UM 코드 서명 없음 (SmartScreen) |
| P2-5 | `temp/` 에 민감 스크린샷·텍스트 — 커밋 금지 위생 |

---

## 2. 순차·교차검증 결과 (여러 패스)

| Pass | 내용 | 결과 |
|------|------|------|
| **A** | `verify_security_crosscheck.py` + `verify_pii_crosscheck.py` | **53/53 · 34/34 OK** |
| **B** | pytest: p0/p1/p2 security, vault, crypto, UM, um_diag, error_popup, next_action, autostart | **90 passed** |
| **C** | packaging/icon/iss/dist/GitHub assets | **12 PASS / 1 FAIL** (install≠source version) · Release에 Setup+zip 둘 다 있음 · ico src==dist |
| **D1** | security+pii **2차** 재실행 | 둘 다 OK |
| **D3** | P0 정적 마커 (Local mutex / optional digest / extractall / HKCU / EnumWindows) | **STATIC_P0_MARKERS_OK** |
| **D4** | keyring 토큰 존재(값 미출력) | present, classic 길이, `ghp_`/`github_pat_` 형태 |
| **D5** | 설치본 실행 + 두 번째 실행 | 프로세스 **1개 유지** (단일 인스턴스 OK) |
| **E1** | orphan `cloneup-git-cred-*` | **0** |
| **E2** | UM `--once` (유저 컨텍스트) | `update available 0.1.12 → 0.1.13` 후 **`main window visible — defer`** ✅ |
| **E3** | API vs local | local 0.1.12 · remote 0.1.13 · digest `sha256:f348…` |
| **E4** | 클립보드 clear | **없음** |
| **E5** | 창 제목 | `클론업 (CloneUp)` (pid 일치) |
| **F** | security **3차** + digest/extractall/mutex 재확인 | OK / optional / unsanitized / Local\ |

### 이 PC 설치·UM 진단 요약

| 항목 | 상태 |
|------|------|
| 설치 경로 | `%LOCALAPPDATA%\Programs\CloneUp` (Program Files 없음) |
| VERSION | 0.1.12 (소스·릴리스 0.1.13보다 뒤) |
| UM exe | LocalAppData\CloneUp\UpdateManager 존재 |
| 자동시작 | **HKCU Run** (schtasks `CloneUpUpdateManager` **없음**) |
| UM 프로세스 | 평소 not running; `--once`는 정상 동작 후 종료 |
| 아이콘 파일 | src ico 해시 == dist == installed |
| Defender MotW | none |

---

## 3. 기본 동작 — 무엇이 되고 / 안 되는지

| 기본 기능 | 판정 | 메모 |
|-----------|------|------|
| 앱 실행 · 창 제목 | **PASS** | `클론업 (CloneUp)` |
| 단일 인스턴스 | **PASS** | 두 번 실행해도 PID 1개 |
| 토큰 저장·로드 | **PASS** | keyring에 classic PAT 존재 |
| 보안/PII/하드닝 회귀 | **PASS** | 자동 검사 3회 연속 OK |
| 패키징 소스(0.1.13 dist/iss) | **PASS** | ico·schtasks·admin·Setup 산출물 |
| 자동 업데이트 → 0.1.13 적용 | **DEFER (정상)** | 창 열려 있어 연기. 창 닫으면 유저 UM은 적용 시도 예상 |
| admin+SYSTEM 업데이트 경로 | **미검증(이 PC)** / **코드상 P0** | 재설치(admin Setup) 후에야 실측 |
| PAT 클립보드 잔존 제거 | **FAIL** | clear 미구현 |
| 문서↔실제 UM 모델 | **FAIL** | lowest/HKCU 잔존 vs admin/schtasks |
| GUI 스모크 #1–#4 (실제 push) | **미실행** | `SMOKE_CHECKLIST.md` 는 수기·실키 필요. 에이전트 대행 무효 |

---

## 4. 권장 다음 조치 (빌드/릴리스 없음 — 승인 후)

1. **P0:** UM을 SYSTEM 상시 폴러로 두지 말 것. 로그인 사용자 작업으로 돌리거나, 파일 교체만 짧은 elevated helper. 당분간 완화: `Global\` mutex · `%PROGRAMDATA%\CloneUp\logs` · 활성 세션 창 검사 · SYSTEM에서 `--tray` 금지.  
2. **P0-4:** digest **필수**(없으면 거부) · zip 멤버 경로 sanitize · (가능하면) 코드 서명.  
3. **P1-1:** PAT ingest 직후 클립보드 clear.  
4. **P1-5:** `UPDATE_MANAGER.md` + diagnose를 ProgramData/schtasks/HKLM 기준으로 고침.  
5. **운영:** 이 PC에서 0.1.13 반영은 창 닫은 뒤 UM 1회, 또는 **승인된** Setup 재설치(admin).  
6. 사용자 수기 `SMOKE_CHECKLIST` #1–#4.

---

## 5. 명시: 빌드·릴리스

이번 세션에서 Setup/exe 재빌드·GitHub Release 재업로드는 **하지 않았습니다.**  
진행하려면 대화에서 예: 「빌드만」 / 「릴리스까지」를 따로 승인해 주세요.
