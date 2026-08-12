# 참고 자료 모음 (REFERENCES)

작성일: 2026-08-08.
목적: **이 저장소에서 계속 개발할 때** 바로 찾아볼 수 있는 외부 문서·유사 제품·내부 상태를 한 곳에 모은다.
`docs/`의 다른 문서가 "왜 이렇게 만들었는지"를 다룬다면, 이 문서는 **"어디를 찾아보면 되는지"** 를 다룬다.

---

## 1. 외부 기술 문서 (라이브러리·API별)

코드가 실제로 쓰는 항목만 추렸다 (`requirements.txt` / `requirements-dev.txt` / `requirements-playwright.txt` 기준).

### GUI — PySide6 (Qt for Python)

| 용도 | 링크 |
|------|------|
| 공식 문서 (모듈 API 전체) | https://doc.qt.io/qtforpython-6/ |
| 예제 모음 | https://doc.qt.io/qtforpython-6/examples/index.html |
| `QThread` / 백그라운드 작업 패턴 | https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html |
| PyPI (버전 이력) | https://pypi.org/project/PySide6/ |

- `app/ui/` 워커(`tab_workers.py`, `publish_worker.py`)는 `QThread` 기반 — 시그널/슬롯 문서를 자주 참고하게 됨.
- `requirements.txt` 는 `PySide6>=6.6.0` 고정. 메이저 업그레이드 전엔 release notes 확인: https://doc.qt.io/qtforpython-6/release_notes/pyside6_release_notes.html

### GitHub REST API

| 용도 | 링크 |
|------|------|
| REST API 전체 색인 | https://docs.github.com/en/rest |
| 저장소 (`repos`) — `create_repo`/`get_repo_default_branch` 관련 | https://docs.github.com/en/rest/repos/repos |
| 커밋 (`commits`) — `list_repo_commits`/`list_remote_changed_files` 관련 | https://docs.github.com/en/rest/commits/commits |
| API 버전 헤더 (`X-GitHub-Api-Version`) | https://docs.github.com/en/rest/about-the-rest-api/api-versions |
| Rate limit | https://docs.github.com/en/rest/rate-limit |

- `app/github/api_client.py` 는 `X-GitHub-Api-Version: 2022-11-28` 을 고정 헤더로 보냄 — GitHub가 새 버전을 내면 이 문서에서 마이그레이션 노트를 확인.

### GitHub 인증 — OAuth Device Flow / PAT

| 용도 | 링크 |
|------|------|
| Device Flow 상세 (요청/폴링/에러 코드) | https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow |
| Personal Access Token (classic vs fine-grained) | https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens |
| OAuth App 등록/관리 | https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app |

- `app/auth/device_flow.py`의 `authorization_pending` / `slow_down` / `expired_token` / `access_denied` / `incorrect_device_code` 에러 처리는 이 문서의 에러 코드 표와 1:1로 대응한다. 새 에러 코드가 추가되면 이 문서부터 확인.
- Fine-grained PAT는 `X-OAuth-Scopes` 헤더를 비워서 보낼 수 있음 → `app/auth/token_store.py`의 `SCOPE_UNKNOWN` 처리 근거.

### 그 외 Python 라이브러리

| 라이브러리 | 용도 (이 저장소) | 링크 |
|------------|------------------|------|
| `requests` | GitHub API·Device Flow HTTP 호출 | https://requests.readthedocs.io/ |
| `keyring` | OS 자격 증명 저장소에 토큰 저장 (`app/auth/token_store.py`) | https://github.com/jaraco/keyring |
| `python-dotenv` | 개발용 `.env` 로드 | https://pypi.org/project/python-dotenv/ |
| `pytest` | 테스트 러너 (`tests/`) | https://docs.pytest.org/ |
| `playwright` (실험적, 기본 비활성) | Device Flow 자동 입력 실험 (`app/auth/playwright_device.py`) | https://playwright.dev/python/ |

### 패키징 — PyInstaller / Inno Setup

| 용도 | 링크 |
|------|------|
| PyInstaller 공식 매뉴얼 | https://pyinstaller.org/en/stable/ |
| PyInstaller — 숨은 임포트/데이터 파일 (`cloneup.spec` 수정 시) | https://pyinstaller.org/en/stable/spec-files.html |
| Inno Setup 공식 사이트 | https://jrsoftware.org/isinfo.php |
| Inno Setup 스크립트 문법 (`installer/CloneUp.iss` 수정 시) | https://jrsoftware.org/ishelp/ |

- 이 저장소는 이미 `docs/PACKAGING.md`, `docs/POWERSHELL_BUILD_SCRIPTS.md`에 초심자용 요약이 있음 — 위 링크는 **공식 원문이 필요할 때**만.

---

## 2. 내부 문서 상태 (docs/ 검토 메모)

`docs/README.md` 색인은 최신이고 문서 대부분이 2026-08 기준으로 관리되고 있다. 검토 중 눈에 띈 점:

| 관찰 | 내용 |
|------|------|
| 버전 표기 편차 | `CLONEUP_SECURITY_REVIEW.md`는 **v0.1.2** 기준 스냅샷(외부 리뷰), 이후 `SECURITY_CROSS_VERIFY.md`(2026-08-07 보안 재검증)가 최신을 맡음. 현재 버전은 **0.1.6** — 보안 문서를 볼 땐 `SECURITY_CROSS_VERIFY.md`를 최신으로 우선 참고하고, `CLONEUP_SECURITY_REVIEW.md`는 "최초 외부 리뷰 원문(0.1.2 시점)"으로 읽을 것. |
| RELEASE 노트 | `RELEASE_0.1.1.md` ~ `RELEASE_0.1.6.md` 순서대로 존재, `VERSION` 파일(0.1.6) · `installer/CloneUp.iss`(`MyAppVersion "0.1.6"`) · `app/__init__.py` 와 일치. 다음 배포 시 `RELEASE_0.1.7.md` 추가 + 위 3곳 버전 동시 갱신 패턴 유지. |
| 구조 | 폴더별 README.md(`app/*/README.md`, `ui/`, `assets/`, `scripts/`, `installer/`, `desin/`)가 이미 일관되게 존재 — 새 폴더를 추가할 때도 이 패턴(무엇 하는 곳/언제 만지나/다음 참고)을 따르면 됨. |

별도의 대규모 재정리는 필요 없어 보인다 (중복·죽은 링크 없음).

---

## 3. 유사 제품 리서치 (`docs/DIFFERENTIATION.md` 보강용)

`docs/DIFFERENTIATION.md`에 이미 GitHub Desktop / Bitbucket / Sourcetree 비교가 있다. 추가로 확인한 2026년 기준 시장 동향:

| 제품 | 강점 | CloneUp과의 관계 |
|------|------|-------------------|
| **GitHub Desktop** | GitHub 전용 단순함, 초보자에게 추천되는 기본값 | `docs/DIFFERENTIATION.md`의 핵심 비교 대상. CloneUp은 "Desktop이 부담스러운" 더 좁은 사용자층을 노림 |
| **GitKraken** | 커밋 그래프 시각화가 강력, 2026년 리뷰에서도 초보자용으로 자주 추천됨 | 단, **비공개 저장소는 유료** — CloneUp의 "무료·PAT 기반" 포지션과 대비할 수 있는 새 비교 축 |
| **Sourcetree** | 완전 무료, Atlassian/Bitbucket 연계, Git-flow·서브모듈 지원 | 기존 문서대로 "팀·고급 Git" 쪽 — CloneUp의 "첫 3동작" 포지션과 여전히 반대 방향 |

제안: `docs/DIFFERENTIATION.md` 비교 표에 **GitKraken 행 추가**를 고려할 만하다 (무료 티어가 비공개 저장소를 지원하지 않는다는 점은 "PAT만으로 비공개 저장소까지 무료로 되는" CloneUp의 V1 신뢰 가치와 바로 대비됨).

Sources:
- [Best Free Git GUI Clients in 2026 — GitKraken, Sourcetree, GitHub Desktop & More](https://tools.fun/resources/best-free-git-gui-clients)
- [GitKraken vs Sourcetree 2026: Which Git GUI Is Right for You?](https://thesoftwarescout.com/gitkraken-vs-sourcetree-2026-which-git-gui-is-right-for-you/)
- [Sourcetree vs GitKraken | Which is the best Git GUI?](https://www.gitkraken.com/compare/gitkraken-vs-sourcetree)

---

## 4. 디자인 시안 ↔ 구현 상태 (`desin/`)

`docs/DESIGN_PHASES.md`에 이미 단계별로 추적되고 있다. 요약:

| 영역 | 시안 위치 | 구현 위치 | 남은 것 |
|------|-----------|-----------|---------|
| 라이트/다크 팔레트 | `desin/CloneUp Window.dc.html`, `desin/dark/` | `app/ui/theme.py` | D5 (수동 라이트/다크/시스템 설정) — 선택, 대기 |
| 아이콘 | `desin/icon/` | `assets/icons/` (`scripts/import_design_pngs.py`로 생성) | I4 (About 등 UI 내 마크), I5 (exe 패키징 아이콘 연동) — 대기 |
| 이용약관 | `desin/provision/` | `legal/CloneUp_Terms_ko.txt` (`scripts/export_terms_license.py`로 추출) | — |

새로 디자인 작업을 시작할 때는 `docs/DESIGN_PHASES.md`의 표를 먼저 갱신하고, 완료 후 상태를 "완료"로 바꾸는 기존 패턴을 그대로 따르면 된다.

---

## 5. 이 문서를 언제 갱신하나

- 새 라이브러리를 `requirements*.txt`에 추가할 때 → 1절에 링크 추가.
- 버전을 올릴 때 (`VERSION`, `installer/CloneUp.iss`, `app/__init__.py`) → 2절 표의 버전 숫자 갱신.
- `docs/DIFFERENTIATION.md`를 고칠 때 → 3절과 내용이 어긋나지 않는지 확인.
- `docs/DESIGN_PHASES.md` 단계가 진행될 때 → 4절 표 갱신.
