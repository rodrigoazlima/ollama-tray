"""
setup.exe — self-contained installer for ollama-tray.
Copies bundled ollama-tray.exe to AppData, registers autostart, and launches it.
No Python installation required on the target machine.
"""
import os
import shutil
import subprocess
import sys
import time
import winreg
from pathlib import Path

_INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "OllamaTray"
_EXE_NAME    = "ollama-tray.exe"
_TASK_NAME   = "OllamaTray"
_CONFIG_DIR  = Path.home() / ".ollama-tray"
_CONFIG_NAME = "config.properties"


def _bundled_tray_exe() -> Path | None:
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / _EXE_NAME
        if p.exists():
            return p
    dev = Path(__file__).resolve().parent.parent / "dist" / _EXE_NAME
    if dev.exists():
        return dev
    return None


def _bundled_config() -> Path | None:
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / _CONFIG_NAME
        if p.exists():
            return p
    dev = Path(__file__).resolve().parent.parent / _CONFIG_NAME
    if dev.exists():
        return dev
    return None


def _install_config_if_absent() -> list[str]:
    """Copy bundled config.properties to ~/.ollama-tray/ only when none exists there."""
    msgs: list[str] = []
    dest = _CONFIG_DIR / _CONFIG_NAME
    if dest.exists():
        msgs.append(f"Config exists — keeping: {dest}")
        return msgs
    src = _bundled_config()
    if src is None:
        msgs.append("Warning: bundled config.properties not found — skipping.")
        return msgs
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        msgs.append(f"Config installed: {dest}")
    except Exception as e:
        msgs.append(f"Warning: could not install config: {e}")
    return msgs


def _uninstall_previous() -> list[str]:
    """Stop ollama-tray, ollama, and llama.cpp; remove existing installation."""
    msgs: list[str] = []
    for proc in (_EXE_NAME, "ollama.exe", "llama-server.exe", "llama.cpp"):
        result = subprocess.run(["taskkill", "/F", "/IM", proc], capture_output=True)
        if result.returncode == 0:
            msgs.append(f"Stopped: {proc}")
    time.sleep(0.5)
    dst = _INSTALL_DIR / _EXE_NAME
    if dst.exists():
        try:
            dst.unlink()
            msgs.append(f"Removed previous: {dst}")
        except Exception as e:
            msgs.append(f"Warning: could not remove previous exe: {e}")
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, _TASK_NAME)
        winreg.CloseKey(key)
        msgs.append(f"Removed autostart entry: {_TASK_NAME}")
    except FileNotFoundError:
        pass
    except Exception as e:
        msgs.append(f"Warning: autostart removal: {e}")
    return msgs


def _install(src: Path) -> Path:
    _INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    dst = _INSTALL_DIR / _EXE_NAME
    shutil.copy2(src, dst)
    return dst


def _register_autostart(exe: Path) -> None:
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, _TASK_NAME, 0, winreg.REG_SZ, f'"{exe}"')
    winreg.CloseKey(key)


def _launch(exe: Path) -> None:
    subprocess.Popen([str(exe)], close_fds=True)


def run_gui() -> None:
    import tkinter as tk

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

    w, h = 420, 260
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
                       font=("Consolas", 9), height=6, state="disabled", bd=0)
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

    def _do_install() -> None:
        btn.configure(state="disabled")
        root.update_idletasks()

        status_var.set("Uninstalling previous version...")
        root.update_idletasks()
        for msg in _uninstall_previous():
            _log(msg, DIM)

        status_var.set("Locating ollama-tray...")
        root.update_idletasks()
        src = _bundled_tray_exe()
        if src is None:
            _log("ERROR: ollama-tray.exe not found in bundle.", RED)
            status_var.set("Install failed — bundled exe missing.")
            btn.configure(state="normal", text="Retry")
            return
        _log(f"Found: {src}", DIM)

        status_var.set(f"Installing to {_INSTALL_DIR}...")
        root.update_idletasks()
        try:
            dst = _install(src)
            _log(f"Installed: {dst}", GREEN)
        except Exception as e:
            _log(f"Copy error: {e}", RED)
            status_var.set("Install failed.")
            btn.configure(state="normal", text="Retry")
            return

        status_var.set("Installing configuration...")
        root.update_idletasks()
        for msg in _install_config_if_absent():
            _log(msg, DIM)

        status_var.set("Registering autostart...")
        root.update_idletasks()
        try:
            _register_autostart(dst)
            _log(f"Autostart: HKCU\\Run\\{_TASK_NAME}", GREEN)
        except Exception as e:
            _log(f"Registry error: {e}", RED)
            status_var.set("Could not register autostart.")
            btn.configure(state="normal", text="Retry")
            return

        status_var.set("Starting OllamaTray...")
        root.update_idletasks()
        try:
            _launch(dst)
            _log("Tray launched.", GREEN)
        except Exception as e:
            _log(f"Launch error: {e}", RED)

        status_var.set("Done! OllamaTray is running — look for the icon in the system tray.")
        btn.configure(state="normal", text="Close", command=root.destroy,
                      bg="#a6e3a1", activebackground="#94e2d5")

    btn.configure(command=_do_install)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
