"""
ollama_tray_linux.py — Ollama system tray manager for Linux (KDE/GNOME).

Manages Ollama as a systemd service (system or user) or detects the process.
Tray icon: green = running, red = stopped, amber = transitioning.
Right-click menu: service control + live CPU/RAM stats (1 s refresh).
Double-click: toggle resource-monitor dialog.

CLI flags:
  --start      Start Ollama service
  --stop       Stop Ollama service
  --restart    Restart Ollama service
  --status     Print current service status (exit 0 = running)
  --install    Register autostart via XDG (~/.config/autostart/)
  --uninstall  Remove XDG autostart entry
"""

import argparse
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

import psutil
import pystray
from pystray import MenuItem as item, Menu
from PIL import Image, ImageDraw, ImageFont

# ── pystray backend: prefer appindicator (KDE SNI-compatible) ────────────────
os.environ.setdefault("PYSTRAY_BACKEND", "appindicator")

# ── constants ────────────────────────────────────────────────────────────────

OLLAMA_URL        = "http://localhost:11434"
AUTOSTART_NAME    = "ollama-tray"
ICON_SIZE         = 64
STATS_INTERVAL    = 1     # seconds
STATUS_INTERVAL   = 5     # ticks (every 5 s)
TOGGLE_DEBOUNCE_S = 0.6   # seconds

STATUS_COLOR = {
    "running":  (72,  199, 116),
    "stopped":  (220,  53,  69),
    "starting": (255, 193,   7),
    "stopping": (255, 193,   7),
    "unknown":  (255, 193,   7),
}

# systemd service mode: "system" | "user" | None (process-only)
_SERVICE_MODE: str | None = None


def _detect_service_mode() -> str | None:
    """Probe systemd for an 'ollama' unit. Returns 'system', 'user', or None."""
    for flag in ([], ["--user"]):
        try:
            r = subprocess.run(
                ["systemctl", *flag, "status", "ollama"],
                capture_output=True, timeout=5,
            )
            # 0 = active, 3 = inactive/failed but unit exists
            if r.returncode in (0, 3):
                return "user" if flag else "system"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return None


def _init_service_mode() -> None:
    global _SERVICE_MODE
    if _SERVICE_MODE is None:
        _SERVICE_MODE = _detect_service_mode()


# ── icon ─────────────────────────────────────────────────────────────────────

def _find_ollama_icon() -> str | None:
    candidates = [
        "/usr/share/icons/hicolor/256x256/apps/ollama.png",
        "/usr/share/icons/hicolor/128x128/apps/ollama.png",
        "/usr/share/icons/hicolor/64x64/apps/ollama.png",
        os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/ollama.png"),
        os.path.join(os.path.dirname(__file__), "assets", "ollama-icon.png"),
    ]
    return next((c for c in candidates if os.path.exists(c)), None)


OLLAMA_ICON = _find_ollama_icon()


def _base_image() -> Image.Image:
    if OLLAMA_ICON:
        img = Image.open(OLLAMA_ICON).convert("RGBA")
        return img.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, ICON_SIZE - 2, ICON_SIZE - 2], fill=(30, 30, 30, 230))
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 30)
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


# ── service control (systemctl) ───────────────────────────────────────────────

def _ctl(*args, timeout: int = 10) -> subprocess.CompletedProcess:
    _init_service_mode()
    base = ["systemctl"]
    if _SERVICE_MODE == "user":
        base.append("--user")
    return subprocess.run(
        [*base, *args],
        capture_output=True, text=True, timeout=timeout,
    )


def get_status() -> str:
    _init_service_mode()
    if _SERVICE_MODE is None:
        # no systemd unit — fall back to process detection
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
    """Re-launch with pkexec for graphical privilege elevation."""
    script = os.path.abspath(__file__)
    exe = sys.executable
    try:
        subprocess.Popen(["pkexec", exe, script, f"--{action}"])
    except FileNotFoundError:
        # pkexec not available — try kdesu, then gksudo
        for elevator in ("kdesu", "gksudo", "gksu"):
            try:
                subprocess.Popen([elevator, exe, script, f"--{action}"])
                return
            except FileNotFoundError:
                continue


def _svc_start() -> None:
    _ctl("start", "ollama", timeout=30)


def _svc_stop() -> None:
    _ctl("stop", "ollama", timeout=30)


def _service_action(action: str) -> None:
    _init_service_mode()
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
                ct   = p.create_time()
                name = p.name()
            s.cpu_pct  += cpu
            s.mem_rss  += mi.rss
            s.mem_vms  += mi.vms
            s.threads  += thr
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

# Linux monospace fonts, tried in order
_MONO_FONTS = ["Hack", "JetBrains Mono", "Fira Code", "Monospace", "Courier New"]
_UI_FONTS   = ["Noto Sans", "Liberation Sans", "DejaVu Sans", "Sans"]


def _first_available_font(candidates: list[str]) -> str:
    """Return first font name from candidates (tkinter will fall back anyway)."""
    return candidates[0]


def _set_dialog_closed() -> None:
    global _dialog_open, _dialog_root
    _dialog_open = False
    _dialog_root = None


def _open_resource_dialog() -> None:
    global _dialog_open, _dialog_root, _last_toggle_time

    with _dialog_lock:
        now = time.monotonic()
        if now - _last_toggle_time < TOGGLE_DEBOUNCE_S:
            return
        _last_toggle_time = now

        if _dialog_open:
            if _dialog_root is not None:
                try:
                    _dialog_root.after(0, _dialog_root.destroy)
                except Exception:
                    pass
            return
        _dialog_open = True

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

        if OLLAMA_ICON and OLLAMA_ICON.endswith(".png"):
            try:
                icon_img = tk.PhotoImage(file=OLLAMA_ICON)
                root.iconphoto(True, icon_img)
            except Exception:
                pass

        mono = _first_available_font(_MONO_FONTS)
        ui   = _first_available_font(_UI_FONTS)

        tk.Label(
            root, text="  Ollama Resource Monitor",
            bg="#313244", fg="#cdd6f4",
            font=(ui, 11, "bold"),
            anchor="w", padx=8, pady=6,
        ).pack(fill="x")

        frame = tk.Frame(root, bg="#1e1e2e")
        frame.pack(fill="both", expand=True, padx=12, pady=8)

        txt = tk.Text(
            frame,
            font=(mono, 10),
            bg="#1e1e2e", fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat", bd=0,
            width=52, height=14,
            state="disabled",
        )
        txt.pack(fill="both", expand=True)

        txt.tag_configure("header", foreground="#89b4fa", font=(mono, 10, "bold"))
        txt.tag_configure("good",   foreground="#a6e3a1")
        txt.tag_configure("warn",   foreground="#f9e2af")
        txt.tag_configure("bad",    foreground="#f38ba8")
        txt.tag_configure("dim",    foreground="#6c7086")
        txt.tag_configure("sep",    foreground="#313244")

        footer = tk.Label(
            root, text="",
            bg="#181825", fg="#6c7086",
            font=(mono, 9), anchor="w", padx=8, pady=4,
        )
        footer.pack(fill="x")

        def _cpu_tag(pct): return "good" if pct < 30 else "warn" if pct < 70 else "bad"
        def _mem_tag(mb):  return "good" if mb < 2048 else "warn" if mb < 6144 else "bad"

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
                    ("CPU (total)",  f"{s.cpu_pct:.1f}%",       _cpu_tag(s.cpu_pct)),
                    ("RAM  RSS",     _fmt_bytes(s.mem_rss),      _mem_tag(s.mem_rss/1024**2)),
                    ("RAM  VMS",     _fmt_bytes(s.mem_vms),      "dim"),
                    ("Threads",      str(s.threads),             "good"),
                    ("Processes",    str(s.num_procs),           "dim"),
                    ("Uptime",       s.uptime,                   "dim"),
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
        _init_service_mode()
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


# ── autostart (XDG) ──────────────────────────────────────────────────────────

_AUTOSTART_DIR = Path.home() / ".config" / "autostart"
_DESKTOP_FILE  = _AUTOSTART_DIR / f"{AUTOSTART_NAME}.desktop"


def _desktop_entry() -> str:
    script = os.path.abspath(__file__)
    exe    = sys.executable
    if getattr(sys, "frozen", False):
        exec_line = f'Exec="{exe}"'
    else:
        exec_line = f'Exec={exe} "{script}"'

    icon_line = f"Icon={OLLAMA_ICON}" if OLLAMA_ICON else "Icon=ollama"

    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name=Ollama Tray\n"
        "Comment=Ollama system tray manager\n"
        f"{exec_line}\n"
        f"{icon_line}\n"
        "Hidden=false\n"
        "NoDisplay=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-KDE-autostart-enabled=true\n"
        "X-KDE-autostart-phase=2\n"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def cli_start() -> int:
    _init_service_mode()
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
    _init_service_mode()
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
    _init_service_mode()
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


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Ollama system tray manager (Linux)")
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
