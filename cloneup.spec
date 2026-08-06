# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — onedir build for CloneUp (Windows).
# Build:  .\.venv\Scripts\python.exe -m PyInstaller --noconfirm cloneup.spec

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "ui" / "main_window.ui"), "ui"),
        # Multi-size icons: CloneUp.ico + icon-{16..512}.png (+ masters)
        (str(ROOT / "assets" / "icons"), "assets/icons"),
        # Terms of service (installer also ships a copy under {app}\legal)
        (str(ROOT / "legal"), "legal"),
    ],
    hiddenimports=[
        "keyring.backends",
        "keyring.backends.Windows",
        "PySide6.QtUiTools",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "playwright",
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CloneUp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI: use runw.exe — no permanent console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icons" / "CloneUp.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CloneUp",
)
