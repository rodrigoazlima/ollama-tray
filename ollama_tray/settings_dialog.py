"""
Settings dialog: GUI editor for Ollama GPU/CPU/path configuration.
Reads current values from config and writes changes to config.properties.
"""
import re
import sys
import threading

import ollama_tray.config as _cfg

_dialog_lock = threading.Lock()
_dialog_open = False
_dialog_root = None

_UI_FONT   = "Segoe UI"   if sys.platform == "win32" else "Noto Sans"
_MONO_FONT = "Consolas"   if sys.platform == "win32" else "Hack"


def open_settings_dialog() -> None:
    global _dialog_open, _dialog_root
    with _dialog_lock:
        if _dialog_open:
            if _dialog_root is not None:
                try:
                    _dialog_root.lift()
                    _dialog_root.focus_force()
                except Exception:
                    pass
            return
        _dialog_open = True
    threading.Thread(target=_run_dialog, daemon=True).start()


def _set_closed() -> None:
    global _dialog_open, _dialog_root
    _dialog_open = False
    _dialog_root = None


def _write_config(updates: dict[str, str]) -> None:
    """Update or append key = value pairs in config.properties, preserving all comments."""
    path = _cfg._config_path
    if not path or not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
        for key, value in updates.items():
            pattern = rf"^({re.escape(key)}\s*=).*$"
            if re.search(pattern, text, re.MULTILINE):
                text = re.sub(pattern, rf"\1 {value}", text, flags=re.MULTILINE)
            else:
                text += f"\n{key} = {value}\n"
        path.write_text(text, encoding="utf-8")
    except Exception:
        pass


def _run_dialog() -> None:
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog

        c = _cfg.UI_COLOR

        root = tk.Tk()
        with _dialog_lock:
            global _dialog_root
            _dialog_root = root

        root.title("Ollama Settings")
        root.resizable(False, False)
        root.configure(bg=c["bg"])
        root.attributes("-topmost", True)

        w, h = 520, 580
        root.update_idletasks()
        x = (root.winfo_screenwidth()  - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")

        # ── header ────────────────────────────────────────────────────────────
        tk.Label(
            root, text="  ⚙  Ollama Settings",
            bg=c["surface"], fg=c["fg"],
            font=(_UI_FONT, 11, "bold"),
            anchor="w", padx=8, pady=7,
        ).pack(fill="x")

        tk.Label(
            root,
            text="  Applied as environment variables when Ollama starts from the tray.",
            bg=c["bg"], fg=c["dim"],
            font=(_UI_FONT, 9), anchor="w", padx=8, pady=3,
        ).pack(fill="x")

        body = tk.Frame(root, bg=c["bg"], padx=20, pady=8)
        body.pack(fill="both", expand=True)

        # ── helpers ───────────────────────────────────────────────────────────
        def section(label: str) -> None:
            tk.Label(body, text=label,
                     bg=c["bg"], fg=c["blue"],
                     font=(_UI_FONT, 9, "bold"), anchor="w",
                     ).pack(fill="x", pady=(12, 1))
            tk.Frame(body, bg=c["surface"], height=1).pack(fill="x")

        def row(label: str, hint: str = "") -> None:
            f = tk.Frame(body, bg=c["bg"])
            f.pack(fill="x", pady=(7, 0))
            tk.Label(f, text=label, bg=c["bg"], fg=c["subtext"],
                     font=(_UI_FONT, 9, "bold"), anchor="w").pack(side="left")
            if hint:
                tk.Label(f, text=hint, bg=c["bg"], fg=c["dim"],
                         font=(_UI_FONT, 8), anchor="w").pack(side="left", padx=(6, 0))

        def mono_entry(var: tk.StringVar, width: int = 36) -> tk.Entry:
            e = tk.Entry(body, textvariable=var,
                         bg=c["surface"], fg=c["fg"], insertbackground=c["fg"],
                         relief="flat", font=(_MONO_FONT, 10), width=width)
            e.pack(fill="x", ipady=4, pady=(3, 0))
            return e

        # ── Server ────────────────────────────────────────────────────────────
        section("Server")

        row("Host  (OLLAMA_HOST)", "bind address for ollama serve")
        host_var = tk.StringVar(value=_cfg.SERVE_HOST)
        mono_entry(host_var)

        row("API URL  (OLLAMA_URL)", "tray uses this to poll status")
        url_var = tk.StringVar(value=_cfg.OLLAMA_URL)
        mono_entry(url_var)

        # ── GPU ───────────────────────────────────────────────────────────────
        section("GPU")

        row("GPU count  (OLLAMA_NUM_GPU)", "999 = use all available")
        gpu_var = tk.StringVar(value=_cfg.OLLAMA_NUM_GPU)
        mono_entry(gpu_var, width=10)

        row("KV cache type  (OLLAMA_KV_CACHE_TYPE)",
            "f16 = lossless  ·  q8_0 ≈ 2× ctx  ·  q4_0 ≈ 4× ctx")
        kv_var = tk.StringVar(value=_cfg.OLLAMA_KV_CACHE_TYPE)
        kv_style = ttk.Style()
        kv_style.theme_use("default")
        kv_style.configure(
            "Cfg.TCombobox",
            fieldbackground=c["surface"], background=c["surface"],
            foreground=c["fg"],
            selectbackground=c["surface1"], selectforeground=c["fg"],
        )
        ttk.Combobox(
            body, textvariable=kv_var,
            values=["f16", "q8_0", "q4_0"],
            style="Cfg.TCombobox",
            state="readonly", font=(_MONO_FONT, 10), width=12,
        ).pack(anchor="w", ipady=3, pady=(3, 0))

        row("Flash Attention  (OLLAMA_FLASH_ATTENTION)",
            "enable for stable long-context inference")
        fa_var = tk.BooleanVar(value=_cfg.OLLAMA_FLASH_ATTENTION == "1")
        tk.Checkbutton(
            body, text="Enabled",
            variable=fa_var,
            bg=c["bg"], fg=c["fg"],
            activebackground=c["bg"], activeforeground=c["fg"],
            selectcolor=c["surface"],
            font=(_UI_FONT, 9),
        ).pack(anchor="w", pady=(3, 0))

        # ── Models ────────────────────────────────────────────────────────────
        section("Models")

        row("Models directory  (OLLAMA_MODELS)", "leave blank to use Ollama default")
        models_var = tk.StringVar(value=_cfg.OLLAMA_MODELS_DIR)
        mrow = tk.Frame(body, bg=c["bg"])
        mrow.pack(fill="x", pady=(3, 0))
        tk.Entry(mrow, textvariable=models_var,
                 bg=c["surface"], fg=c["fg"], insertbackground=c["fg"],
                 relief="flat", font=(_MONO_FONT, 10),
                 ).pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(
            mrow, text="…",
            command=lambda: models_var.set(
                filedialog.askdirectory(
                    title="Select Ollama models directory",
                    initialdir=models_var.get() or "/",
                ) or models_var.get()
            ),
            bg=c["surface1"], fg=c["fg"],
            relief="flat", font=(_UI_FONT, 9), padx=8, pady=3, cursor="hand2",
            activebackground=c["overlay0"], activeforeground=c["fg"],
        ).pack(side="left", padx=(4, 0))

        row("Max loaded models  (OLLAMA_MAX_LOADED_MODELS)",
            "models kept simultaneously in VRAM")
        maxmod_var = tk.StringVar(value=str(_cfg.OLLAMA_MAX_LOADED_MODELS))
        mono_entry(maxmod_var, width=8)

        row("Parallel requests  (OLLAMA_NUM_PARALLEL)",
            "simultaneous inference requests")
        parallel_var = tk.StringVar(value=str(_cfg.OLLAMA_NUM_PARALLEL))
        mono_entry(parallel_var, width=8)

        # ── AMD ROCm ──────────────────────────────────────────────────────────
        section("AMD ROCm")

        row("HSA_ENABLE_SDMA",
            "0 = disable SDMA on RDNA3 (+5–15% throughput)  ·  1 = AMD default")
        sdma_var = tk.StringVar(value=_cfg.HSA_ENABLE_SDMA)
        mono_entry(sdma_var, width=8)

        # ── footer ────────────────────────────────────────────────────────────
        footer = tk.Frame(root, bg=c["bg_dark"], pady=12, padx=20)
        footer.pack(fill="x")

        def _save() -> None:
            _write_config({
                "ollama_serve_host":        host_var.get().strip(),
                "ollama_url":               url_var.get().strip(),
                "ollama_num_gpu":           gpu_var.get().strip() or "999",
                "ollama_kv_cache_type":     kv_var.get().strip() or "f16",
                "ollama_flash_attention":   "1" if fa_var.get() else "0",
                "ollama_models_dir":        models_var.get().strip(),
                "ollama_max_loaded_models": maxmod_var.get().strip() or "1",
                "ollama_num_parallel":      parallel_var.get().strip() or "1",
                "hsa_enable_sdma":          sdma_var.get().strip() or "0",
            })
            _cfg.reload()
            root.destroy()

        tk.Button(
            footer, text="Save & Reload",
            command=_save,
            bg=c["blue"], fg=c["bg"],
            font=(_UI_FONT, 10, "bold"),
            relief="flat", padx=16, pady=6, cursor="hand2",
            activebackground=c["blue_act"], activeforeground=c["bg"],
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            footer, text="Cancel",
            command=root.destroy,
            bg=c["surface"], fg=c["fg"],
            font=(_UI_FONT, 10),
            relief="flat", padx=14, pady=6, cursor="hand2",
            activebackground=c["surface1"], activeforeground=c["fg"],
        ).pack(side="left")

        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
    finally:
        _set_closed()
