# ollama-tray package structure

```
ollama-tray/
├── ollama_tray/                  # installable Python package
│   ├── __init__.py               # exports main()
│   ├── __main__.py               # python -m ollama_tray
│   ├── constants.py              # shared tunables: URLs, timings, STATUS_COLOR
│   ├── stats.py                  # OllamaStats dataclass, refresh_stats(), psutil logic
│   ├── icon.py                   # make_icon(), PIL dot-overlay, set_icon_path()
│   ├── dialog.py                 # tkinter resource-monitor dialog (open/toggle/run)
│   ├── tray.py                   # OllamaTray class — pystray menu + poll loop
│   ├── cli.py                    # argparse entry point → main()
│   └── platform/
│       ├── __init__.py           # re-exports correct platform at import time (win32 / else)
│       ├── windows.py            # win32service control, UAC elevation, winreg autostart
│       └── linux.py              # systemd/systemctl control, pkexec elevation, XDG autostart
│
├── assets/
│   ├── ollama.ico
│   ├── ollama-icon.png
│   └── preview.png
│
├── windows/
│   ├── build.ps1                 # PyInstaller build script
│   ├── install.ps1               # user-facing Windows installer
│   └── ollama-tray.spec          # PyInstaller spec
│
├── linux/
│   └── install.sh                # user-facing Linux installer
│
├── pyproject.toml                # build metadata; entry point: ollama-tray = ollama_tray:main
├── requirements.txt              # Windows runtime deps (pystray, Pillow, pywin32, psutil)
├── requirements-linux.txt        # Linux runtime deps (pystray, Pillow, psutil)
├── README.md
└── LICENSE
```

## Module responsibilities

| Module | Responsibility |
|---|---|
| `constants` | Single source of truth for all magic numbers and colour maps |
| `stats` | psutil process scanning; `OllamaStats` accumulator; thread-safe `current_stats()` |
| `icon` | PIL icon rendering with coloured status dot; `set_icon_path()` called by platform `init()` |
| `dialog` | Tkinter resource monitor — debounced open/close, 1 s auto-refresh, catppuccin theme |
| `tray` | `OllamaTray` — builds pystray menu, runs background poll thread, delegates service calls to `platform` |
| `cli` | argparse wiring; calls `platform.init()` before any CLI action; falls through to `OllamaTray().run()` |
| `platform.windows` | `win32service` start/stop/query; UAC re-launch via `ShellExecuteW runas`; `winreg` HKCU Run autostart |
| `platform.linux` | `systemctl` start/stop/is-active; `pkexec`/`kdesu` elevation; XDG `.desktop` autostart |
| `platform.__init__` | Selects the right platform submodule at import time via `sys.platform` |

## Data flow

```
main() [cli.py]
  └─ OllamaTray.run() [tray.py]
       ├─ platform.init()          → set_icon_path() [icon.py]
       ├─ platform.get_status()    → tray icon color
       ├─ refresh_stats() [stats]  → OllamaStats
       ├─ make_icon() [icon]       → PIL image → pystray
       └─ poll thread
            ├─ refresh_stats()
            ├─ platform.get_status()
            └─ open_resource_dialog() [dialog] on double-click
```
