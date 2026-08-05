# 원본 아이콘 마스터 (필수)

시안: `desin/icon/CloneUp Logo.dc.html`

이 폴더에 **디자인 툴에서 export한 원본**을 넣으세요.  
현재 상위 `assets/icons/*.png` 는 교차검증 결과 **플레이스홀더**입니다 (`docs/ICON_CROSS_VERIFY.md`).

## 넣을 파일

| 파일 | 설명 |
|------|------|
| `icon-512.png` | 라이트 타일 마크 512×512 |
| `icon-512-dark.png` | 다크 타일 마크 512×512 |
| `mark-glyph.png` | 타일 없는 단색 심볼 (투명 배경) |
| (선택) `icon-16.png` `icon-24.png` `icon-32.png` | 단순화 소형 (없으면 512 리사이즈) |

## 적용

```text
.\.venv\Scripts\python.exe scripts\generate_icons.py
```

심볼을 코드로 다시 그리지 않고, 마스터만 리사이즈·ICO 패킹합니다.
