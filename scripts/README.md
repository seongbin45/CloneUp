# `scripts/` — 빌드·검증·아이콘 스크립트

PowerShell / Python 보조 도구입니다. **앱 실행에 필수는 아닙니다.**

## 목록

| 스크립트 | 하는 일 | 언제 쓰나 |
|----------|---------|-----------|
| `build_exe.ps1` | PyInstaller → `dist/CloneUp/` | exe만 필요할 때 |
| `build_installer.ps1` | exe + Inno Setup → `installer/Output/CloneUp-Setup.exe` | **사용자 배포** |
| `render_icons.py` | 선명한 아이콘 재생성 | 아이콘 수정 |
| `import_design_pngs.py` | 시안 PNG에서 아이콘 추출 | 디자인 export 반영 |
| `generate_icons.py` | 마스터 기반 리사이즈/ICO | masters/ 있을 때 |
| `cross_verify.py` | 기능 교차검증 | 커밋 전 권장 |
| `verify_pii_crosscheck.py` | 개인정보 스캔 규칙 검증 | safety 수정 후 |

## 초심자: 배포 한 줄

저장소 **루트**에서:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

성공 시 사용자에게 줄 파일:

`installer\Output\CloneUp-Setup.exe`

자세한 순서: 루트 [README.md](../README.md) **4장**, [docs/PACKAGING.md](../docs/PACKAGING.md).

## 주의

- `dist/`, `installer/Output/` 은 Git에 올리지 않습니다.  
- Inno Setup이 없으면 Setup 단계만 실패하고, exe는 `dist/`에 남을 수 있습니다.
