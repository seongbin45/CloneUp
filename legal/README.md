# `legal/` — 배포용 약관 사본

| 파일 | 설명 |
|------|------|
| `CloneUp_Terms_ko.txt` | 설치 동의·앱 번들용 이용약관 (UTF-8 BOM) |

**원본 시안:** [`desin/provision/CloneUp 이용약관.dc.html`](../desin/provision/CloneUp%20이용약관.dc.html)

재생성:

```powershell
.\.venv\Scripts\python.exe scripts\export_terms_license.py
```

Inno Setup 도 `installer/license/` 에 동일 내용을 씁니다.
