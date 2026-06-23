"""
Startup environment checks for ollama-tray.

Fatal checks (wrong Python, missing deps, no tray backend) call sys.exit(1)
after showing a platform-native error dialog or printing to stderr.

Non-fatal checks (Ollama not installed, not running, old version) warn / prompt
and continue — the tray still runs with limited functionality.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from typing import Callable

from ollama_tray.config import MIN_OLLAMA as _MIN_OLLAMA, OLLAMA_URL, SERVE_HOST, UI_COLOR as _COLOR

_MIN_PYTHON = (3, 10)

_FONT_UI   = "Segoe UI"   if sys.platform == "win32" else "Noto Sans"
_FONT_MONO = "Consolas"   if sys.platform == "win32" else "Hack"


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
        ("pystray",  "pystray"),
        ("Pillow",   "PIL"),
        ("psutil",   "psutil"),
        ("watchdog", "watchdog"),
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
        pkgs  = " ".join(p for p, _ in missing)
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


# ── ollama binary / download prompt ──────────────────────────────────────────

def _show_download_prompt(download_url: str) -> None:
    """
    Tkinter dialog: Ollama binary not found.
    Download button opens browser. Either way the tray starts.
    Only call after check_tkinter() has passed.
    """
    import tkinter as tk
    import webbrowser

    root = tk.Tk()
    root.title("Ollama Not Found")
    root.resizable(False, False)
    root.configure(bg=_COLOR["bg"])
    root.attributes("-topmost", True)

    w, h = 420, 210
    root.update_idletasks()
    x = (root.winfo_screenwidth()  - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(
        root, text="  Ollama Not Found",
        bg=_COLOR["surface"], fg=_COLOR["fg"],
        font=(_FONT_UI, 11, "bold"),
        anchor="w", padx=8, pady=7,
    ).pack(fill="x")

    body = tk.Frame(root, bg=_COLOR["bg"], padx=20, pady=14)
    body.pack(fill="both", expand=True)

    tk.Label(
        body,
        text=(
            "Ollama is not installed or was not found in PATH.\n\n"
            "Service controls will be unavailable.\n"
            "Install Ollama and restart the tray at any time."
        ),
        bg=_COLOR["bg"], fg=_COLOR["fg"],
        font=(_FONT_UI, 10),
        justify="left", anchor="w", wraplength=380,
    ).pack(fill="x")

    btn_frame = tk.Frame(root, bg=_COLOR["bg"], pady=12)
    btn_frame.pack(fill="x", padx=20)

    def _download() -> None:
        webbrowser.open(download_url)
        root.destroy()

    tk.Button(
        btn_frame, text="Download Ollama",
        command=_download,
        bg=_COLOR["blue"], fg=_COLOR["bg"],
        font=(_FONT_UI, 10, "bold"),
        relief="flat", padx=14, pady=5, cursor="hand2",
        activebackground=_COLOR["blue_act"], activeforeground=_COLOR["bg"],
    ).pack(side="left", padx=(0, 10))

    tk.Button(
        btn_frame, text="Continue without Ollama",
        command=root.destroy,
        bg=_COLOR["surface"], fg=_COLOR["fg"],
        font=(_FONT_UI, 10),
        relief="flat", padx=14, pady=5, cursor="hand2",
        activebackground=_COLOR["surface1"], activeforeground=_COLOR["fg"],
    ).pack(side="left")

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


def check_ollama_binary(gui: bool = True) -> bool:
    """
    Returns True if the Ollama binary is found.
    In GUI mode shows a download prompt when missing. Non-fatal either way.
    """
    if sys.platform == "win32":
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
            r"C:\Program Files\Ollama\ollama.exe",
        ]
        download_url = "https://ollama.com/download/windows"
    else:
        candidates = [
            "/usr/local/bin/ollama",
            "/usr/bin/ollama",
            os.path.expanduser("~/.local/bin/ollama"),
        ]
        download_url = "https://ollama.com/install.sh"

    found = bool(shutil.which("ollama")) or any(os.path.exists(p) for p in candidates)

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


# ── ollama start dialog ───────────────────────────────────────────────────────

def _is_ollama_running() -> bool:
    """True if the Ollama HTTP server responds at OLLAMA_URL."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/version", timeout=2):
            return True
    except Exception:
        return False


def _get_ollama_models() -> list[str]:
    """Return model names from `ollama list`. Empty list on any failure."""
    try:
        r = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=5,
        )
        lines = r.stdout.strip().splitlines()
        return [ln.split()[0] for ln in lines[1:] if ln.strip()]
    except Exception:
        return []


def _launch_ollama(host: str, extra_env_text: str, preload_model: str) -> None:
    """
    Start `ollama serve` as a detached subprocess.
    If preload_model is given, sends a keep-alive load request after 3 s.
    """
    env = os.environ.copy()
    if host:
        env["OLLAMA_HOST"] = host

    for line in extra_env_text.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()

    kwargs: dict = {"env": env}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen(["ollama", "serve"], **kwargs)

    if preload_model:
        # resolve the port from host field so we can call the right endpoint
        port = host.split(":")[-1] if ":" in host else "11434"
        api_url = f"http://127.0.0.1:{port}/api/generate"

        def _preload() -> None:
            import time
            time.sleep(3)
            try:
                payload = json.dumps({"model": preload_model, "keep_alive": -1}).encode()
                req = urllib.request.Request(
                    api_url, data=payload,
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=30)
            except Exception:
                pass

        threading.Thread(target=_preload, daemon=True).start()


def _show_ollama_start_dialog() -> None:
    """
    Tkinter dialog: Ollama binary present but server not running.
    User can configure host, pick a model to preload, add env vars,
    then click Start to launch `ollama serve` locally.
    Only call after check_tkinter() has passed.
    """
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Start Ollama")
    root.resizable(False, False)
    root.configure(bg=_COLOR["bg"])
    root.attributes("-topmost", True)

    w, h = 480, 390
    root.update_idletasks()
    x = (root.winfo_screenwidth()  - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # ── header ────────────────────────────────────────────────────────────────
    tk.Label(
        root, text="  Ollama is Not Running",
        bg=_COLOR["surface"], fg=_COLOR["fg"],
        font=(_FONT_UI, 11, "bold"),
        anchor="w", padx=8, pady=7,
    ).pack(fill="x")

    tk.Label(
        root,
        text="  Configure and start Ollama locally, or continue with limited functionality.",
        bg=_COLOR["bg"], fg=_COLOR["dim"],
        font=(_FONT_UI, 9),
        anchor="w", padx=8, pady=3,
    ).pack(fill="x")

    body = tk.Frame(root, bg=_COLOR["bg"], padx=20, pady=10)
    body.pack(fill="both", expand=True)

    # ── helper: labelled row ──────────────────────────────────────────────────
    def _label_row(text: str, hint: str = "") -> tk.Frame:
        f = tk.Frame(body, bg=_COLOR["bg"])
        f.pack(fill="x", pady=(6, 0))
        tk.Label(
            f, text=text,
            bg=_COLOR["bg"], fg=_COLOR["subtext"],
            font=(_FONT_UI, 9, "bold"), anchor="w",
        ).pack(side="left")
        if hint:
            tk.Label(
                f, text=hint,
                bg=_COLOR["bg"], fg=_COLOR["overlay0"],
                font=(_FONT_UI, 8), anchor="w",
            ).pack(side="left", padx=(6, 0))
        return f

    # ── host ──────────────────────────────────────────────────────────────────
    _label_row("Host", "→ OLLAMA_HOST")
    host_var = tk.StringVar(value=SERVE_HOST)
    tk.Entry(
        body, textvariable=host_var,
        bg=_COLOR["surface"], fg=_COLOR["fg"], insertbackground=_COLOR["fg"],
        relief="flat", font=(_FONT_MONO, 10), width=36,
    ).pack(fill="x", ipady=4, pady=(3, 0))

    # ── model ─────────────────────────────────────────────────────────────────
    model_row = _label_row("Model to preload", "  (optional — loads into memory after start)")
    model_var = tk.StringVar(value="(none)")

    style = ttk.Style()
    style.theme_use("default")
    style.configure(
        "Dark.TCombobox",
        fieldbackground=_COLOR["surface"],
        background=_COLOR["surface"],
        foreground=_COLOR["fg"],
        selectbackground=_COLOR["surface1"],
        selectforeground=_COLOR["fg"],
    )

    combo = ttk.Combobox(
        body, textvariable=model_var,
        style="Dark.TCombobox",
        state="readonly", font=(_FONT_MONO, 10),
    )
    combo.pack(fill="x", ipady=3, pady=(3, 0))

    status_var = tk.StringVar(value="")
    status_lbl = tk.Label(
        body, textvariable=status_var,
        bg=_COLOR["bg"], fg=_COLOR["dim"],
        font=(_FONT_UI, 8), anchor="w",
    )
    status_lbl.pack(fill="x")

    def _refresh_models() -> None:
        status_var.set("Fetching models…")
        root.update_idletasks()

        def _fetch() -> None:
            models = _get_ollama_models()
            values = ["(none)"] + models
            combo["values"] = values
            if not combo.get() or combo.get() not in values:
                combo.set("(none)")
            if models:
                status_var.set(f"{len(models)} model(s) found")
            else:
                status_var.set("No models installed — run 'ollama pull <model>'")

        threading.Thread(target=_fetch, daemon=True).start()

    ref_btn = tk.Button(
        model_row, text="↻ Refresh",
        command=_refresh_models,
        bg=_COLOR["surface1"], fg=_COLOR["fg"],
        relief="flat", font=(_FONT_UI, 8), padx=6, pady=1,
        cursor="hand2",
        activebackground=_COLOR["overlay0"], activeforeground=_COLOR["fg"],
    )
    ref_btn.pack(side="right")

    _refresh_models()

    # ── extra env vars ────────────────────────────────────────────────────────
    _label_row("Environment variables", "  one KEY=VALUE per line")
    env_text = tk.Text(
        body,
        height=4,
        bg=_COLOR["surface"], fg=_COLOR["fg"], insertbackground=_COLOR["fg"],
        relief="flat", font=(_FONT_MONO, 9),
        wrap="none",
    )
    env_text.pack(fill="x", ipady=5, pady=(3, 0))

    examples = [
        "# OLLAMA_NUM_PARALLEL=4",
        "# OLLAMA_MAX_LOADED_MODELS=2",
        "# OLLAMA_DEBUG=1",
        "# OLLAMA_ORIGINS=*",
    ]
    env_text.insert("1.0", "\n".join(examples))
    env_text.configure(fg=_COLOR["surface1"])  # dim placeholder

    def _clear_placeholder(event: object) -> None:
        if env_text.get("1.0", "end").strip() == "\n".join(examples):
            env_text.delete("1.0", "end")
            env_text.configure(fg=_COLOR["fg"])

    env_text.bind("<FocusIn>", _clear_placeholder)

    # ── buttons ───────────────────────────────────────────────────────────────
    btn_frame = tk.Frame(root, bg=_COLOR["bg_dark"], pady=12, padx=20)
    btn_frame.pack(fill="x")

    def _start() -> None:
        host  = host_var.get().strip() or "127.0.0.1:11434"
        model = model_var.get().strip()
        if model == "(none)":
            model = ""
        raw_env = env_text.get("1.0", "end")
        if raw_env.strip() == "\n".join(examples):
            raw_env = ""
        root.destroy()
        _launch_ollama(host, raw_env, model)

    def _skip() -> None:
        root.destroy()

    tk.Button(
        btn_frame, text="▶  Start Ollama",
        command=_start,
        bg=_COLOR["green"], fg=_COLOR["bg"],
        font=(_FONT_UI, 10, "bold"),
        relief="flat", padx=16, pady=6, cursor="hand2",
        activebackground=_COLOR["green_act"], activeforeground=_COLOR["bg"],
    ).pack(side="left", padx=(0, 10))

    tk.Button(
        btn_frame, text="Continue without starting",
        command=_skip,
        bg=_COLOR["surface"], fg=_COLOR["fg"],
        font=(_FONT_UI, 10),
        relief="flat", padx=14, pady=6, cursor="hand2",
        activebackground=_COLOR["surface1"], activeforeground=_COLOR["fg"],
    ).pack(side="left")

    root.protocol("WM_DELETE_WINDOW", _skip)
    root.mainloop()


def check_ollama_running(gui: bool = True) -> None:
    """
    Show start dialog (GUI) or warn to stderr (CLI) when the Ollama server is
    not responding. Non-fatal — tray starts regardless.
    Only relevant when the Ollama binary was already confirmed present.
    """
    if _is_ollama_running():
        return
    if gui:
        _show_ollama_start_dialog()
    else:
        print(
            f"Warning: Ollama server not reachable at {OLLAMA_URL}.\n"
            "Start with:  ollama serve",
            file=sys.stderr,
        )


# ── version check ─────────────────────────────────────────────────────────────

def check_ollama_version() -> None:
    """
    Probe the running Ollama API for its version string.
    Non-fatal: warns if below minimum, silently skips if Ollama is not running.
    """
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/version", timeout=2) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return

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

    # Non-fatal: prompt / warn and continue
    ollama_found = check_ollama_binary(gui=gui)
    if ollama_found:
        check_ollama_running(gui=gui)
    check_ollama_version()
