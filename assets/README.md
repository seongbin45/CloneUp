# `assets/` — 정적 자원

실행 시 읽히는 **이미지 등**을 둡니다. (현재는 아이콘 위주)

## 하위

| 폴더 | 내용 |
|------|------|
| [icons/](icons/README.md) | 앱 아이콘 PNG/ICO |

## 배포

PyInstaller가 `assets/icons` 를 exe 묶음에 넣습니다.  
아이콘을 바꿨으면 **반드시 Setup을 다시 빌드**해야 설치본에 반영됩니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```
