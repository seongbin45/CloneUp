# `desin/dark/` — 다크 모드 창 시안

| 파일 | 내용 |
|------|------|
| `CloneUp Window Dark.dc.html` | 다크 팔레트 메인 창 목업 |
| [`../CloneUp Settings Dark.dc.html`](../CloneUp%20Settings%20Dark.dc.html) | 다크 **설정** 팝업 목업 |

## 코드 연결

- 토큰: `app/ui/theme.py` 의 `DARK`  
- OS 다크 감지 후 QSS 적용: `main.py` → `apply_system_theme`  
- 설정 팝업: `app/ui/settings_dialog.py` (`active_palette()` + 다크 시안 보정)

## 초심자

다크 색을 바꾸려면:

1. 이 HTML에서 색 코드 확인  
2. `app/ui/theme.py` 의 `DARK = Palette(...)` 수정  
3. `main.py` 실행 후 OS를 다크/라이트로 바꿔 확인  
4. 루트 README 3장으로 커밋·병합  

시안만 수정하고 코드를 안 바꾸면 **앱 화면은 변하지 않습니다.**
