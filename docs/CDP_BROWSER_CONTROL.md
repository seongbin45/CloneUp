# Path B: Chrome/Edge CDP 직접 제어 (실험)

**기본 Path B는 UIA/수동입니다.**  
CDP는 **옵트인**이며, Playwright로 사용자 Chromium의 디버깅 포트에 붙어  
classic PAT 폼의 Expiration / Generate를 **DOM**으로 조작합니다.

## 왜 필요한가

- 일반 Chrome에는 DevTools 포트가 없습니다 → “이미 켜 둔 창”에 몰래 붙을 수 없음.
- URL만으로는 Expiration을 넣을 수 없음 (scopes + Note만).
- Path A(내장 WebView)는 이미 JS로 Expiration을 맞춥니다. CDP는 그 방식을 외부 브라우저에 확장합니다.

## 활성화

```powershell
cd C:\Users\seong\Desktop\ProJect\Codyssey_2+1_ProJect\CloneUp
.\.venv\Scripts\python.exe -m pip install -r requirements-playwright.txt
.\.venv\Scripts\python.exe -m playwright install chromium   # connect_over_cdp 용 드라이버

$env:CLONEUP_CDP = "1"
.\.venv\Scripts\python.exe main.py
```

끄기:

```powershell
Remove-Item Env:CLONEUP_CDP -ErrorAction SilentlyContinue
```

## 사용 흐름

1. Path B로 「브라우저로 연결」.
2. 만료·권한 칩 선택 → 키 만들기 장면.
3. `CLONEUP_CDP=1` 이면 「**제어용 브라우저 열기**」 버튼이 보입니다.
4. 버튼 → CloneUp **전용 프로필** (`%LOCALAPPDATA%\CloneUp\cdp-profile`) +  
   `--remote-debugging-port=9222` 로 Chrome/Edge 기동 (기본 프로필을 건드리지 않음).
5. 그 창에서 GitHub 로그인 후 tokens/new 가 열리면, CloneUp이 CDP로 Expiration을 맞춥니다.
6. CDP 실패 시 기존 UIA/수동으로 폴백.

이미 디버깅 포트로 켠 브라우저가 있으면 기동 없이 연결만 합니다.

```powershell
# 수동 기동 예 (전용 프로필 권장 — localhost만 바인딩)
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --remote-debugging-address=127.0.0.1 `
  --user-data-dir="$env:LOCALAPPDATA\CloneUp\cdp-profile" `
  --no-first-run
```

확인: 브라우저에서 `http://127.0.0.1:9222/json/version`

## 보안

- 포트는 **127.0.0.1** 만 사용합니다.
- CDP 세션에서 `browser.close()`를 호출하지 않습니다 (사용자 브라우저 종료 방지).
- 기본 User Data를 강제 종료·덮어쓰지 않습니다.
- 로그는 `path_b_log` + 토큰 마스크 (`docs/DEV_LOGGING_GUIDE.md`).

## 한계

- passkey / 2FA / CAPTCHA 는 자동화하지 않습니다.
- Playwright 미설치·포트 없음·탭을 못 찾으면 UIA/수동 폴백.
- 배포 exe에 Playwright를 기본 포함하지 않는 것을 권장합니다.

## 코드

| 모듈 | 역할 |
|------|------|
| `app/util/browser_cdp.py` | probe / launch / set Expiration / Generate |
| `app/auth/pat_form_js.py` | Path A·CDP 공유 DOM 스크립트 |
| `app/ui/path_b_assist_worker.py` | CDP·포트 대기를 **백그라운드 스레드**에서 실행 (안내창 멈춤 방지) |
| `app/ui/external_pat_guide.py` | CDP 우선 → UIA 폴백, 기동 버튼, 워커 결과 반영 |
