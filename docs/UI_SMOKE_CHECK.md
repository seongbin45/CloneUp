# UI 스모크 점검 — 메뉴·버튼 오류 확인

목적: **"오류가 나는 메뉴나 작동 안 하는 기능이 있는지"** 정기적으로 확인하기 위한 방법과, 가장 최근 점검 결과.

## 방법 (헤드리스 오프스크린 드라이버)

CloneUp은 Windows 전용 PySide6 데스크톱 앱이라 화면이 없는 환경에서는 그냥 "실행"할 수 없다.
`QT_QPA_PLATFORM=offscreen` 로 Qt를 오프스크린 모드로 띄우면 **실제 `.venv`의 진짜 앱 코드**
(`app/ui/main_window.py`)를 화면 없이 그대로 구동해서, `QTest.mouseClick`으로 각 버튼을 누르고
예외 발생 여부·다이얼로그 반응을 확인할 수 있다.

```powershell
# .venv\Scripts\python.exe 로 실행 (진짜 앱 의존성 그대로 사용)
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe <드라이버 스크립트 경로>
```

### 안전 규칙 (반드시 지킬 것)

실제 개발 PC의 키링(Windows Credential Manager)에 **진짜 GitHub 로그인 토큰이 저장돼 있을 수 있다.**
자동 점검 스크립트는 절대:

- `btnLogout` 을 클릭하지 않는다 (실제 저장된 연결이 삭제됨).
- 「Yes / 확인 / 삭제」류의 확인 다이얼로그를 자동으로 누르지 않는다 — 항상 No/Cancel/Discard 계열만 자동 클릭.
- 실제 폴더 경로·저장소 이름을 채워 올리기(Publish)/받기(Clone)를 **끝까지 실행하지 않는다** — 빈 입력값으로
  눌러서 "검증 경고가 뜨는지"만 확인한다 (소스 확인 결과 `on_publish`/`on_clone`은 빈 필드일 때
  `QMessageBox.warning` 후 즉시 return, git/GitHub 호출 이전에 멈춘다).

## 최근 점검 결과 — 2026-08-08

실행: `seongbin45/gulper` 브랜치, WSL에서 `.venv\Scripts\python.exe`를 상호운용성으로 직접 호출.
15개 항목 모두 예외 없이 통과.

| 항목 | 결과 | 비고 |
|------|------|------|
| 앱 기동 (`load_main_window`) | 정상 | |
| 탭 전환 (만들고 올리기 / 받기 / 동기화) | 정상 | 3개 전부 |
| `btnSettings` | 정상 | `SettingsDialog` 열고 닫힘 |
| `btnHelpOnboarding` | 정상 | `OnboardingDialog` 열고 닫힘 |
| `btnPublish` (빈 입력) | 정상 | "로컬 폴더를 선택하세요" 경고 후 중단 |
| `btnBrowseFolder` | 정상 | 네이티브 폴더 선택창 뜸 |
| `btnClone` (빈 입력) | 정상 | 경고 후 중단 |
| `btnCloneBrowseParent` | 정상 | 네이티브 폴더 선택창 뜸 |
| `btnCloneHistory` | 정상 | |
| `btnCloneRepoList` | 정상 | **참고 아래** |
| `btnSyncBrowse` | 정상 | 네이티브 폴더 선택창 뜸 |
| `btnSyncRefresh` | 정상 | |
| `btnSyncHistory` | 정상 | |

**참고**: 점검을 실행한 PC에 이미 실제 GitHub 로그인이 저장돼 있어서, `btnCloneRepoList` 클릭이
`is_logged_in() == True` 분기를 타서 **실제 GitHub API로 내 저장소 목록을 읽어왔다** (읽기 전용,
`GET /user/repos` — 계정에 쓰기 동작 없음). 로그인 안 된 PC에서 점검하면 이 버튼은 대신
"GitHub에 연결한 뒤에…" 안내 메시지만 뜬다 (`main_window.py:1604` 분기).

## 다음에 점검할 때

- 이 방식(오프스크린 + QTest)이 유용하면 `.claude/skills/run-*` 같은 재사용 가능한 스킬로
  고정해 두는 걸 권장 (`/run-skill-generator`). 그러면 다음에 "메뉴 점검해줘" 했을 때 매번
  드라이버를 새로 짜지 않아도 된다.
- 지금 점검은 **클릭했을 때 죽지 않는지 / 검증 경고가 뜨는지**만 본다. 실제 GitHub 업로드·받기까지
  끝까지 도는 End-to-End 테스트는 별도로 (테스트 전용 계정 + 임시 저장소로) 설계해야 한다.
