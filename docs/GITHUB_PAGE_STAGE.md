# GitHub 페이지 단계 판별

연결(PAT) 흐름에서 **지금 어떤 GitHub 화면인지**를 URL·title·HTML 시그니처로 구분합니다.

구현: `app/auth/github_page_stage.py`  
근거 자료: `temp/` HTML·스크린샷, `temp/github.com.zip` (저장 시 `settings/tokens` **목록** 페이지)

## 이 모듈이 하는 일 / 안 하는 일

| 함 | 안 함 |
|----|--------|
| `PageSnapshot(url, title, html)` → `GitHubPageStage` | 실제 브라우저 창 읽기 |
| 순수 함수 · 네트워크 없음 | 트래픽 MITM / CDP |
| 테스트 fixture로 회귀 | 연결 마법사 자동 스텝 연결(다음 단계) |

## 단계

| Stage | 의미 | 대표 신호 |
|-------|------|-----------|
| `LOGIN` | 로그인 | `/login`, title `Sign in to GitHub`, `#login_field` |
| `AUTH_2FA` | 앱/이메일 OTP | `/sessions/two-factor`, `Two-factor authentication` |
| `AUTH_PASSKEY_OS` | Windows 패스키 창 | **HTML/URL로 감지 불가** (문서용 라벨) |
| `TOKEN_CLASSIC_NEW` | classic 키 만들기 | `/settings/tokens/new`, `new_oauth_access`, `Generate token` |
| `TOKEN_FINE_NEW` | 세분 키 만들기 | `/settings/personal-access-tokens/new` |
| `TOKEN_ISSUED` | 방금 발급 · 지금 복사 | “Make sure to copy…” + `ghp_`/`github_pat_` |
| `TOKEN_CLASSIC_LIST` | classic 키 **목록** | `/settings/tokens`, title `Personal Access Tokens (Classic)` — zip 근거 |
| `UNKNOWN` | 그 외 | |

**중요:** zip의 `github.com/settings/tokens.html`은 발급 직후 화면이 아니라 **목록**입니다.  
발급 완료는 스크린샷의 copy-now 배너 + 토큰 문자열로만 `TOKEN_ISSUED`입니다.

## 연결 UI와의 연동

- `app/ui/connect_webview.py` + `ConnectGitHubWizard` (WebEngine 있을 때)
- `urlChanged` / `titleChanged` / `toHtml` → `PageSnapshot` → 안내 문구·체크리스트 갱신
- WebEngine 없으면 외부 브라우저 + 클립보드 폴백
- OS 패스키 창은 HTML로 안 보임 → 안내로 비밀번호·OTP 유도

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_github_page_stage.py -q
```
