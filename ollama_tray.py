"""
ollama_tray.py — Ollama system tray manager for Windows.

Tray icon: green dot = running, red = stopped, amber = transitioning.
Right-click menu: service control + live CPU/RAM summary (updates every second).
Double-click: toggle resource-monitor dialog (debounced — 600 ms min between toggles).

CLI flags:
  --start      Start the Ollama service
  --stop       Stop the Ollama service
  --restart    Restart the Ollama service
  --status     Print current service status
  --install    Register tray to auto-launch at logon (HKCU Run key)
  --uninstall  Remove logon autostart
"""

import argparse
import ctypes
import os
import sys
import threading
import time
import tkinter as tk
import webbrowser
import winreg
from datetime import datetime, timedelta

import psutil
import pystray
import pywintypes
import win32service
from pystray import MenuItem as item, Menu
from PIL import Image, ImageDraw, ImageFont

# ── constants ────────────────────────────────────────────────────────────────

SERVICE_NAME       = "Ollama"
OLLAMA_URL         = "http://localhost:11434"
TASK_NAME          = "OllamaTray"
ICON_SIZE          = 64
STATS_INTERVAL     = 1    # seconds — resource stats + menu refresh
STATUS_INTERVAL    = 5    # ticks  — service status re-check (every 5 s)
TOGGLE_DEBOUNCE_S  = 0.6  # seconds — min gap between open/close dialog

OLLAMA_ICO = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Programs", "Ollama", "app.ico",
)

STATUS_COLOR = {
    "running":  (72,  199, 116),   # green
    "stopped":  (220,  53,  69),   # red
    "starting": (255, 193,   7),   # amber
    "stopping": (255, 193,   7),
    "unknown":  (255, 193,   7),
}

# ── icon ─────────────────────────────────────────────────────────────────────

def _base_image() -> Image.Image:
    if os.path.exists(OLLAMA_ICO):
        img = Image.open(OLLAMA_ICO).convert("RGBA")
        return img.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, ICON_SIZE - 2, ICON_SIZE - 2], fill=(30, 30, 30, 230))
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except Exception:
        font = ImageFont.load_default()
    draw.text((18, 14), "O", fill=(200, 200, 200), font=font)
    return img


_base: Image.Image | None = None


def make_icon(status: str) -> Image.Image:
    global _base
    if _base is None:
        _base = _base_image()
    img = _base.copy()
    draw = ImageDraw.Draw(img)
    r = 10
    x0, y0 = ICON_SIZE - r * 2 - 2, ICON_SIZE - r * 2 - 2
    color = STATUS_COLOR.get(status, STATUS_COLOR["unknown"])
    draw.ellipse([x0 - 1, y0 - 1, x0 + r * 2 + 1, y0 + r * 2 + 1], fill=(0, 0, 0, 180))
    draw.ellipse([x0, y0, x0 + r * 2, y0 + r * 2], fill=color + (255,))
    return img


# ── service control (win32service — zero subprocesses, zero CMD flashes) ─────

def _scm(access: int = win32service.SC_MANAGER_CONNECT):
    return win32service.OpenSCManager(None, None, access)


def _svc(hscm, access: int):
    return win32service.OpenService(hscm, SERVICE_NAME, access)


def get_status() -> str:
    try:
        hscm = _scm()
        hsvc = _svc(hscm, win32service.SERVICE_QUERY_STATUS)
        try:
            state = win32service.QueryServiceStatus(hsvc)[1]
        finally:
            win32service.CloseServiceHandle(hsvc)
            win32service.CloseServiceHandle(hscm)
        return {
            win32service.SERVICE_RUNNING:          "running",
            win32service.SERVICE_STOPPED:          "stopped",
            win32service.SERVICE_START_PENDING:    "starting",
            win32service.SERVICE_CONTINUE_PENDING: "starting",
            win32service.SERVICE_STOP_PENDING:     "stopping",
            win32service.SERVICE_PAUSE_PENDING:    "stopping",
        }.get(state, "unknown")
    except Exception:
        return "unknown"


def _svc_start() -> None:
    hscm = _scm(win32service.SC_MANAGER_CONNECT)
    hsvc = _svc(hscm, win32service.SERVICE_START)
    try:
        win32service.StartService(hsvc, None)
    finally:
        win32service.CloseServiceHandle(hsvc)
        win32service.CloseServiceHandle(hscm)


def _svc_stop() -> None:
    hscm = _scm(win32service.SC_MANAGER_CONNECT)
    hsvc = _svc(hscm, win32service.SERVICE_STOP)
    try:
        win32service.ControlService(hsvc, win32service.SERVICE_CONTROL_STOP)
    finally:
        win32service.CloseServiceHandle(hsvc)
        win32service.CloseServiceHandle(hscm)


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate(action: str) -> None:
    """Re-launch with UAC elevation for the given CLI action."""
    exe = sys.executable
    if getattr(sys, "frozen", False):
        # PyInstaller exe: sys.executable IS the exe, no script arg needed
        args = f"--{action}"
    else:
        script = os.path.abspath(__file__)
        args   = f'"{script}" --{action}'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 0)


def _service_action(action: str) -> None:
    """Start or stop service; auto-elevates via UAC if access denied."""
    try:
        if action == "start":
            _svc_start()
        elif action == "stop":
            _svc_stop()
    except pywintypes.error as e:
        if e.args[0] == 5:   # ERROR_ACCESS_DENIED
            _elevate(action)
        # other errors (e.g. already running/stopped) are silently swallowed


# ── resource stats (psutil) ──────────────────────────────────────────────────

def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_uptime(create_time: float) -> str:
    delta = timedelta(seconds=int(time.time() - create_time))
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s   = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


class OllamaStats:
    cpu_pct:   float = 0.0
    mem_rss:   int   = 0
    mem_vms:   int   = 0
    threads:   int   = 0
    handles:   int   = 0
    num_procs: int   = 0
    uptime:    str   = "—"
    procs:     list  = []

    def is_empty(self) -> bool:
        return self.num_procs == 0


_stats_lock    = threading.Lock()
_current_stats = OllamaStats()
_proc_handles: dict[int, psutil.Process] = {}


def refresh_stats() -> OllamaStats:
    global _proc_handles, _current_stats

    live = [
        p for p in psutil.process_iter(["name", "pid"])
        if "ollama" in (p.info.get("name") or "").lower()
    ]
    live_pids = {p.pid for p in live}
    _proc_handles = {pid: h for pid, h in _proc_handles.items() if pid in live_pids}

    for p in live:
        if p.pid not in _proc_handles:
            try:
                p.cpu_percent(interval=None)
                _proc_handles[p.pid] = p
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    s = OllamaStats()
    s.procs = []
    earliest = None

    for pid, p in list(_proc_handles.items()):
        try:
            with p.oneshot():
                cpu  = p.cpu_percent(interval=None)
                mi   = p.memory_info()
                thr  = p.num_threads()
                hdl  = p.num_handles() if hasattr(p, "num_handles") else 0
                ct   = p.create_time()
                name = p.name()
            s.cpu_pct  += cpu
            s.mem_rss  += mi.rss
            s.mem_vms  += mi.vms
            s.threads  += thr
            s.handles  += hdl
            s.num_procs += 1
            if earliest is None or ct < earliest:
                earliest = ct
            s.procs.append({"name": name, "pid": pid, "cpu": cpu,
                             "rss": mi.rss, "vms": mi.vms, "thr": thr})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            _proc_handles.pop(pid, None)

    if earliest:
        s.uptime = _fmt_uptime(earliest)

    with _stats_lock:
        _current_stats = s
    return s


def current_stats() -> OllamaStats:
    with _stats_lock:
        return _current_stats


# ── resource dialog (tkinter) ─────────────────────────────────────────────────

_dialog_lock        = threading.Lock()
_dialog_open        = False
_dialog_root: tk.Tk | None = None
_last_toggle_time   = 0.0


def _set_dialog_closed() -> None:
    global _dialog_open, _dialog_root
    _dialog_open = False
    _dialog_root = None


def _open_resource_dialog() -> None:
    global _dialog_open, _dialog_root, _last_toggle_time

    with _dialog_lock:
        now = time.monotonic()
        # debounce: ignore if called too soon after previous toggle
        if now - _last_toggle_time < TOGGLE_DEBOUNCE_S:
            return
        _last_toggle_time = now

        if _dialog_open:
            # second toggle → close
            if _dialog_root is not None:
                try:
                    _dialog_root.after(0, _dialog_root.destroy)
                except Exception:
                    pass
            return
        _dialog_open = True

    # open in its own thread (tkinter needs its own mainloop)
    threading.Thread(target=_run_dialog, daemon=True).start()


def _run_dialog() -> None:
    try:
        root = tk.Tk()
        with _dialog_lock:
            global _dialog_root
            _dialog_root = root

        root.title("Ollama Resource Monitor")
        root.resizable(False, False)
        root.configure(bg="#1e1e2e")
        if os.path.exists(OLLAMA_ICO):
            root.iconbitmap(OLLAMA_ICO)

        # header
        tk.Label(
            root, text="  Ollama Resource Monitor",
            bg="#313244", fg="#cdd6f4",
            font=("Segoe UI", 11, "bold"),
            anchor="w", padx=8, pady=6,
        ).pack(fill="x")

        # text area
        frame = tk.Frame(root, bg="#1e1e2e")
        frame.pack(fill="both", expand=True, padx=12, pady=8)

        txt = tk.Text(
            frame,
            font=("Consolas", 10),
            bg="#1e1e2e", fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat", bd=0,
            width=52, height=14,
            state="disabled",
        )
        txt.pack(fill="both", expand=True)

        txt.tag_configure("header", foreground="#89b4fa", font=("Consolas", 10, "bold"))
        txt.tag_configure("good",   foreground="#a6e3a1")
        txt.tag_configure("warn",   foreground="#f9e2af")
        txt.tag_configure("bad",    foreground="#f38ba8")
        txt.tag_configure("dim",    foreground="#6c7086")
        txt.tag_configure("sep",    foreground="#313244")

        # footer
        footer = tk.Label(
            root, text="",
            bg="#181825", fg="#6c7086",
            font=("Consolas", 9), anchor="w", padx=8, pady=4,
        )
        footer.pack(fill="x")

        def _cpu_tag(pct):  return "good" if pct < 30 else "warn" if pct < 70 else "bad"
        def _mem_tag(mb):   return "good" if mb < 2048 else "warn" if mb < 6144 else "bad"

        def _update():
            s = refresh_stats()
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            sep = "─" * 50 + "\n"

            if s.is_empty():
                txt.insert("end", "\n  No Ollama processes found.\n\n", "dim")
                txt.insert("end", "  Service may be stopped.\n", "dim")
            else:
                txt.insert("end",
                    f"  {'Process':<22} {'PID':>6}  {'CPU%':>6}  {'RSS':>9}\n", "header")
                txt.insert("end", "  " + sep, "sep")

                for p in s.procs:
                    rss_mb = p["rss"] / 1024 ** 2
                    txt.insert("end",
                        f"  {p['name']:<22} {p['pid']:>6}  {p['cpu']:>5.1f}%  {rss_mb:>7.1f} MB\n",
                        _cpu_tag(p["cpu"]))

                if s.num_procs > 1:
                    txt.insert("end", "  " + sep, "sep")
                    txt.insert("end",
                        f"  {'TOTAL':<22} {'':>6}  {s.cpu_pct:>5.1f}%  "
                        f"{s.mem_rss/1024**2:>7.1f} MB\n", "header")

                txt.insert("end", "\n  " + sep, "sep")

                for label, val, tag in [
                    ("CPU (total)",  f"{s.cpu_pct:.1f}%",         _cpu_tag(s.cpu_pct)),
                    ("RAM  RSS",     _fmt_bytes(s.mem_rss),        _mem_tag(s.mem_rss/1024**2)),
                    ("RAM  VMS",     _fmt_bytes(s.mem_vms),        "dim"),
                    ("Threads",      str(s.threads),               "good"),
                    ("Handles",      str(s.handles) or "—",        "dim"),
                    ("Processes",    str(s.num_procs),             "dim"),
                    ("Uptime",       s.uptime,                     "dim"),
                ]:
                    txt.insert("end", f"  {label:<16}", "dim")
                    txt.insert("end", f"  {val}\n", tag)

            txt.configure(state="disabled")
            footer.configure(
                text=f"  Updated {datetime.now().strftime('%H:%M:%S')}   · 1 s refresh"
            )
            root.after(1000, _update)

        _update()
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
    finally:
        _set_dialog_closed()


# ── tray application ──────────────────────────────────────────────────────────

class OllamaTray:
    def __init__(self):
        self._status = "unknown"
        self._icon: pystray.Icon | None = None
        self._lock  = threading.Lock()
        self._tick  = 0

    def _stats_label(self, _=None) -> str:
        s = current_stats()
        if s.is_empty():
            return "  Usage: no process"
        return f"  CPU {s.cpu_pct:.1f}%  ·  RAM {_fmt_bytes(s.mem_rss)}"

    def _start(self, *_):
        threading.Thread(target=_service_action, args=("start",), daemon=True).start()

    def _stop(self, *_):
        threading.Thread(target=_service_action, args=("stop",), daemon=True).start()

    def _restart(self, *_):
        def _do():
            _service_action("stop")
            time.sleep(3)
            _service_action("start")
        threading.Thread(target=_do, daemon=True).start()

    def _open_browser(self, *_):
        webbrowser.open(OLLAMA_URL)

    def _toggle_dialog(self, *_):
        _open_resource_dialog()

    def _exit(self, *_):
        if self._icon:
            self._icon.stop()

    def _poll(self):
        while True:
            time.sleep(STATS_INTERVAL)
            self._tick += 1

            refresh_stats()

            if self._tick % STATUS_INTERVAL == 0:
                new = get_status()
                with self._lock:
                    if new != self._status:
                        self._status = new
                        if self._icon:
                            self._icon.icon  = make_icon(new)
                            self._icon.title = f"Ollama — {new.capitalize()}"

            if self._icon:
                try:
                    self._icon.update_menu()
                except Exception:
                    pass

    def run(self):
        self._status = get_status()
        refresh_stats()

        menu = Menu(
            item(self._stats_label, self._toggle_dialog, default=True),
            Menu.SEPARATOR,
            item("Start Service",   self._start),
            item("Stop Service",    self._stop),
            item("Restart Service", self._restart),
            Menu.SEPARATOR,
            item("Open in Browser", self._open_browser),
            Menu.SEPARATOR,
            item("Exit",            self._exit),
        )
        self._icon = pystray.Icon(
            "ollama",
            make_icon(self._status),
            f"Ollama — {self._status.capitalize()}",
            menu=menu,
        )
        threading.Thread(target=self._poll, daemon=True).start()
        self._icon.run()


# ── CLI helpers ───────────────────────────────────────────────────────────────

def cli_start() -> int:
    try:
        _svc_start()
        print(f"Service '{SERVICE_NAME}' started.")
        return 0
    except pywintypes.error as e:
        print(f"Error: {e}")
        return 1

def cli_stop() -> int:
    try:
        _svc_stop()
        print(f"Service '{SERVICE_NAME}' stopped.")
        return 0
    except pywintypes.error as e:
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
    print(f"Ollama service: {st}")
    return 0 if st == "running" else 1

def cli_install() -> int:
    script = os.path.abspath(__file__)
    exe    = sys.executable
    if getattr(sys, "frozen", False):
        value = f'"{exe}"'
    else:
        value = f'"{exe}" "{script}"'
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, TASK_NAME, 0, winreg.REG_SZ, value)
    winreg.CloseKey(key)
    print(f"Installed autostart: HKCU Run '{TASK_NAME}' → {value}")
    return 0

def cli_uninstall() -> int:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, TASK_NAME)
        winreg.CloseKey(key)
        print(f"Removed autostart: HKCU Run '{TASK_NAME}'")
    except FileNotFoundError:
        print(f"'{TASK_NAME}' not in Run key — nothing to remove.")
    return 0


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Ollama system tray manager")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--start",     action="store_true")
    g.add_argument("--stop",      action="store_true")
    g.add_argument("--restart",   action="store_true")
    g.add_argument("--status",    action="store_true")
    g.add_argument("--install",   action="store_true")
    g.add_argument("--uninstall", action="store_true")
    args = p.parse_args()

    for name, fn in {
        "start": cli_start, "stop": cli_stop, "restart": cli_restart,
        "status": cli_status, "install": cli_install, "uninstall": cli_uninstall,
    }.items():
        if getattr(args, name):
            sys.exit(fn())

    OllamaTray().run()


if __name__ == "__main__":
    main()
