import sys
import threading
import time
from datetime import datetime

import ollama_tray.config as _cfg
from ollama_tray import __version__
from ollama_tray.stats import (
    _fmt_bytes, fmt_expires, current_stats, get_history,
    last_refresh_time, start_ps_poller,
)

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

        import ollama_tray.config as _cfg_live
        start_ps_poller(_cfg_live.OLLAMA_URL)

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
            width=58, height=22,
            state="disabled",
        )
        txt.pack(fill="both", expand=True)

        txt.tag_configure("header", foreground=c["blue"],   font=(_MONO_FONT, 10, "bold"))
        txt.tag_configure("good",   foreground=c["green"])
        txt.tag_configure("warn",   foreground=c["yellow"])
        txt.tag_configure("bad",    foreground=c["red"])
        txt.tag_configure("dim",    foreground=c["dim"])
        txt.tag_configure("sep",    foreground=c["surface"])

        # ── action buttons ────────────────────────────────────────────────────
        btn_frame = tk.Frame(root, bg=c["bg_dark"], pady=6, padx=12)

        def _start_ollama():
            from ollama_tray.platform import service_action
            from ollama_tray.stats import force_scan_next
            force_scan_next()
            threading.Thread(target=service_action, args=("start",), daemon=True).start()

        def _force_kill():
            import psutil
            from ollama_tray.stats import force_scan_next
            for p in psutil.process_iter(["name", "pid"]):
                if "ollama" in (p.info.get("name") or "").lower():
                    try:
                        p.kill()
                    except psutil.NoSuchProcess:
                        pass
            force_scan_next()

        btn_start = tk.Button(
            btn_frame, text="Start Ollama",
            command=_start_ollama,
            bg=c["green"], fg=c["bg"],
            font=(_UI_FONT, 10, "bold"),
            relief="flat", padx=14, pady=5, cursor="hand2",
            activebackground=c["green_act"], activeforeground=c["bg"],
        )
        btn_kill = tk.Button(
            btn_frame, text="Force Kill All",
            command=_force_kill,
            bg=c["red"], fg=c["fg"],
            font=(_UI_FONT, 10, "bold"),
            relief="flat", padx=14, pady=5, cursor="hand2",
            activebackground="#c0392b", activeforeground=c["fg"],
        )

        # ── history chart ─────────────────────────────────────────────────────
        CHART_W, CHART_H = 420, 60
        chart_frame = tk.Frame(root, bg=c["bg_dark"], padx=12, pady=4)
        chart_frame.pack(fill="x")

        legend_row = tk.Frame(chart_frame, bg=c["bg_dark"])
        legend_row.pack(fill="x")
        tk.Label(legend_row, text="■ CPU%", bg=c["bg_dark"], fg=c["blue"],
                 font=(_MONO_FONT, 8)).pack(side="left")
        tk.Label(legend_row, text="■ RAM",  bg=c["bg_dark"], fg=c["green"],
                 font=(_MONO_FONT, 8)).pack(side="left", padx=(8, 0))

        chart_canvas = tk.Canvas(
            chart_frame,
            width=CHART_W, height=CHART_H,
            bg=c["bg_dark"], highlightthickness=0,
        )
        chart_canvas.pack()

        # ── footer ────────────────────────────────────────────────────────────
        footer_frame = tk.Frame(root, bg=c["bg_dark"], pady=5, padx=8)
        footer_frame.pack(fill="x")

        footer_time = tk.Label(
            footer_frame, text="",
            bg=c["bg_dark"], fg=c["dim"],
            font=(_MONO_FONT, 9), anchor="w",
        )
        footer_time.pack(side="left", fill="x", expand=True)

        tk.Label(
            footer_frame, text=f"v{__version__}",
            bg=c["bg_dark"], fg=c["dim"],
            font=(_MONO_FONT, 9),
        ).pack(side="right", padx=(0, 4))

        def _open_settings_from_dialog():
            from ollama_tray.settings_dialog import open_settings_dialog
            open_settings_dialog()

        tk.Button(
            footer_frame, text="Settings…",
            command=_open_settings_from_dialog,
            bg=c["surface"], fg=c["fg"],
            font=(_UI_FONT, 9),
            relief="flat", padx=8, pady=2, cursor="hand2",
            activebackground=c["surface1"], activeforeground=c["fg"],
        ).pack(side="right", padx=(0, 6))

        def _cpu_tag(pct: float) -> str:
            return "good" if pct < 30 else "warn" if pct < 70 else "bad"

        def _mem_tag(mb: float) -> str:
            return "good" if mb < 2048 else "warn" if mb < 6144 else "bad"

        def _draw_chart() -> None:
            cpu_hist, ram_hist = get_history()
            chart_canvas.delete("all")
            n = len(cpu_hist)
            if n < 2:
                return
            W, H = CHART_W, CHART_H

            # grid lines at 25%, 50%, 75%
            for frac in (0.25, 0.5, 0.75):
                y = H - frac * H
                chart_canvas.create_line(0, y, W, y, fill=c["surface"], width=1)

            def _polyline(values: list, max_val: float, color: str) -> None:
                if max_val <= 0:
                    return
                pts: list[float] = []
                for i, v in enumerate(values):
                    x = W * i / (n - 1)
                    y = H - max(0.0, min(1.0, v / max_val)) * H
                    pts.extend((x, y))
                if len(pts) >= 4:
                    chart_canvas.create_line(*pts, fill=color, width=1, smooth=True)

            max_ram = max(ram_hist) if ram_hist else 1
            _polyline(list(cpu_hist), 100.0,  c["blue"])
            _polyline(list(ram_hist), max_ram, c["green"])

        def _update() -> None:
            # Use cached stats — the poll thread drives refresh_stats().
            s = current_stats()
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            sep = "─" * 50 + "\n"

            if s.is_empty():
                txt.insert("end", "\n  No Ollama processes found.\n\n", "dim")
                txt.insert("end", "  Service may be stopped.\n", "dim")
                btn_kill.pack_forget()
                btn_start.pack(side="left")
                btn_frame.pack(fill="x", before=chart_frame)
            else:
                btn_start.pack_forget()
                btn_kill.pack(side="left")
                btn_frame.pack(fill="x", before=chart_frame)

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

                vram_ollama = sum(m.get("size_vram", 0) for m in s.models)

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
                if vram_ollama:
                    rows.append(("VRAM (models)", _fmt_bytes(vram_ollama), "good"))
                if s.vram_nvml:
                    used, total = s.vram_nvml
                    rows.append(("VRAM (GPU)",
                                 f"{_fmt_bytes(used)} / {_fmt_bytes(total)}", "good"))

                for label, val, tag in rows:
                    txt.insert("end", f"  {label:<16}", "dim")
                    txt.insert("end", f"  {val}\n", tag)

                # ── loaded models ──────────────────────────────────────────
                txt.insert("end", "\n  " + sep, "sep")
                txt.insert("end", "  LOADED MODELS\n", "header")
                txt.insert("end", "  " + sep, "sep")

                if not s.models:
                    txt.insert("end", "  (none)\n", "dim")
                else:
                    for m in s.models:
                        name      = m.get("name", "?")
                        size_vram = m.get("size_vram", 0)
                        size_tot  = m.get("size", 0)
                        exp_str   = fmt_expires(m.get("expires_at", ""))

                        display = name if len(name) <= 46 else name[:45] + "…"
                        txt.insert("end", f"  {display}\n", "good")

                        vram_str = _fmt_bytes(size_vram) if size_vram else "CPU only"
                        ram_str  = _fmt_bytes(size_tot - size_vram) if size_tot > size_vram else "—"
                        detail   = f"    VRAM {vram_str}   RAM {ram_str}"
                        if exp_str:
                            detail += f"   exp {exp_str}"
                        txt.insert("end", detail + "\n", "dim")

            txt.configure(state="disabled")
            _draw_chart()

            ts = last_refresh_time()
            if ts:
                footer_time.configure(
                    text=f"  Updated {datetime.now().strftime('%H:%M:%S')}"
                )
            root.after(1000, _update)

        _update()
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
    finally:
        _set_dialog_closed()
