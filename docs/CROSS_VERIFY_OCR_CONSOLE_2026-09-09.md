# Cross-verify: OCR black console flash (2026-09-09)

## Question

Does Path B Expiration OCR keep flashing a black console / Terminal window?

## Method

1. Static: `pytesseract.subprocess_args` uses `SW_HIDE` only — **no** `CREATE_NO_WINDOW`.
2. Static: `get_tesseract_version()` → naked `subprocess.check_output([tesseract, --version])`.
3. Live: launch **`pythonw.exe`** (no console, same as packaged CloneUp) while enumerating `ConsoleWindowClass` / `CASCADIA_HOSTING_WINDOW_CLASS`.

## Results

| Case | Result |
|------|--------|
| Console-attached `python.exe` + OCR | No *new* console (child attaches / SW_HIDE) — **misleading PASS** |
| **`pythonw` + unpatched tesseract** | **FAIL** — Terminal titled `C:\Program Files\Tesseract-OCR\tesseract.exe` (multiple flashes) |
| `pythonw` + `CREATE_NO_WINDOW` patch | **PASS** — `FLASH_COUNT=0`, `TESSERACT_FLASHES=0` |
| WinOCR-only fast path | No tesseract spawn; but `tesseract_available()` used to call `get_tesseract_version` → still flashed once |

## Fix

`app/util/expiry_ocr.py`:

- Patch `pytesseract.subprocess_args` to OR in `CREATE_NO_WINDOW`.
- `tesseract_available()` uses `winproc.run_hidden([tesseract, --version])` instead of `get_tesseract_version()`.

Field effect needs **CloneUp GUI rebuild** (not UM-only).
