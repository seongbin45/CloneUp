# `ui/` — Qt Designer 화면 파일

| 파일 | 역할 |
|------|------|
| `main_window.ui` | 메인 창 레이아웃 (탭, 입력란, 로그 영역 등) |

## 초심자

1. **글자·배치만** 바꿀 때: Qt Designer로 `main_window.ui` 편집 **또는** XML을 신중히 수정.  
2. **버튼 동작**은 여기가 아니라 `app/ui/main_window.py` 에서 위젯 이름(`objectName`)으로 연결합니다.  
3. `.ui` 에서 위젯 이름을 바꾸면 **파이썬 쪽 `findChild(..., "이름")` 도 같이** 바꿔야 합니다.

## 배포

`.ui` 파일은 exe 빌드 시 `cloneup.spec` 에 의해 번들에 포함됩니다.  
수정 후 Setup을 다시 만들려면 루트 README **4장**.
