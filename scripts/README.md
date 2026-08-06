# `scripts/` — 빌드·검증·아이콘 스크립트

PowerShell / Python 보조 도구입니다. **앱 일상 실행에는 필수가 아닙니다.**  
**exe / Setup 을 만들 때**, 아이콘을 다시 뽑을 때, 자동 검증할 때 사용합니다.

---

## PowerShell 파일(`.ps1`)이란? (초심자)

| 이름 | 설명 |
|------|------|
| **`.ps1`** | Windows **PowerShell** 용 스크립트 (명령 레시피) |
| **`.py`** | Python 스크립트 (이 폴더의 아이콘·검증 도구) |

**exe를 만들기 전에** 이 `.ps1` 이 하는 일을 이해하려면:

→ **[docs/POWERSHELL_BUILD_SCRIPTS.md](../docs/POWERSHELL_BUILD_SCRIPTS.md)**  
  (왜 만들었는지, 줄 단위 설명, 실행 방법, 전체 흐름 그림)

요약:

1. 사람이 매번 치기 번거로운 **빌드 순서를 파일에 적어 둔 것**  
2. 메모장/에디터로 작성한 **텍스트 파일** (마법 아님)  
3. 실행 예:
   ```powershell
   cd (CloneUp 저장소 루트)
   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
   ```

---

## 목록

| 스크립트 | 종류 | 하는 일 | 언제 쓰나 |
|----------|------|---------|-----------|
| **`build_exe.ps1`** | `.ps1` | PyInstaller → `dist/CloneUp/` | exe 폴더만 필요할 때 |
| **`build_installer.ps1`** | `.ps1` | 위 실행 + Inno → `CloneUp-Setup.exe` | **사용자 배포** |
| `render_icons.py` | `.py` | 선명한 아이콘 재생성 | 아이콘 수정 |
| `import_design_pngs.py` | `.py` | 시안 PNG에서 아이콘 추출 | 디자인 export 반영 |
| `generate_icons.py` | `.py` | 마스터 기반 리사이즈/ICO | masters/ 있을 때 |
| `cross_verify.py` | `.py` | 기능 교차검증 | 커밋 전 권장 |
| `verify_pii_crosscheck.py` | `.py` | 개인정보 스캔 규칙 검증 | safety 수정 후 |
| `verify_security_crosscheck.py` | `.py` | **보안** 교차검증 (인증·마스킹·git·H1) | 보안/auth/git 수정 후 |

---

## 빌드 두 파일의 관계 (한 줄)

```text
build_exe.ps1          →  dist\CloneUp\CloneUp.exe  (+ _internal)
        ↑
build_installer.ps1    →  먼저 build_exe.ps1 호출
                       →  그다음 Inno Setup 으로 Setup.exe
```

자세한 줄 단위 설명은 [POWERSHELL_BUILD_SCRIPTS.md](../docs/POWERSHELL_BUILD_SCRIPTS.md) **3~4장**.

---

## 초심자: 배포용 Setup 만들기

저장소 **루트**에서:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

성공 시 사용자에게 줄 파일:

`installer\Output\CloneUp-Setup.exe`

전체 배포 순서: 루트 [README.md](../README.md) **4장**, [docs/PACKAGING.md](../docs/PACKAGING.md).

---

## 주의

- `dist/`, `installer/Output/` 은 Git에 올리지 않습니다.  
- Inno Setup이 없으면 Setup 단계만 실패하고, exe 폴더는 `dist/`에 남을 수 있습니다.  
- 모르는 출처의 `.ps1` 은 `-ExecutionPolicy Bypass` 로 실행하지 마세요.
