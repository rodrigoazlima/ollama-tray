import sys
import threading
import time
from datetime import datetime

import ollama_tray.config as _cfg
from ollama_tray.stats import _fmt_bytes, refresh_stats

_dialog_lock      = threading.Lock()
_dialog_open      = False
_dialog_root      = None  # tk.Tk when open; untyped to allow deferred tkinter import
_last_toggle_time = 0.0

if sys.platform == "win32":
    _MONO_FONT = "Consolas"
    _UI_FONT   = "Segoe UI"
else:
    _MONO_FONT = "Hack"
    _UI_FONT   = "Noto Sans"


def _set_dialog_closed() -> None:
    global _dialog_open, _dialog_root
    _dialog_open = False
    _dialog_root = None


def open_resource_dialog() -> None:
    global _dialog_open, _dialog_root, _last_toggle_time

    with _dialog_lock:
        now = time.monotonic()
        if now - _last_toggle_time < _cfg.TOGGLE_DEBOUNCE_S:
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
        try:
            import tkinter as tk
        except ImportError:
            print(
                "ollama-tray: tkinter not available — resource monitor dialog disabled",
                file=sys.stderr,
            )
            return

        c = _cfg.UI_COLOR

        root = tk.Tk()
        with _dialog_lock:
            global _dialog_root
            _dialog_root = root

        root.title("Ollama Resource Monitor")
        root.resizable(False, False)
        root.configure(bg=c["bg"])

        from ollama_tray.icon import _icon_path
        if _icon_path:
            if _icon_path.endswith(".ico"):
                try:
                    root.iconbitmap(_icon_path)
                except Exception:
                    pass
            elif _icon_path.endswith(".png"):
                try:
                    img = tk.PhotoImage(file=_icon_path)
                    root.iconphoto(True, img)
                except Exception:
                    pass

        tk.Label(
            root, text="  Ollama Resource Monitor",
            bg=c["surface"], fg=c["fg"],
            font=(_UI_FONT, 11, "bold"),
            anchor="w", padx=8, pady=6,
        ).pack(fill="x")

        frame = tk.Frame(root, bg=c["bg"])
        frame.pack(fill="both", expand=True, padx=12, pady=8)

        txt = tk.Text(
            frame,
            font=(_MONO_FONT, 10),
            bg=c["bg"], fg=c["fg"],
            insertbackground=c["fg"],
            relief="flat", bd=0,
            width=52, height=14,
            state="disabled",
        )
        txt.pack(fill="both", expand=True)

        txt.tag_configure("header", foreground=c["blue"],   font=(_MONO_FONT, 10, "bold"))
        txt.tag_configure("good",   foreground=c["green"])
        txt.tag_configure("warn",   foreground=c["yellow"])
        txt.tag_configure("bad",    foreground=c["red"])
        txt.tag_configure("dim",    foreground=c["dim"])
        txt.tag_configure("sep",    foreground=c["surface"])

        footer = tk.Label(
            root, text="",
            bg=c["bg_dark"], fg=c["dim"],
            font=(_MONO_FONT, 9), anchor="w", padx=8, pady=4,
        )
        footer.pack(fill="x")

        def _cpu_tag(pct: float) -> str:
            return "good" if pct < 30 else "warn" if pct < 70 else "bad"

        def _mem_tag(mb: float) -> str:
            return "good" if mb < 2048 else "warn" if mb < 6144 else "bad"

        def _update() -> None:
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

                rows = [
                    ("CPU (total)", f"{s.cpu_pct:.1f}%",      _cpu_tag(s.cpu_pct)),
                    ("RAM  RSS",    _fmt_bytes(s.mem_rss),     _mem_tag(s.mem_rss / 1024 ** 2)),
                    ("RAM  VMS",    _fmt_bytes(s.mem_vms),     "dim"),
                    ("Threads",     str(s.threads),            "good"),
                    ("Processes",   str(s.num_procs),          "dim"),
                    ("Uptime",      s.uptime,                  "dim"),
                ]
                if s.handles:
                    rows.insert(4, ("Handles", str(s.handles), "dim"))

                for label, val, tag in rows:
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
