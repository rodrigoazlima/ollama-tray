# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for setup.exe (self-contained installer for ollama-tray).
# ollama-tray.spec must be built first so dist/ollama-tray.exe exists.
# Build via: .\windows\build.ps1

import os
import sys as _sys
from pathlib import Path

_here     = Path(SPECPATH).parent   # repo root (spec lives in windows/)
_src      = str(_here / "windows" / "setup_installer.py")
_tray_exe = str(_here / "dist" / "ollama-tray.exe")
_ico      = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Programs", "Ollama", "app.ico",
)
_icon_arg = [_ico] if os.path.exists(_ico) else []

if not os.path.exists(_tray_exe):
    print(f"ERROR: {_tray_exe} not found. Build ollama-tray.spec first.", file=_sys.stderr)
    raise SystemExit(1)

a = Analysis(
    [_src],
    pathex=[str(_here)],
    binaries=[],
    datas=[(_tray_exe, ".")],
    hiddenimports=["winreg", "tkinter", "tkinter.font"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_arg,
)
