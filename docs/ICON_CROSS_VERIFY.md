# 아이콘 교차검증 (원본 시안 vs 현재 자산)

날짜: 2026-08-06  
시안: `desin/icon/CloneUp Logo.dc.html`

## 결론 (요약)

| 항목 | 결과 |
|------|------|
| 원본 시안 HTML | 있음 (레이아웃·색 토큰·파일명 규약) |
| 원본 비트맵 (`icon-512.png` 등) | **레포/디스크에 없음** |
| 현재 `assets/icons/*` | **플레이스홀더** (`scripts/generate_icons.py` 임의 심볼) |
| 창 아이콘 연결 (I3) | 동작함 — 다만 **원본 마크가 아님** |

→ “원본과 많이 다르다”는 판정은 **타당**. 원인은 시안 미구현이 아니라 **원본 픽셀이 없는 상태에서 심볼을 발명**한 것.

## 시안이 요구하는 파일

| 파일 | 시안 용도 |
|------|-----------|
| `assets/icon-512.png` | 라이트 타일 마크 (가로 조합) |
| `assets/icon-512-dark.png` | 다크 타일 마크 |
| `assets/mark-glyph.png` | 타일 없는 단색 심볼 |
| `icon-16` … `icon-256` | 크기 세트 (16–32는 단순화) |
| `CloneUp.ico` | 멀티 사이즈 Windows 아이콘 |

시안 팔레트 스트립: `#1f6f5c` · `#46a685` · `#f6f2e8` · `#2b2821`  
규칙: 여백 ≥ 심볼 높이 25% · 비율/그라디언트/타일 그림자 금지 · 16–32 단순화.

## 현재 플레이스홀더와의 차이

| | 시안(원본) | 현재 생성물 |
|--|------------|-------------|
| 심볼 형태 | **미확인** (비트맵 부재) | 문서 2장 + 위 화살표 (임의) |
| 타일 색 | 시안 토큰과 동일 계열 가능 | `#1f6f5c` / `#2b2821` 사용 |
| 출처 | 디자인 툴 export 예정 | Pillow 벡터 드로잉 |
| 검증 가능 여부 | 원본 PNG 필요 | 자체 생성 ↔ 시안 HTML 경로만 맞춤 |

첫 `desin/icon/` 목록 시 **HTML만** 있었고 `assets/` 폴더는 없었음.  
이후 생성 스크립트가 `desin/icon/assets/`에 플레이스홀더를 써 넣어, 시안 미리보기도 **가짜 마크**를 가리키게 됨.

## 디스크/Git 조사

- Git 최초 아이콘 커밋: `8fdba4a` — 전부 생성 스크립트 산출물
- 프로젝트/Downloads/로컬에서 `icon-512`·`mark-glyph` **원본 미발견**
- GitHub `desin`에도 원본 비트맵 검색 결과 없음

## 수정 방향 (적용됨)

1. **마스터 필수 파이프라인**  
   - 원본 `icon-512.png` / `icon-512-dark.png` / `mark-glyph.png` 를  
     `assets/icons/masters/` 에 두면  
   - `scripts/generate_icons.py` 가 **리사이즈·ICO만** 수행 (심볼 발명 없음)
2. **임의 발명 모드**는 `--invent-placeholder` 로만 (기본 비활성)
3. 플레이스홀더는 `_placeholder/` 로 격리 가능

## 사용자 액션 (원본 복구)

디자인 툴에서 아래를 export 한 뒤 이 경로에 넣기:

```text
assets/icons/masters/icon-512.png
assets/icons/masters/icon-512-dark.png
assets/icons/masters/mark-glyph.png
```

그다음:

```text
.\.venv\Scripts\python.exe scripts\generate_icons.py
```

→ `assets/icons/` 크기 세트 + `CloneUp.ico` + 시안 미러 갱신, 앱 재실행 시 창 아이콘 반영.

원본 파일이 zip/다른 폴더에 있으면 경로를 알려 주시면 그쪽으로 import 하겠습니다.
