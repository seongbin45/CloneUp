# CloneUp 0.1.3

보안 재검증(외부 리뷰) 반영 릴리스입니다.  
0.1.2 UX 위에 **안전검사·자격증명·origin 검사**를 고쳤습니다.

## 사용자에게 알려 줄 말 (짧게)

1. **만들고 올리기** 시, 확인 창 **전에** 이 폴더를 Git으로 준비합니다 (`.git` · 필요 시 `.gitignore`).  
   안내 창에서 취소할 수 있습니다. 취소해도 이미 준비된 항목은 남을 수 있습니다.
2. **기본 비공개** 저장소로 올립니다 (공개는 직접 선택).
3. 파일 안의 키·인증서처럼 보이는 값은 **고급 허용으로도 막습니다.**
4. 동기화는 **github.com HTTPS** 원격만 지원합니다.

## 설치

- `CloneUp-Setup.exe` 실행 → 설치  
- 0.1.2 위에 덮어쓰기 가능

## 개발자용 변경 요약 (0.1.2 → 0.1.3)

### 보안 (재검증 반영)
- **H1** 안전검사 전에 `ensure_repo_for_safety` (gitignore 존중; 신규 폴더 경로)
- **H2** credential helper 경로 인용 · 앱 전용 temp
- **H3** 설치 파일 서명 검사 fail-closed
- **P2** origin fetch/push URL + local `url.*` 거부
- **M4** hooks 비활성 · `commit --no-verify`
- **M1/M2** stdout 마스킹 · 토큰 누출 정규식 통일

### 기타
- pytest 스위트 · GitHub Actions CI
- PySide6 없이도 보안 테스트 수집 가능 (`importorskip`)
- 죽은 코드 `abandon_created_repo` 제거

## 버전 위치

- `VERSION` · `app/__init__.py` · `installer/CloneUp.iss`
