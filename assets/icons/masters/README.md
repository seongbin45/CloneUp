# `assets/icons/masters/` — 아이콘 마스터

| 파일 | 설명 |
|------|------|
| `icon-512.png` | 라이트 타일 512 |
| `icon-512-dark.png` | 다크 타일 512 |
| `mark-glyph.png` | 단색 심볼 |
| `icon-16/24/32.png` | (선택) 소형 단순화 |

## 초심자

- **일상 수정**은 상위 폴더의 `render_icons.py` 결과물을 쓰면 됩니다.  
- 디자인 툴에서 **원본 PNG를 받았을 때** 여기에 넣고:

```powershell
.\.venv\Scripts\python.exe scripts\generate_icons.py
```

(마스터가 없으면 generate 스크립트는 안내만 하고 중단합니다.  
플레이스홀더 강제 생성은 `--invent-placeholder` — 비권장.)

배포: 아이콘이 바뀌면 Setup 재빌드 (루트 [README.md](../../../README.md) 4장).
