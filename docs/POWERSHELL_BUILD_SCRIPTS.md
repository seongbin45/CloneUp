# PowerShell 빌드 스크립트 설명 (초심자용)

확장자 **`.ps1`** 은 Windows **PowerShell 스크립트**입니다.  
(오타로 `.psl` 이라고 부르기도 하는데, 실제 파일 이름은 **`.ps1`** 입니다.)

CloneUp 에서 exe / 설치 파일을 만들 때 쓰는 두 파일:

| 파일 | 역할 |
|------|------|
| [`scripts/build_exe.ps1`](../scripts/build_exe.ps1) | Python 코드 → `CloneUp.exe` 폴더 만들기 |
| [`scripts/build_installer.ps1`](../scripts/build_installer.ps1) | 위 exe를 만든 뒤 → `CloneUp-Setup.exe` 설치 파일 만들기 |

직접 타이핑해서 긴 명령을 치지 않도록, **미리 적어 둔 레시피**라고 생각하면 됩니다.

---

## 1. 왜 PowerShell 파일을 만들었나?

exe 를 만들려면 대략 이런 일을 **매번 순서대로** 해야 합니다.

1. 프로젝트 폴더로 이동한다  
2. 가상환경의 Python 경로를 찾는다  
3. PyInstaller 가 없으면 설치한다  
4. `cloneup.spec` 설정으로 빌드한다  
5. `dist\CloneUp\CloneUp.exe` 가 생겼는지 확인한다  
6. (설치 파일까지) Inno Setup 컴파일러(`ISCC.exe`)를 찾아 실행한다  
7. `installer\Output\CloneUp-Setup.exe` 가 생겼는지 확인한다  

초심자가 이 순서를 외우거나, 경로를 잘못 치면 실패하기 쉽습니다.  
그래서 **같은 순서를 `.ps1` 파일에 적어 두고**, 한 줄로 실행하게 만들었습니다.

```text
사람:  “설치 파일 만들어줘”
  ↓
build_installer.ps1 이 위 1~7 을 대신 실행
  ↓
CloneUp-Setup.exe 생성
```

---

## 2. `.ps1` 파일은 어떻게 “만든” 건가? (손으로 쓴 텍스트)

특별한 마법 도구가 있는 것이 아닙니다.

1. 메모장 / VS Code / Cursor 등으로 **새 텍스트 파일**을 만든다  
2. 확장자를 **`.ps1`** 로 저장한다 (예: `build_exe.ps1`)  
3. 안에 **PowerShell 문법**으로 명령을 적는다  
4. 저장소의 `scripts/` 폴더에 둔다  
5. Git 에 커밋해서 모두가 같은 레시피를 쓰게 한다  

즉 **소스 코드와 같은 종류**입니다.  
Python 의 `.py` 가 “파이썬 명령 모음”이라면,  
`.ps1` 은 “Windows 셸 명령 모음”입니다.

### 실행하는 방법 (왜 `-ExecutionPolicy Bypass` 가 붙나)

Windows 는 보안 때문에, 인터넷에서 받은 스크립트를 함부로 실행하지 못하게  
**실행 정책(ExecutionPolicy)** 이 있을 수 있습니다.

그래서 문서에서는 이렇게 적습니다.

```powershell
cd C:\경로\CloneUp
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

| 부분 | 의미 |
|------|------|
| `powershell` | PowerShell 을 켠다 |
| `-ExecutionPolicy Bypass` | **이 한 번 실행**에 한해 정책 검사를 느슨하게 (스크립트 내용을 우리가 만든 것으로 믿을 때) |
| `-File scripts\...ps1` | 그 파일을 실행한다 |

**주의:** 모르는 사람이 준 `.ps1` 은 함부로 Bypass 로 실행하지 마세요.  
이 저장소의 `scripts\build_*.ps1` 은 우리가 작성·검토한 파일입니다.

---

## 3. `build_exe.ps1` 을 줄 단위로 읽기

파일 위치: `scripts/build_exe.ps1`

### 3-1. 주석 (설명일 뿐, 실행 안 됨)

```powershell
# Build CloneUp Windows onedir with PyInstaller
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

`#` 로 시작하는 줄은 **메모**입니다. 컴퓨터는 무시합니다.

### 3-2. 에러가 나면 즉시 멈추기

```powershell
$ErrorActionPreference = "Stop"
```

중간 명령이 실패하면, 다음 줄로 넘어가지 않고 **멈춥니다**.  
(반쯤 깨진 exe 가 생기는 걸 줄입니다.)

### 3-3. “프로젝트 루트” 폴더 찾기

```powershell
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
```

| 기호 | 의미 |
|------|------|
| `$MyInvocation.MyCommand.Path` | 지금 실행 중인 `.ps1` 파일의 전체 경로  
| 예: `C:\...\CloneUp\scripts\build_exe.ps1` |
| `Split-Path -Parent` 한 번 | 상위 폴더 → `...\CloneUp\scripts` |
| `Split-Path -Parent` 두 번 | 그 상위 → `...\CloneUp` (**저장소 루트**) |
| `Set-Location $Root` | 작업 폴더를 CloneUp 루트로 이동 |

그래서 **어느 폴더에서 실행해도**, 스크립트가 알아서 프로젝트 루트로 갑니다.

### 3-4. 가상환경 Python 확인

```powershell
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Missing venv: $py"
}
```

- 개발용 Python 은 보통 `.venv\Scripts\python.exe` 에 있습니다.  
- 없으면 “가상환경을 먼저 만들어라”는 뜻으로 에러를 냅니다.  
- 초심자 준비: 루트 README 2-3장 (`python -m venv .venv` 등).

### 3-5. PyInstaller 설치 (없으면 받기)

```powershell
& $py -m pip install -q "pyinstaller>=6.0"
```

| 부분 | 의미 |
|------|------|
| `& $py` | 위에서 찾은 python.exe 실행 |
| `-m pip install` | pip 으로 패키지 설치 |
| `-q` | 출력 조용히 |
| `pyinstaller>=6.0` | exe 로 묶어 주는 도구 |

PyInstaller = **Python 스크립트 + 라이브러리를 Windows 실행 파일 형태로 포장**하는 프로그램입니다.

### 3-6. 실제 빌드 (스펙 파일 사용)

```powershell
& $py -m PyInstaller --noconfirm (Join-Path $Root "cloneup.spec")
```

| 부분 | 의미 |
|------|------|
| `-m PyInstaller` | PyInstaller 실행 |
| `--noconfirm` | 기존 `dist` 덮어쓸 때 물어보지 않음 |
| `cloneup.spec` | **어떻게 묶을지** 적어 둔 설정 파일 (아이콘, ui 파일 포함, 콘솔 창 없음 등) |

`.ps1` 은 “순서”,  
`cloneup.spec` 은 “포장 명세서” 라고 구분하면 쉽습니다.

### 3-7. 결과 확인

```powershell
$out = Join-Path $Root "dist\CloneUp\CloneUp.exe"
if (-not (Test-Path $out)) {
    Write-Error "Build failed: $out not found"
}
Write-Host "OK: $out"
Get-Item $out | Format-List FullName, Length, LastWriteTime
```

- `dist\CloneUp\CloneUp.exe` 가 생겼는지 검사  
- 경로·파일 크기·수정 시각을 화면에 보여 줌  

**중요:** `CloneUp.exe` 옆의 `_internal` 폴더도 같이 있어야 실행됩니다.  
사용자 배포용은 보통 이 단계만 쓰지 않고, 아래 Setup 단계까지 갑니다.

---

## 4. `build_installer.ps1` 을 줄 단위로 읽기

파일 위치: `scripts/build_installer.ps1`  
역할: **exe 만들기 + 설치 마법사(Setup) 만들기** 를 이어서 실행.

### 4-1. 먼저 exe 빌드 스크립트를 호출

```powershell
& (Join-Path $Root "scripts\build_exe.ps1")
```

같은 폴더의 `build_exe.ps1` 을 **그대로 실행**합니다.  
(위에서 설명한 1~3-7 전체가 여기서 한 번 돌아갑니다.)

### 4-2. exe 가 있는지 재확인

```powershell
$exe = Join-Path $Root "dist\CloneUp\CloneUp.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Missing $exe"
}
```

### 4-3. Inno Setup 컴파일러 찾기

```powershell
$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
```

- **Inno Setup** = Windows 설치 파일(`.exe` 설치 마법사)을 만드는 무료 도구  
- **ISCC.exe** = 그 도구의 **명령줄 컴파일러** (스크립트를 Setup.exe 로 변환)  
- PC 마다 설치 경로가 달라서, 여러 후보 경로를 적어 두고 **있는 첫 경로**를 씁니다.

없으면:

```text
winget install --id JRSoftware.InnoSetup -e
```

안내 후 종료 코드 2 로 끝납니다. (이 경우 `dist\CloneUp` 은 이미 만들어져 있을 수 있음)

### 4-4. 설치 스크립트 컴파일

```powershell
& $iscc (Join-Path $Root "installer\CloneUp.iss")
```

| 파일 | 역할 |
|------|------|
| `installer/CloneUp.iss` | “어떤 파일을 어디에 설치할지, 아이콘, 버전” 을 적은 **설치 설계도** |
| ISCC | 그 설계도 + `dist\CloneUp\*` → **하나의 Setup.exe** 로 압축 |

### 4-5. Setup 결과 확인

```powershell
$setup = Join-Path $Root "installer\Output\CloneUp-Setup.exe"
...
Write-Host "OK: $setup"
```

**사용자에게 줄 파일은 보통 이 `CloneUp-Setup.exe` 하나**입니다.

---

## 5. 전체 그림 (한 장으로)

```text
[소스 코드 app/, main.py, ui/, assets/]
           │
           │  build_exe.ps1
           │  (+ cloneup.spec + PyInstaller)
           ▼
   dist\CloneUp\CloneUp.exe
   dist\CloneUp\_internal\ ...
           │
           │  build_installer.ps1
           │  (+ CloneUp.iss + Inno Setup ISCC)
           ▼
   installer\Output\CloneUp-Setup.exe   ← 배포용
           │
           ▼
   사용자가 Setup 실행 → 설치 → CloneUp 실행
           │
           ▼
   Git 없으면 앱이 설치 안내 (DG1/DG2)
```

---

## 6. 초심자가 직접 “비슷한 .ps1” 을 만들려면 (연습)

1. `scripts` 폴더에 `hello.ps1` 생성  
2. 내용 예:

```powershell
Write-Host "Hello from CloneUp scripts"
Write-Host "현재 폴더:" (Get-Location)
```

3. 실행:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\hello.ps1
```

4. 이해되면 `build_exe.ps1` 을 열어 위 설명과 한 줄씩 대조합니다.  
5. **빌드 스크립트를 고친 뒤**에는 실제로 한 번 돌려 보고, 성공하면 Git 커밋 (루트 README 3장).

---

## 7. 자주 묻는 질문

### Q. `.ps1` 을 더블클릭만 하면 되나?
A. 검은 창이 잠깐 뜨고 닫히거나, 정책 때문에 막힐 수 있습니다.  
문서대로 **PowerShell 에서 `-File` 로 실행**하는 편이 안전합니다.

### Q. Python 이 아니라 PowerShell 인 이유?
A. Windows 에서 “폴더 이동, 파일 있는지 확인, 다른 exe 실행” 을 다루기 쉽고,  
Inno Setup·winget 과도 잘 맞습니다. 앱 본체는 여전히 Python 입니다.

### Q. 스크립트를 고치지 않고 명령만 치려면?
A. 가능합니다. 다만 경로를 직접 써야 해서 실수하기 쉽습니다.  
`.ps1` 은 그 실수를 줄이려고 만든 **공식 레시피**입니다.

### Q. Setup 없이 exe 폴더만 zip 으로 줘도 되나?
A. `dist\CloneUp` **폴더 전체**를 zip 하면 실행은 됩니다.  
초심자 배포는 설치·바로가기가 있는 **Setup.exe** 를 권장합니다.

---

## 8. 관련 문서

| 문서 | 내용 |
|------|------|
| [scripts/README.md](../scripts/README.md) | scripts 폴더 목록 |
| [PACKAGING.md](PACKAGING.md) | 패키징 단계 요약 |
| [installer/README.md](../installer/README.md) | Inno Setup 쪽 설명 |
| [루트 README 4장](../README.md) | 배포 전체 절차 |
