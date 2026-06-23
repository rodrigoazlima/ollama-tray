import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import psutil

from ollama_tray.config import AUTOSTART_NAME, OLLAMA_URL
from ollama_tray.icon import set_icon_path

os.environ.setdefault("PYSTRAY_BACKEND", "appindicator")

_AUTOSTART_DIR = Path.home() / ".config" / "autostart"
_DESKTOP_FILE  = _AUTOSTART_DIR / f"{AUTOSTART_NAME}.desktop"

_SERVICE_MODE: str | None = None   # "system" | "user" | None


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


def _http_ping() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/version", timeout=2):
            return True
    except Exception:
        return False


def _process_running() -> bool:
    return any(
        "ollama" in (p.info.get("name") or "").lower()
        for p in psutil.process_iter(["name"])
    )


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


_SYSTEMD_STATE_MAP = {
    "active":       "running",
    "inactive":     "stopped",
    "activating":   "starting",
    "deactivating": "stopping",
    "reloading":    "starting",
    "failed":       "stopped",
}


def get_status() -> str:
    if _SERVICE_MODE is not None:
        try:
            r = _ctl("is-active", "ollama")
            return _SYSTEMD_STATE_MAP.get(r.stdout.strip(), "unknown")
        except Exception:
            return "unknown"
    # No systemd unit: HTTP ping, then process scan
    if _http_ping():
        return "running"
    return "running" if _process_running() else "stopped"


def service_label() -> str:
    """'Service' when a systemd unit is detected; 'Ollama' otherwise."""
    return "Service" if _SERVICE_MODE is not None else "Ollama"


def _is_root() -> bool:
    return os.getuid() == 0


def _elevate(action: str) -> bool:
    """Try graphical privilege elevation. Returns True if an elevator was launched."""
    exe = sys.executable
    script = os.path.abspath(sys.argv[0])
    for elevator in ("pkexec", "kdesu", "gksudo", "gksu"):
        try:
            subprocess.Popen([elevator, exe, script, f"--{action}"])
            return True
        except FileNotFoundError:
            continue
    return False


def _svc_start() -> None:
    _ctl("start", "ollama", timeout=30)


def _svc_stop() -> None:
    _ctl("stop", "ollama", timeout=30)


def _ollama_env() -> dict[str, str]:
    """Build environment dict for `ollama serve` from config settings."""
    from ollama_tray.config import (
        SERVE_HOST, OLLAMA_MODELS_DIR, OLLAMA_NUM_GPU, OLLAMA_FLASH_ATTENTION,
        OLLAMA_KV_CACHE_TYPE, OLLAMA_NUM_PARALLEL, OLLAMA_MAX_LOADED_MODELS,
        HSA_ENABLE_SDMA,
    )
    env = os.environ.copy()
    if SERVE_HOST:
        env["OLLAMA_HOST"] = SERVE_HOST
    if OLLAMA_MODELS_DIR:
        env["OLLAMA_MODELS"] = OLLAMA_MODELS_DIR
    if OLLAMA_NUM_GPU:
        env["OLLAMA_NUM_GPU"] = OLLAMA_NUM_GPU
    if OLLAMA_FLASH_ATTENTION == "1":
        env["OLLAMA_FLASH_ATTENTION"] = "1"
    if OLLAMA_KV_CACHE_TYPE and OLLAMA_KV_CACHE_TYPE != "f16":
        env["OLLAMA_KV_CACHE_TYPE"] = OLLAMA_KV_CACHE_TYPE
    if OLLAMA_NUM_PARALLEL > 1:
        env["OLLAMA_NUM_PARALLEL"] = str(OLLAMA_NUM_PARALLEL)
    if OLLAMA_MAX_LOADED_MODELS > 1:
        env["OLLAMA_MAX_LOADED_MODELS"] = str(OLLAMA_MAX_LOADED_MODELS)
    if HSA_ENABLE_SDMA:
        env["HSA_ENABLE_SDMA"] = HSA_ENABLE_SDMA
    return env


def _start_process() -> None:
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            env=_ollama_env(),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        from ollama_tray.checks import _show_warning
        _show_warning(
            "ollama-tray: Ollama not found",
            "Ollama binary not found in PATH.\n"
            "Install: curl -fsSL https://ollama.com/install.sh | sh",
        )


def _stop_process() -> None:
    for p in psutil.process_iter(["name", "pid"]):
        if "ollama" in (p.info.get("name") or "").lower():
            try:
                p.terminate()
            except psutil.NoSuchProcess:
                pass


def service_action(action: str) -> None:
    if _SERVICE_MODE is None:
        if action == "start":
            _start_process()
        elif action == "stop":
            _stop_process()
        return
    needs_root = _SERVICE_MODE == "system" and not _is_root()
    if needs_root:
        if not _elevate(action):
            from ollama_tray.checks import _show_warning
            _show_warning(
                "ollama-tray: elevation failed",
                "Root access is required to control the system Ollama service,\n"
                "but no graphical privilege elevator (pkexec/kdesu/gksudo) was found.\n\n"
                "Run manually:\n  sudo systemctl " + action + " ollama",
            )
        return
    try:
        if action == "start":
            _svc_start()
        elif action == "stop":
            _svc_stop()
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass


def cli_start() -> int:
    if _SERVICE_MODE is None:
        try:
            _start_process()
            print("Ollama started (process mode).")
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    try:
        _svc_start()
        print("Ollama service started.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cli_stop() -> int:
    if _SERVICE_MODE is None:
        _stop_process()
        print("Ollama processes terminated.")
        return 0
    try:
        _svc_stop()
        print("Ollama service stopped.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
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
