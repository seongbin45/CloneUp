# `installer/` — Windows 설치 관리자 (Inno Setup)

## 파일

| 경로 | 역할 |
|------|------|
| `CloneUp.iss` | Inno Setup 스크립트 (버전·아이콘·설치 경로) |
| `Output/CloneUp-Setup.exe` | **빌드 결과** (gitignore, 재생성) |

## 초심자: Setup 만들기 (처음부터 끝까지)

### 전제
1. 이미 `dist\CloneUp\CloneUp.exe` 가 있거나, 아래 통합 스크립트가 만들어 줌  
2. Inno Setup 6 설치  
   ```powershell
   winget install --id JRSoftware.InnoSetup -e
   ```

### 권장: 한 방에
저장소 루트에서:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

이 명령이 부르는 **`.ps1` 스크립트가 무엇인지** (exe 빌드 → Setup 컴파일 순서)는  
초심자용 설명 문서: [docs/POWERSHELL_BUILD_SCRIPTS.md](../docs/POWERSHELL_BUILD_SCRIPTS.md)

### 결과물
```
installer\Output\CloneUp-Setup.exe
```

이 파일 **하나만** 사용자에게 전달하면 설치할 수 있습니다.

### 버전 숫자 바꾸기
`CloneUp.iss` 파일 위쪽:

```iss
#define MyAppVersion "0.1.3"
```

올린 뒤 다시 `build_installer.ps1` 실행.

## Git에 올리지 않는 것

- `Output/` 폴더 전체 (Setup.exe 포함)  
→ 배포는 GitHub **Releases** 첨부 권장 (루트 README 4-4).

## Git 설치와의 관계

Setup은 **CloneUp만** 설치합니다.  
PC에 Git이 없으면 앱 **첫 실행** 때 안내합니다 ([docs/GIT_BOOTSTRAP.md](../docs/GIT_BOOTSTRAP.md)).
