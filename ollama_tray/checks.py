"""
Startup environment checks for ollama-tray.

Fatal checks (wrong Python, missing deps, no tray backend) call sys.exit(1)
after showing a platform-native error dialog or printing to stderr.

Non-fatal checks (Ollama not installed, old version) warn and continue —
the tray still runs, just with limited functionality.
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Callable

from ollama_tray.constants import OLLAMA_URL

_MIN_PYTHON = (3, 10)
_MIN_OLLAMA = (0, 1, 14)


class StartupError(Exception):
    pass


# ── display helpers ───────────────────────────────────────────────────────────

def _show_fatal(title: str, message: str) -> None:
    """Platform-native fatal error dialog (does not exit — caller must)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
            return
        except Exception:
            pass
    else:
        for cmd in (
            ["zenity", "--error", "--title", title, "--text", message, "--no-wrap"],
            ["kdialog", "--error", message, "--title", title],
        ):
            try:
                subprocess.run(cmd, timeout=30, check=False)
                return
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
    print(f"FATAL — {title}\n{message}", file=sys.stderr)


def _show_warning(title: str, message: str) -> None:
    """Platform-native non-fatal warning (non-blocking where possible)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x30)  # MB_ICONWARNING
            return
        except Exception:
            pass
    else:
        try:
            subprocess.run(
                ["notify-send", "-u", "normal", "-t", "8000", title, message],
                timeout=5, check=False,
            )
            return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        for cmd in (
            ["zenity", "--warning", "--title", title, "--text", message, "--no-wrap"],
            ["kdialog", "--sorry", message, "--title", title],
        ):
            try:
                subprocess.run(cmd, timeout=30, check=False)
                return
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
    print(f"WARNING — {title}\n{message}", file=sys.stderr)


# ── fatal checks ──────────────────────────────────────────────────────────────

def check_python_version() -> None:
    if sys.version_info < _MIN_PYTHON:
        ver = ".".join(map(str, sys.version_info[:3]))
        req = ".".join(map(str, _MIN_PYTHON))
        raise StartupError(
            f"Python {req}+ required (running {ver}).\n"
            "Download: https://www.python.org/downloads/"
        )


def check_imports() -> None:
    """Verify all required third-party packages are importable."""
    missing: list[tuple[str, str]] = []
    for pip_name, import_name in [
        ("pystray", "pystray"),
        ("Pillow",  "PIL"),
        ("psutil",  "psutil"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append((pip_name, import_name))

    if sys.platform == "win32":
        try:
            import win32service  # noqa: F401
        except ImportError:
            missing.append(("pywin32", "win32service"))

    if missing:
        pkgs = " ".join(p for p, _ in missing)
        names = ", ".join(p for p, _ in missing)
        raise StartupError(
            f"Missing required packages: {names}\n\n"
            f"Install with:\n  pip install {pkgs}"
        )


def check_tkinter() -> None:
    """tkinter is stdlib but absent on minimal Linux installs."""
    try:
        import tkinter  # noqa: F401
    except ImportError:
        raise StartupError(
            "tkinter is not installed (required for the resource monitor dialog).\n\n"
            "Install:\n"
            "  sudo apt install python3-tk       # Debian / Ubuntu\n"
            "  sudo dnf install python3-tkinter  # Fedora\n"
            "  sudo pacman -S tk                 # Arch"
        )


def check_pystray_backend() -> None:
    """On Linux, verify python-gobject (gi) is available for the tray backend."""
    if sys.platform == "win32":
        return
    try:
        import gi  # noqa: F401
    except ImportError:
        raise StartupError(
            "python-gi (PyGObject) is required for system tray support.\n\n"
            "Install:\n"
            "  sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1  # Debian/Ubuntu\n"
            "  sudo dnf install python3-gobject libayatana-appindicator-gtk3  # Fedora\n"
            "  sudo pacman -S python-gobject libayatana-appindicator          # Arch"
        )


# ── non-fatal checks ──────────────────────────────────────────────────────────

def _show_download_prompt(download_url: str) -> None:
    """
    Tkinter dialog shown when Ollama is not found.
    Offers a Download button (opens browser) and a Continue button.
    Tray starts either way — user can install Ollama and restart.
    Only call this after check_tkinter() has confirmed tkinter is available.
    """
    import tkinter as tk
    import webbrowser

    root = tk.Tk()
    root.title("Ollama Not Found")
    root.resizable(False, False)
    root.configure(bg="#1e1e2e")
    root.attributes("-topmost", True)

    # Centre on screen
    root.update_idletasks()
    w, h = 420, 210
    x = (root.winfo_screenwidth()  - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Header bar
    tk.Label(
        root, text="  Ollama Not Found",
        bg="#313244", fg="#cdd6f4",
        font=("Segoe UI" if sys.platform == "win32" else "Noto Sans", 11, "bold"),
        anchor="w", padx=8, pady=7,
    ).pack(fill="x")

    # Body
    body = tk.Frame(root, bg="#1e1e2e", padx=20, pady=14)
    body.pack(fill="both", expand=True)

    tk.Label(
        body,
        text=(
            "Ollama is not installed or was not found in PATH.\n\n"
            "Service controls will be unavailable.\n"
            "You can install Ollama and restart the tray at any time."
        ),
        bg="#1e1e2e", fg="#cdd6f4",
        font=("Segoe UI" if sys.platform == "win32" else "Noto Sans", 10),
        justify="left", anchor="w",
        wraplength=380,
    ).pack(fill="x")

    # Button row
    btn_frame = tk.Frame(root, bg="#1e1e2e", pady=12)
    btn_frame.pack(fill="x", padx=20)

    def _download() -> None:
        webbrowser.open(download_url)
        root.destroy()

    def _continue() -> None:
        root.destroy()

    tk.Button(
        btn_frame, text="Download Ollama",
        command=_download,
        bg="#89b4fa", fg="#1e1e2e",
        font=("Segoe UI" if sys.platform == "win32" else "Noto Sans", 10, "bold"),
        relief="flat", padx=14, pady=5, cursor="hand2",
        activebackground="#74c7ec", activeforeground="#1e1e2e",
    ).pack(side="left", padx=(0, 10))

    tk.Button(
        btn_frame, text="Continue without Ollama",
        command=_continue,
        bg="#313244", fg="#cdd6f4",
        font=("Segoe UI" if sys.platform == "win32" else "Noto Sans", 10),
        relief="flat", padx=14, pady=5, cursor="hand2",
        activebackground="#45475a", activeforeground="#cdd6f4",
    ).pack(side="left")

    root.protocol("WM_DELETE_WINDOW", _continue)
    root.mainloop()


def check_ollama_binary(gui: bool = True) -> bool:
    """
    Prompt to download Ollama if binary not found (GUI mode) or warn to stderr
    (CLI mode). Returns True if found. Non-fatal either way.
    """
    if sys.platform == "win32":
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
            r"C:\Program Files\Ollama\ollama.exe",
        ]
        found = bool(shutil.which("ollama")) or any(os.path.exists(p) for p in candidates)
        download_url = "https://ollama.com/download/windows"
    else:
        candidates = [
            "/usr/local/bin/ollama",
            "/usr/bin/ollama",
            os.path.expanduser("~/.local/bin/ollama"),
        ]
        found = bool(shutil.which("ollama")) or any(os.path.exists(p) for p in candidates)
        download_url = "https://ollama.com/install.sh"

    if not found:
        if gui:
            _show_download_prompt(download_url)
        else:
            print(
                f"Warning: Ollama not found. Service controls unavailable.\n"
                f"Install: {download_url}",
                file=sys.stderr,
            )
    return found


def check_ollama_version() -> None:
    """
    Probe the running Ollama API for its version string.
    Non-fatal: warns if below minimum, silently skips if Ollama is not running.
    """
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/version", timeout=2) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return  # not running — expected at startup

    version_str = data.get("version", "")
    try:
        parts: tuple[int, ...] = tuple(
            int(x) for x in version_str.lstrip("v").split(".")[:3]
        )
    except (ValueError, AttributeError):
        return

    if len(parts) == 3 and parts < _MIN_OLLAMA:
        min_str = ".".join(map(str, _MIN_OLLAMA))
        _show_warning(
            "ollama-tray: outdated Ollama",
            f"Detected Ollama {version_str}; version {min_str}+ is recommended.\n"
            "Update: https://ollama.com/download",
        )


# ── orchestrator ──────────────────────────────────────────────────────────────

def run_startup_checks(gui: bool = True) -> None:
    """
    Execute all startup checks in order.

    gui=True  — tray mode: use native dialogs, check tkinter + tray backend
    gui=False — CLI mode:  stderr only, skip GUI-only checks
    """
    fatal: list[Callable[[], None]] = [
        check_python_version,
        check_imports,
    ]
    if gui:
        fatal += [check_tkinter, check_pystray_backend]

    for check in fatal:
        try:
            check()
        except StartupError as exc:
            msg = str(exc)
            if gui:
                _show_fatal("ollama-tray: startup error", msg)
            else:
                print(f"Error: {msg}", file=sys.stderr)
            sys.exit(1)

    # Non-fatal: prompt/warn and continue
    check_ollama_binary(gui=gui)
    check_ollama_version()
