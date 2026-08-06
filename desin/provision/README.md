# `desin/provision/` — 약관·고지 시안

| 파일 | 내용 |
|------|------|
| `CloneUp 이용약관.dc.html` | 이용약관 시안 (**원본**) |

## 설치 관리자 연동

이 HTML이 설치 동의 약관의 원본입니다.

```powershell
.\.venv\Scripts\python.exe scripts\export_terms_license.py
```

| 산출물 | 용도 |
|--------|------|
| `installer/license/CloneUp_Terms_ko.txt` | Inno Setup `LicenseFile` (설치 시 동의) |
| `legal/CloneUp_Terms_ko.txt` | 저장소·앱 번들 사본 |

시안을 고친 뒤 → 위 스크립트 → `scripts\build_installer.ps1` 으로 Setup 재빌드.  
(`build_installer.ps1` 은 추출을 자동 호출합니다.)

## 초심자

- 설치 마법사에서 약관에 동의해야 설치가 진행됩니다.
- 설치 후 파일 위치: `{app}\legal\CloneUp_Terms_ko.txt`
- 앱 안 별도 약관 창은 아직 없을 수 있습니다.
- 대괄호 `[ ]` 항목은 배포 전 운영자 정보로 채우고 법률 검토를 받으세요.
