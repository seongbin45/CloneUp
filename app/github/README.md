# `app/github/` — GitHub REST API

토큰으로 GitHub 서버에 요청하는 얇은 계층입니다.

## 파일

| 파일 | 역할 |
|------|------|
| `api_client.py` | `GET /user`, repos/branches/commits, zipball 스냅샷, `POST /user/repos` (auto_init 금지 등) |

## 초심자 메모

- **로그인 절차**는 여기가 아니라 `app/auth/` 입니다.  
- 저장소 **생성 실패**(이름 중복, 권한) 메시지를 바꾸려면 `api_client.py`와 이를 부르는 `app/git/publish.py`를 함께 봅니다.  
- 네트워크·토큰 문제는 UI에서 「Device 인증 실패」「다음: 로그인…」으로 이어질 수 있습니다.

## 변경 후

```powershell
.\.venv\Scripts\python.exe spike_create_repo.py --help
.\.venv\Scripts\python.exe main.py
```

병합·배포는 루트 [README.md](../../README.md).
