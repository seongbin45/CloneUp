# `desin/` — UI·브랜딩 시안 (디자인 참고)

프로그램 **실행 코드가 아닙니다.**  
디자이너/시안 HTML을 보고 `app/ui/theme.py` 등과 맞출 때 참고합니다.

> 폴더 이름 철자 `desin` 은 프로젝트에 이미 쓰인 이름을 유지합니다.

## 하위

| 경로 | 내용 |
|------|------|
| [CloneUp Window.dc.html](./CloneUp%20Window.dc.html) | 라이트 메인 창 시안 |
| [dark/](dark/README.md) | 다크 창 시안 |
| [icon/](icon/README.md) | 로고·아이콘 시안 |
| [provision/](provision/README.md) | 이용약관 등 문서 시안 |
| [PROMPT_브라우저_안내_연결_시안.md](./PROMPT_브라우저_안내_연결_시안.md) | **브라우저 Path B** 시안용 복붙 프롬프트 |
| [CloneUp 브라우저 안내 대화형.dc.html](./CloneUp%20브라우저%20안내%20대화형.dc.html) | Path B **대화형** 안내 (체크리스트 대체) |
| `support.js` | 시안 뷰어 런타임 |

## 초심자

1. **앱 기능을 고치려면** 여기가 아니라 `app/` 을 수정합니다.  
2. **색·레이아웃을 시안에 맞출 때** 이 HTML을 브라우저로 연 뒤 `app/ui/theme.py` 를 고칩니다.  
3. 시안만 커밋해도 앱 동작은 그대로입니다. Setup 재빌드는 코드/아이콘이 바뀔 때만.

실행·병합·배포 전체 절차: 루트 [README.md](../README.md).
