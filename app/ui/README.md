# `app/ui/` — 화면과 백그라운드 작업

버튼을 누르면 **워커 스레드**가 git/로그인을 하고,  
메인 스레드는 팝업·로그·상태 줄을 갱신합니다.

## 주요 파일

| 파일 | 역할 |
|------|------|
| `main_window.py` | 메인 창 로직, 탭 동작, G3 확인, 로그아웃, Git 부트스트랩 호출 |
| `device_code_dialog.py` | 장치 코드 팝업 (로그인 취소 / 로그아웃) |
| `auth_status.py` | 상단 GitHub 로그인 상태 점 |
| `tip_card.py` | 탭 도움말 접기 카드 |
| `git_setup.py` | Git 없을 때 설치 안내 대화상자 |
| `theme.py` | 라이트/다크 색 QSS |
| `publish_worker.py` | 로그인·Publish 스레드 |
| `tab_workers.py` | Clone / Sync 스레드 |
| `settings_store.py` | 최근 폴더 등 QSettings |
| `icons.py` | 창 아이콘 로드 |

화면 **배치 XML**은 여기가 아니라 [`ui/main_window.ui`](../../ui/README.md) 입니다.

## 초심자: 자주 하는 수정

| 수정 | 어디 |
|------|------|
| 버튼 누른 뒤 동작 | `main_window.py` 해당 `on_*` |
| 팝업 문구 | `device_code_dialog.py`, `git_setup.py`, `main_window` 의 `QMessageBox` |
| 색/다크모드 | `theme.py` |
| 팁 카드 본문 | `main_window.py` → `_install_tab_tip_cards` |

## 변경 후

```powershell
.\.venv\Scripts\python.exe main.py
```

탭 전환, 로그인 팝업, 해당 버튼만 확인 → 루트 README 3~4장으로 배포.
