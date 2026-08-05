# `app/` — 프로그램 본체

CloneUp의 **실제 동작 코드**가 모인 곳입니다.  
`main.py`가 이 패키지를 불러 창을 띄웁니다.

## 하위 폴더

| 폴더 | 역할 | README |
|------|------|--------|
| [auth/](auth/README.md) | GitHub Device Flow 로그인, 토큰(keyring) | 링크 |
| [git/](git/README.md) | clone / publish / sync, 안전·PII 검사 | 링크 |
| [github/](github/README.md) | GitHub REST API (저장소 생성 등) | 링크 |
| [ui/](ui/README.md) | 화면 컨트롤러, 팝업, 워커 스레드 | 링크 |
| [util/](util/README.md) | 로그 마스킹, 실패 시 「다음:」 문구 | 링크 |

루트 파일:

| 파일 | 역할 |
|------|------|
| `config.py` | OAuth client id·scope 기본값 (`.env` 선택 오버라이드) |
| `paths.py` | 개발 폴더 vs exe(동결) 경로 |

## 초심자: 여기를 만질 때

1. **기능 버그 / 새 동작** → 위 표에서 해당 폴더 README를 연다.  
2. **화면 배치·문구만** → `app/ui/` + 상위 [`ui/`](../ui/README.md).  
3. 수정 후:
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```
4. 커밋·병합·배포는 **저장소 루트 [README.md](../README.md) 3~4장**.

## 배포와의 관계

- 이 폴더 소스는 PyInstaller가 `main.py`부터 분석해 **exe 안에 포함**됩니다.  
- `app/`만 zip으로 사용자에게 주면 실행되지 않습니다. Setup 또는 `dist/CloneUp` 전체가 필요합니다.
