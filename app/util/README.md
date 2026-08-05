# `app/util/` — 공용 작은 도구

여러 기능이 같이 쓰는 유틸리티입니다.

## 파일

| 파일 | 역할 |
|------|------|
| `log_mask.py` | 로그에 토큰이 찍히지 않게 마스킹 |
| `next_action.py` | 실패 메시지 → 「다음: …」 한 줄 (G4) |

## 초심자

- 로그에 민감정보가 보이면 → `log_mask.py`  
- 실패 후 안내 문구를 늘리려면 → `next_action.py` 의 `next_step_for_error`  
- UI에서 호출: `app/ui/main_window.py` 의 `_log`, `_on_fail_msg`

변경 후 `main.py`로 일부러 실패 상황을 만들어 로그를 확인한 뒤 커밋합니다.  
배포 절차는 루트 [README.md](../../README.md).
