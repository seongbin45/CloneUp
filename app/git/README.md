# `app/git/` — Git 작업과 안전 검사

로컬 Git 명령과, 올리기 전 **비밀 파일·개인정보 패턴** 검사를 담당합니다.

## 파일

| 파일 | 역할 |
|------|------|
| `runner.py` | `git` 실행, 버전 확인 |
| `bootstrap.py` | Git 없음 감지, winget, **설치 파일 다운로드(DG2)** |
| `clone_ops.py` | 저장소 받기 |
| `publish.py` | 새 저장소 만들고 첫 푸시, 커밋 이메일 peek |
| `sync_ops.py` | pull / commit+push / 충돌 abort |
| `history.py` | **커밋 내역** 읽기 전용 (목록·변경 파일·시점 스냅샷 추출) |
| `safety.py` | 빈 폴더, `.env` 등 파일명, **내용 전화·이메일 스캔** |
| `credentials.py` | 임시 credential helper (토큰이 config에 안 남게) |
| `url_utils.py` | GitHub URL 정규화 (`/tree/main` 제거 등) |
| `env.py` | 비대화형 git 환경변수 |
| `safety` 관련 문서 | [docs/PII_CROSS_VERIFY.md](../../docs/PII_CROSS_VERIFY.md) |

## 초심자: 언제 수정하나

| 하고 싶은 일 | 파일 |
|--------------|------|
| clone 실패 메시지 | `clone_ops.py` |
| push 실패 처리 | `sync_ops.py`, `publish.py` |
| 비밀 파일 규칙 추가 | `safety.py` (`_SECRET_NAME_RE`) |
| Git 설치 도우미 | `bootstrap.py` + `app/ui/git_setup.py` |

## 변경 후 확인

```powershell
.\.venv\Scripts\python.exe scripts\cross_verify.py
.\.venv\Scripts\python.exe scripts\verify_pii_crosscheck.py
.\.venv\Scripts\python.exe main.py
```

배포: 루트 [README.md](../../README.md) 3~4장.
