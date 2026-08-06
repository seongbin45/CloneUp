# `assets/icons/` — 앱 아이콘

창·작업 표시줄·설치 관리자에 쓰입니다.

## 주요 파일

| 파일 | 용도 |
|------|------|
| `CloneUp.ico` | Windows 멀티 아이콘 **16·24·32·48·64·128·256** (EXE·Setup·제어판·바로가기) |
| `icon-16.png` … `icon-512.png` | 개별 해상도 (Qt `load_app_icon`이 전부 로드) |
| `icon-512-dark.png` | 다크 타일 |
| `mark-glyph.png` | 타일 없는 심볼 |
| [masters/](masters/README.md) | 원본/마스터 보관 |

제어판(앱 및 기능) 아이콘: 설치 시 `{app}\CloneUp.ico` + `UninstallDisplayIcon`  
창/작업 표시줄: `app/ui/icons.py` → ICO + 모든 PNG 크기

## 다시 만들기 (권장 경로)

시안 비율 기준 **벡터 렌더** (선명):

```powershell
.\.venv\Scripts\python.exe scripts\render_icons.py
```

시안 PNG 스트립에서 추출(레거시):

```powershell
.\.venv\Scripts\python.exe scripts\import_design_pngs.py
```

## 변경 후

1. `main.py` 로 창 아이콘 확인  
2. 커밋에 `assets/icons/*` 포함  
3. 배포 시 Setup **재빌드** (루트 README 4장)

디자인 시안: [`desin/icon/`](../../desin/icon/README.md)  
검증 메모: [`docs/ICON_CROSS_VERIFY.md`](../../docs/ICON_CROSS_VERIFY.md)
