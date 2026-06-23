# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ollama-tray.
# Build via: pyinstaller windows/ollama-tray.spec
# Or use:    .\windows\build.ps1

import os
from pathlib import Path

_here = Path(SPECPATH)
_src  = str(_here / "ollama_tray" / "__main__.py")
_ico  = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Programs", "Ollama", "app.ico",
)
_icon_arg = [_ico] if os.path.exists(_ico) else []

a = Analysis(
    [_src],
    pathex=[str(_here)],
    binaries=[],
    datas=[(str(_here / "assets"), "assets")],
    hiddenimports=[
        "ollama_tray.platform.windows",
        "win32service",
        "win32con",
        "pywintypes",
        "watchdog.observers",
        "watchdog.observers.winapi",
        "watchdog.events",
    ],
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
    name="ollama-tray",
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
