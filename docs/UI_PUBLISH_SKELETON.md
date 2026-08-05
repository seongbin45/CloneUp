# CloneUp UI — Publish 탭 골격

**범위:** Publish / Clone / Sync 탭 UI + 백그라운드 작업 연결.  
**아직 안 함:** PyInstaller exe, PAT 폴백, 파일별 add UI.

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

## 연결 상태 (구현됨)

1. `btnBrowseFolder` → 폴더 선택 + 저장소 이름 자동 채움  
2. `btnPublish` → S1/S3 선검사 → `PublishWorker(QThread)`  
3. Worker → `ensure_valid_token` + `publish_folder_to_new_repo`  
4. 로그 → `textLog` (토큰 마스킹)  
5. 성공 → 메시지 박스 + 브라우저로 `html_url`  
