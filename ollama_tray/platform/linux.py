import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

from ollama_tray.icon import set_icon_path

os.environ.setdefault("PYSTRAY_BACKEND", "appindicator")

AUTOSTART_NAME = "ollama-tray"
_AUTOSTART_DIR = Path.home() / ".config" / "autostart"
_DESKTOP_FILE  = _AUTOSTART_DIR / f"{AUTOSTART_NAME}.desktop"

_SERVICE_MODE: str | None = None


def _find_ollama_icon() -> str | None:
    candidates = [
        "/usr/share/icons/hicolor/256x256/apps/ollama.png",
        "/usr/share/icons/hicolor/128x128/apps/ollama.png",
        "/usr/share/icons/hicolor/64x64/apps/ollama.png",
        os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/ollama.png"),
        os.path.join(os.path.dirname(__file__), "..", "..", "assets", "ollama-icon.png"),
    ]
    return next((c for c in candidates if os.path.exists(c)), None)


def _detect_service_mode() -> str | None:
    for flag in ([], ["--user"]):
        try:
            r = subprocess.run(
                ["systemctl", *flag, "status", "ollama"],
                capture_output=True, timeout=5,
            )
            if r.returncode in (0, 3):
                return "user" if flag else "system"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return None


def init() -> None:
    global _SERVICE_MODE
    if _SERVICE_MODE is None:
        _SERVICE_MODE = _detect_service_mode()
    set_icon_path(_find_ollama_icon())


def _ctl(*args, timeout: int = 10) -> subprocess.CompletedProcess:
    base = ["systemctl"]
    if _SERVICE_MODE == "user":
        base.append("--user")
    return subprocess.run(
        [*base, *args],
        capture_output=True, text=True, timeout=timeout,
    )


def get_status() -> str:
    if _SERVICE_MODE is None:
        procs = [p for p in psutil.process_iter(["name"])
                 if "ollama" in (p.info.get("name") or "").lower()]
        return "running" if procs else "stopped"
    try:
        r = _ctl("is-active", "ollama")
        state = r.stdout.strip()
        return {
            "active":       "running",
            "inactive":     "stopped",
            "activating":   "starting",
            "deactivating": "stopping",
            "failed":       "stopped",
        }.get(state, "unknown")
    except Exception:
        return "unknown"


def _is_root() -> bool:
    return os.getuid() == 0


def _elevate(action: str) -> None:
    exe = sys.executable
    script = os.path.abspath(sys.argv[0])
    for elevator in ("pkexec", "kdesu", "gksudo", "gksu"):
        try:
            subprocess.Popen([elevator, exe, script, f"--{action}"])
            return
        except FileNotFoundError:
            continue


def _svc_start() -> None:
    _ctl("start", "ollama", timeout=30)


def _svc_stop() -> None:
    _ctl("stop", "ollama", timeout=30)


def service_action(action: str) -> None:
    if _SERVICE_MODE is None:
        return
    needs_root = _SERVICE_MODE == "system" and not _is_root()
    if needs_root:
        _elevate(action)
        return
    try:
        if action == "start":
            _svc_start()
        elif action == "stop":
            _svc_stop()
    except Exception:
        pass


def cli_start() -> int:
    if _SERVICE_MODE is None:
        print("No systemd ollama unit found. Start ollama manually.")
        return 1
    try:
        _svc_start()
        print("Ollama service started.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cli_stop() -> int:
    if _SERVICE_MODE is None:
        print("No systemd ollama unit found.")
        return 1
    try:
        _svc_stop()
        print("Ollama service stopped.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cli_restart() -> int:
    rc = cli_stop()
    if rc != 0:
        return rc
    time.sleep(2)
    return cli_start()


def cli_status() -> int:
    st = get_status()
    mode = f" (systemd {_SERVICE_MODE})" if _SERVICE_MODE else " (process)"
    print(f"Ollama{mode}: {st}")
    return 0 if st == "running" else 1


def cli_install() -> int:
    _AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    _DESKTOP_FILE.write_text(_desktop_entry())
    _DESKTOP_FILE.chmod(0o644)
    print(f"Installed autostart: {_DESKTOP_FILE}")
    return 0


def cli_uninstall() -> int:
    if _DESKTOP_FILE.exists():
        _DESKTOP_FILE.unlink()
        print(f"Removed autostart: {_DESKTOP_FILE}")
    else:
        print(f"No autostart entry found at {_DESKTOP_FILE}")
    return 0


def _desktop_entry() -> str:
    exe = sys.executable
    icon_path = _find_ollama_icon()
    if getattr(sys, "frozen", False):
        exec_line = f'Exec="{exe}"'
    else:
        script = os.path.abspath(sys.argv[0])
        exec_line = f'Exec={exe} "{script}"'
    icon_line = f"Icon={icon_path}" if icon_path else "Icon=ollama"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Ollama Tray\n"
        "Comment=Ollama system tray manager\n"
        f"{exec_line}\n"
        f"{icon_line}\n"
        "Hidden=false\n"
        "NoDisplay=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-KDE-autostart-enabled=true\n"
        "X-KDE-autostart-phase=2\n"
    )
