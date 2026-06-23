"""
setup.exe — GUI installer for ollama-tray.
Finds the system Python, installs dependencies, registers autostart, launches tray.
"""
import os
import subprocess
import sys
import winreg
from pathlib import Path

_TASK_NAME = "OllamaTray"

def _requirements_path() -> Path | None:
    # When frozen, PyInstaller extracts datas into sys._MEIPASS — check there first.
    if getattr(sys, "frozen", False):
        bundled = Path(sys._MEIPASS) / "requirements.txt"
        if bundled.exists():
            return bundled
    # Source layout: repo root is two levels above windows/setup_installer.py
    for candidate in [
        Path(__file__).parent.parent,
        Path(sys.executable).parent,
        Path(sys.executable).parent.parent,
    ]:
        p = candidate / "requirements.txt"
        if p.exists():
            return p
    return None


def _find_python() -> str | None:
    for name in ("python", "python3", "py"):
        try:
            r = subprocess.run(
                [name, "-c", "import sys; print(sys.executable)"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                path = r.stdout.strip()
                if path and Path(path).exists():
                    return path
        except Exception:
            continue
    return None


def _install_deps(python: str, req: Path) -> tuple[bool, str]:
    r = subprocess.run(
        [python, "-m", "pip", "install", "-r", str(req), "--quiet"],
        capture_output=True, text=True,
    )
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def _register_autostart(python: str) -> None:
    cmd = f'"{python}" -m ollama_tray'
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, _TASK_NAME, 0, winreg.REG_SZ, cmd)
    winreg.CloseKey(key)


def _launch_tray(python: str) -> None:
    # Kill any running instance first
    subprocess.run(
        ["taskkill", "/F", "/IM", "python.exe", "/FI", f"WINDOWTITLE eq ollama_tray"],
        capture_output=True,
    )
    subprocess.Popen([python, "-m", "ollama_tray"], close_fds=True)


def run_gui() -> None:
    import tkinter as tk
    from tkinter import font as tkfont

    UI_FONT = "Segoe UI"
    BG      = "#1e1e2e"
    FG      = "#cdd6f4"
    DIM     = "#6c7086"
    SURFACE = "#313244"
    GREEN   = "#a6e3a1"
    RED     = "#f38ba8"
    BLUE    = "#89b4fa"

    root = tk.Tk()
    root.title("OllamaTray Setup")
    root.resizable(False, False)
    root.configure(bg=BG)
    root.attributes("-topmost", True)

    w, h = 420, 300
    root.update_idletasks()
    x = (root.winfo_screenwidth()  - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(root, text="  OllamaTray — Setup",
             bg=SURFACE, fg=FG, font=(UI_FONT, 12, "bold"),
             anchor="w", padx=8, pady=8).pack(fill="x")

    body = tk.Frame(root, bg=BG, padx=20, pady=12)
    body.pack(fill="both", expand=True)

    status_var = tk.StringVar(value="Ready to install.")
    tk.Label(body, textvariable=status_var, bg=BG, fg=DIM,
             font=(UI_FONT, 9), anchor="w", wraplength=360).pack(fill="x", pady=(0, 10))

    log_text = tk.Text(body, bg=SURFACE, fg=FG, relief="flat",
                       font=("Consolas", 9), height=7, state="disabled", bd=0)
    log_text.pack(fill="x")

    footer = tk.Frame(root, bg="#181825", pady=10, padx=20)
    footer.pack(fill="x")

    btn = tk.Button(footer, text="Install",
                    bg=BLUE, fg=BG, font=(UI_FONT, 10, "bold"),
                    relief="flat", padx=16, pady=5, cursor="hand2",
                    activebackground="#74c7ec", activeforeground=BG)
    btn.pack(side="left")

    def _log(msg: str, color: str = FG) -> None:
        log_text.configure(state="normal")
        log_text.tag_configure(color, foreground=color)
        log_text.insert("end", msg + "\n", color)
        log_text.see("end")
        log_text.configure(state="disabled")
        root.update_idletasks()

    def _install() -> None:
        btn.configure(state="disabled")
        root.update_idletasks()

        status_var.set("Locating Python...")
        root.update_idletasks()
        python = _find_python()
        if not python:
            _log("ERROR: Python not found in PATH.", RED)
            status_var.set("Python not found. Install Python 3.10+ and retry.")
            btn.configure(state="normal", text="Retry")
            return
        _log(f"Python: {python}", DIM)

        req = _requirements_path()
        if req is None:
            _log("ERROR: requirements.txt not found (checked bundle + exe dir).", RED)
            status_var.set("requirements.txt not found.")
            btn.configure(state="normal", text="Retry")
            return

        status_var.set("Installing dependencies...")
        root.update_idletasks()
        ok, err = _install_deps(python, req)
        if not ok:
            _log(f"pip error: {err[:200]}", RED)
            status_var.set("Dependency install failed.")
            btn.configure(state="normal", text="Retry")
            return
        _log("Dependencies installed.", GREEN)

        status_var.set("Registering autostart...")
        root.update_idletasks()
        try:
            _register_autostart(python)
            _log(f"Autostart registered (HKCU\\Run\\{_TASK_NAME}).", GREEN)
        except Exception as e:
            _log(f"Registry error: {e}", RED)
            status_var.set("Could not register autostart.")
            btn.configure(state="normal", text="Retry")
            return

        status_var.set("Starting OllamaTray...")
        root.update_idletasks()
        try:
            _launch_tray(python)
            _log("Tray launched.", GREEN)
        except Exception as e:
            _log(f"Launch error: {e}", RED)

        status_var.set("Installation complete. Tray icon is now active.")
        btn.configure(state="normal", text="Close", command=root.destroy,
                      bg="#a6e3a1", activebackground="#94e2d5")

    btn.configure(command=_install)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
