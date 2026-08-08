# CloneUp 0.1.6

0.1.5 위에 **받기 탭 GitHub 주소 커밋 내역**(로그인 없이 공개 저장소 가능)을 더한 릴리스입니다.

## 사용자에게 알려 줄 말 (짧게)

1. **받기** 탭에 GitHub 주소를 넣고 **커밋 내역**을 누르면, 그 저장소의 커밋을 읽기 전용으로 볼 수 있습니다.
2. **공개 저장소**는 GitHub 연결(로그인) 없이도 됩니다. **비공개**는 위쪽 연결이 필요합니다.
3. **동기화** 탭 커밋 내역은 예전처럼 **내 컴퓨터 폴더** 기준입니다.
4. 「이 시점 파일 보기」는 임시 폴더에 꺼 줍니다. 작업 중인 파일은 바뀌지 않습니다.

## 설치

- `CloneUp-Setup.exe` 실행 → 약관 동의 → 설치  
- 0.1.5 위에 덮어쓰기 가능

## 개발자용 변경 요약 (0.1.5 → 0.1.6)

### 받기 · 원격 커밋 내역
- `list_repo_commits` / `list_remote_changed_files` / `export_remote_commit_snapshot` (zipball)
- `CommitHistoryDialog` 로컬·원격 이중 모드
- `on_clone_history` URL 우선 (공개 API, 토큰 있으면 비공개도)
- 404/403/rate-limit 초심자용 한글 메시지

### 기타 (0.1.5 이후 main에 포함된 것)
- 받기 탭 로컬 커밋 내역 버튼 연결 (a18e689) 후 원격으로 전환
- 온보딩 F11 전체화면 나가기 시 창 복원 수정

## 검증 (릴리스 전)

- pytest (원격 커밋 mock 포함)
- 공개 저장소 API 스모크 (`octocat/Hello-World`)
- UI: 받기 URL → 커밋 내역 / 동기화 로컬 커밋 내역

## 버전 위치

- `VERSION` · `app/__init__.py` · `installer/CloneUp.iss`
