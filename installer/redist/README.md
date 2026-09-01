# Redistributables for CloneUp-Setup

## Tesseract OCR

File: `tesseract-ocr-w64-setup-5.4.0.20240606.exe`  
Source: [UB-Mannheim Tesseract releases](https://github.com/UB-Mannheim/tesseract/releases)

Download (repo root):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\fetch_tesseract_redist.ps1
```

`build_installer.ps1` calls this automatically before ISCC.  
The large `.exe` is gitignored — fetch before building Setup.
