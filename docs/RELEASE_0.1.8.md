# CloneUp 0.1.8

0.1.7 위에 **GitHub 연결(Path A/B) 안정화**, **만료일·로그**, **CDP 실험 옵션**을 묶은 패치 릴리스입니다.

**주 경로:** classic PAT(`repo`) + 앱 안 WebView(Path A) 또는 외부 브라우저 안내(Path B).

## 사용자에게 알려 줄 말 (짧게)

1. **앱 안 브라우저(WebView)로 연결**하면 키를 만든 뒤 **자동으로 연결**됩니다. 예전에 키가 만들어졌는데 로그만 「취소」로 보이던 문제를 고쳤습니다.
2. 연결 과정이 메인 **로그**에 `[연결] …` 줄로 남습니다 (키 본문은 가립니다).
3. **외부 브라우저로 연결(Path B)** 안내를 대화형으로 다듬었고, 만료·권한 칩 → Generate 흐름을 돕습니다.
4. (고급) `CLONEUP_CDP=1` + Playwright가 있으면 제어용 Chrome/Edge로 Expiration을 DOM에서 맞출 수 있습니다. 기본 설치본은 이 기능이 꺼져 있습니다. → `docs/CDP_BROWSER_CONTROL.md`
5. 연결 창 크기 경고(고 DPI `setGeometry`)를 줄였습니다.

## 설치

- `CloneUp-Setup.exe` 실행 → 약관 동의 → 설치  
- 0.1.7 위에 덮어쓰기 가능

## 개발자용 변경 요약 (0.1.7 → 0.1.8)

### Path A (WebView)
- ApplicationModal 중 Maximize 플래그 토글로 `exec()`가 Rejected 되던 문제 수정 (「연결 안내 취소」 오탐)
- 키 인식 → 자동 `accept` 방어 로그 (`ConnectGitHubWizard(log=…)`)
- choice `setFixedSize` + DPI 충돌로 인한 `setGeometry` 폭주 완화
- Expiration JS를 `app/auth/pat_form_js.py`로 공유

### Path B (외부 브라우저)
- 대화형 안내 (`browser_dialogue_model` + `external_pat_guide`)
- tasklist PID · 창 순위(PAT 제목 우선) · Invoke/좌표 클릭(커서 복구)
- `path_b_log` → 터미널 + 메인 textLog tee
- 선택: CDP (`browser_cdp`, `path_b_assist_worker`) — UI 스레드 비차단

### 기타
- 만료일 기록·표시, 스크린 맞춤(`clear_size_locks` min+max), DEV_LOGGING_GUIDE 갱신

## 검증 (이 릴리스 기준)

| 항목 | 상태 |
|------|------|
| pytest (연결·CDP·geometry 관련) | 릴리스 전 실행 |
| Path A WebView 키 발급 → accept | 수기 확인 (로그 `[연결] accept`) |
| Path B / CDP | 옵트인·폴백 (기본 off) |
| Setup 빌드 | `scripts\build_installer.ps1` |

## 알려진 한계

- 일부 고 DPI 환경에서 `setGeometry` 경고가 남을 수 있음 (동작과 무관한 Windows/Qt 경고)
- CDP는 Playwright·디버깅 포트 필요, Setup에 Playwright 미포함
- passkey / 2FA는 사용자 확인 필요

## 버전 위치

- `VERSION` · `app/__init__.py` · `installer/CloneUp.iss` · `legal/CloneUp_OpenSourceNotices_ko.txt`
- 문서 색인: `docs/README.md` · 루트 `README.md` (현재 버전 표기)
