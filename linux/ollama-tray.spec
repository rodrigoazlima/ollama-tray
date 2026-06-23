# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ollama-tray on Linux.
# Build via: pyinstaller linux/ollama-tray.spec
# Requires system packages: python3-gi gir1.2-ayatanaappindicator3-0.1 python3-tk

from pathlib import Path

_here = Path(SPECPATH).parent   # repo root (spec lives in linux/)
_src  = str(_here / "ollama_tray" / "__main__.py")
_icon = str(_here / "assets" / "ollama-icon.png")

a = Analysis(
    [_src],
    pathex=[str(_here)],
    binaries=[],
    datas=[(str(_here / "assets"), "assets")],
    hiddenimports=[
        "ollama_tray.platform.linux",
        "pystray._appindicator",
        "watchdog.observers",
        "watchdog.observers.inotify",
        "watchdog.events",
        "gi",
        "gi.repository.Gtk",
        "gi.repository.GLib",
        "gi.repository.AyatanaAppIndicator3",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["win32api", "win32con", "win32service", "pywintypes", "winreg"],
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
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[_icon],
)
