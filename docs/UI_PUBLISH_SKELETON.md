# CloneUp UI — Publish 탭 골격

**범위:** 화면 배치 + 위젯 이름 + 진입점만.  
**아직 안 함:** Device Flow UI, 실제 publish 연결, QThread/QProcess, Clone/Sync 탭 동작.

---

## 창 구조

```
┌─ CloneUp ─────────────────────────────────────────┐
│  상태: Git · 로그인 (플레이스홀더)                    │
├───────────────────────────────────────────────────┤
│  [ Publish ]  (Clone / Sync 탭은 비활성 또는 빈 칸)   │
├───────────────────────────────────────────────────┤
│  로컬 폴더: [______________] [찾아보기]               │
│  저장소 이름: [______________]  (•)공개  ( )비공개     │
│  커밋 메시지: [Initial commit____________]            │
│  [ ] 비밀 파일 경고 무시 (고급)                       │
│                                                     │
│           [ GitHub에 만들고 올리기 ]                  │
├───────────────────────────────────────────────────┤
│  실행 로그 (읽기 전용)                                │
│  …                                                  │
└───────────────────────────────────────────────────┘
```

---

## 파일

| 경로 | 역할 |
|------|------|
| `ui/main_window.ui` | Qt Designer 원본 |
| `app/ui/main_window.py` | `.ui` 로드, 시그널 자리만 |
| `main.py` | GUI 진입점 |

## 위젯 objectName (코드 연결용)

| objectName | 종류 | 용도 |
|------------|------|------|
| `labelStatusGit` | QLabel | Git 설치 여부 |
| `labelStatusAuth` | QLabel | 로그인 상태 |
| `tabWidget` | QTabWidget | 탭 컨테이너 |
| `tabPublish` | QWidget | Publish 탭 |
| `editFolder` | QLineEdit | 로컬 폴더 경로 |
| `btnBrowseFolder` | QPushButton | 폴더 선택 |
| `editRepoName` | QLineEdit | 저장소 이름 |
| `radioPublic` | QRadioButton | 공개 (기본) |
| `radioPrivate` | QRadioButton | 비공개 (`repo` scope, 앱 기본 로그인) |
| `editCommitMessage` | QLineEdit | 커밋 메시지 |
| `checkAllowSecrets` | QCheckBox | `--allow-secrets` 대응 |
| `btnPublish` | QPushButton | 실행 (아직 stub) |
| `textLog` | QPlainTextEdit | 로그 |

---

## 실행

```powershell
cd C:\Users\seong\Desktop\ProJect\Codyssey_2+1_ProJect\CloneUp
.\.venv\Scripts\python.exe -m pip install PySide6
.\.venv\Scripts\python.exe main.py
```

Designer로 수정:

```text
ui/main_window.ui  → Qt Designer에서 연 뒤 저장 → main.py 재실행
```

---

## 다음 연결 순서 (골격 이후)

1. `btnBrowseFolder` → `QFileDialog.getExistingDirectory`  
2. `btnPublish` → 입력 검증 + `docs/FAILURE_CASES.md` S1/S3 선검사  
3. `QThread`/`QProcess` 로 `publish_*` 호출 (UI 스레드 금지)  
4. 로그 시그널 → `textLog` (토큰 마스킹)  
5. 성공 시 `QDesktopServices.openUrl(html_url)`  
