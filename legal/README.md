# `legal/` — 배포용 약관 사본

| 파일 | 설명 |
|------|------|
| `CloneUp_Terms_ko.txt` | 설치 동의·앱 번들용 이용약관 (UTF-8 BOM) |
| `CloneUp_OpenSourceNotices_ko.txt` | 오픈소스 구성요소(PySide6·requests·python-dotenv·keyring) 고지문 |

앱 자체의 Apache License 2.0 전문은 저장소 루트 [`LICENSE`](../LICENSE) 에 있으며,
설치본에는 `{app}\LICENSE` 로 복사됩니다. 설정 → 정보에서 **이용약관 / 라이선스 /
오픈소스 고지** 로 열 수 있습니다.

**원본 시안:** [`desin/provision/CloneUp 이용약관.dc.html`](../desin/provision/CloneUp%20이용약관.dc.html)

재생성 (이용약관만 해당):

```powershell
.\.venv\Scripts\python.exe scripts\export_terms_license.py
```

Inno Setup 도 `installer/license/` 에 동일 내용을 씁니다.

`CloneUp_OpenSourceNotices_ko.txt`는 자동 생성 스크립트가 없습니다. `requirements.txt`가
바뀌면(특히 PySide6 버전) 각 패키지의 `.venv/Lib/site-packages/<pkg>.dist-info/licenses/`를
다시 확인해 수동으로 갱신해야 합니다.
