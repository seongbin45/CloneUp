# `desin/icon/` — 로고·아이콘 시안

| 경로 | 내용 |
|------|------|
| `CloneUp Logo.dc.html` | 아이덴티티 보드 |
| `CloneUp Logo Deck.dc.html` | (있을 경우) 덱 시안 |
| [assets/](assets/README.md) | 시안용으로 복사된 아이콘 미리보기 |
| [png/](png/README.md) | 디자인 툴에서 뽑은 selection PNG |

## 앱에 반영하는 법

1. (선택) `png/` 에 export 두기  
2. 권장: 선명 렌더  
   ```powershell
   .\.venv\Scripts\python.exe scripts\render_icons.py
   ```  
3. 결과: `assets/icons/` (여기가 앱·Setup이 쓰는 경로)  
4. 커밋 + Setup 재빌드 (루트 README 4장)

검증: [docs/ICON_CROSS_VERIFY.md](../../docs/ICON_CROSS_VERIFY.md)
