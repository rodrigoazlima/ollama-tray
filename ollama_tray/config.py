"""
Loads config.properties, exposes typed configuration values,
and hot-reloads when the file changes on disk via watchdog.

Search order for config.properties:
  1. Directory of the frozen executable (PyInstaller builds)
  2. Repository / install root  (two levels above this file)
  3. User config dir: ~/.ollama-tray/config.properties
"""
import configparser
import os
import sys
import threading
from pathlib import Path
from typing import Callable


# ── file discovery ────────────────────────────────────────────────────────────

def _find_config() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "config.properties")
    candidates.append(Path(__file__).parent.parent / "config.properties")
    candidates.append(Path.home() / ".ollama-tray" / "config.properties")
    return next((p for p in candidates if p.exists()), None)


# ── parsing helpers ───────────────────────────────────────────────────────────

def _parse(text: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(default_section="props")
    try:
        cp.read_string("[props]\n" + text)
    except Exception:
        pass
    return cp


def _s(cp: configparser.ConfigParser, key: str, default: str) -> str:
    try:
        return cp.get("props", key).strip()
    except (configparser.NoSectionError, configparser.NoOptionError):
        return default


def _i(cp: configparser.ConfigParser, key: str, default: int) -> int:
    try:
        return int(_s(cp, key, str(default)))
    except ValueError:
        return default


def _f(cp: configparser.ConfigParser, key: str, default: float) -> float:
    try:
        return float(_s(cp, key, str(default)))
    except ValueError:
        return default


def _rgb(
    cp: configparser.ConfigParser,
    key: str,
    default: tuple[int, int, int],
) -> tuple[int, int, int]:
    raw = _s(cp, key, "")
    try:
        r, g, b = (int(x.strip()) for x in raw.split(","))
        return (r, g, b)
    except (ValueError, TypeError):
        return default


def _ver(
    cp: configparser.ConfigParser,
    key: str,
    default: tuple[int, ...],
) -> tuple[int, ...]:
    raw = _s(cp, key, "")
    try:
        parts = tuple(int(x) for x in raw.split(".")[:3])
        return parts if len(parts) == 3 else default
    except (ValueError, AttributeError):
        return default


_DEFAULT_CONFIG_TEXT = """\
# ollama-tray configuration
# Edit and restart the tray to apply changes.
# All keys are optional — missing keys fall back to the defaults shown here.

# ── Server ────────────────────────────────────────────────────────────────────

# Ollama HTTP API base URL
ollama_url = http://localhost:11434

# Default host passed to OLLAMA_HOST when starting Ollama from the tray dialog
ollama_serve_host = 127.0.0.1:11434

# Minimum Ollama version; warn on startup if the running version is below this
min_ollama_version = 0.1.14

# ── Tray polling ──────────────────────────────────────────────────────────────

# Seconds between CPU/RAM stat refreshes
stats_interval = 1

# Number of stat ticks between service-status re-checks  (status_interval × stats_interval = s)
status_interval = 5

# Minimum seconds between resource-monitor dialog open/close toggles
toggle_debounce = 0.6

# ── Icon ──────────────────────────────────────────────────────────────────────

# Tray icon canvas size in pixels
icon_size = 64

# ── Windows service ───────────────────────────────────────────────────────────

# Name of the Windows service managed by the tray
service_name = Ollama

# Registry key name used for autostart (HKCU\\...\\Run)
task_name = OllamaTray

# ── Linux autostart ───────────────────────────────────────────────────────────

# Stem of the XDG .desktop autostart file (~/.config/autostart/<name>.desktop)
autostart_name = ollama-tray

# ── Status indicator colors (R,G,B) ──────────────────────────────────────────

color_running  = 72,199,116
color_stopped  = 220,53,69
color_starting = 255,193,7
color_stopping = 255,193,7
color_unknown  = 255,193,7

# ── Ollama GPU / performance ──────────────────────────────────────────────────
# These are passed as environment variables when starting Ollama from the tray.
# Leave a value blank to let Ollama use its own default.

# Number of GPU layers to offload (blank = Ollama auto-detects; set to 0 for CPU-only)
ollama_num_gpu =

# KV cache quantization: f16 (lossless) | q8_0 (near-lossless) | q4_0 (4× smaller)
ollama_kv_cache_type = f16

# Enable Flash Attention for long-context inference: 0 | 1
ollama_flash_attention = 0

# Parallel inference requests handled simultaneously
ollama_num_parallel = 1

# Models kept loaded in VRAM simultaneously
ollama_max_loaded_models = 1

# ── Ollama paths ──────────────────────────────────────────────────────────────

# Override Ollama model storage directory (blank = Ollama default)
ollama_models_dir =

# ── AMD ROCm ──────────────────────────────────────────────────────────────────
# AMD-specific tuning — leave blank on NVIDIA/Intel/Apple hardware.

# HSA_ENABLE_SDMA: 0 = disable SDMA engine on RDNA3 (+5-15% throughput)
# Set to 1 to restore AMD default behaviour; leave blank on non-AMD systems
hsa_enable_sdma =

# ── Model preload ─────────────────────────────────────────────────────────────

# Model to load into VRAM after Ollama starts (blank = none)
# Example: preload_model = qwen3:30b-a3b
preload_model =

# Auto-start Ollama silently at tray launch when not running: true | false
# false = show the "Start Ollama" dialog instead
auto_start = false

# ── Recovery ──────────────────────────────────────────────────────────────────

# Automatically restart Ollama when it stops unexpectedly: true | false
auto_recover = false

# ── Updates ───────────────────────────────────────────────────────────────────

# Check for a newer version of ollama-tray on startup and prompt to install: true | false
check_for_updates = true

# ── Window / UI theme ─────────────────────────────────────────────────────────

# Theme for tkinter dialogs: dark | light | black
# Change here or via the Theme submenu in the tray icon.
ui_theme = dark
"""

_THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg":        "#1e1e2e",
        "bg_dark":   "#181825",
        "surface":   "#313244",
        "surface1":  "#45475a",
        "overlay0":  "#585b70",
        "dim":       "#6c7086",
        "subtext":   "#a6adc8",
        "fg":        "#cdd6f4",
        "blue":      "#89b4fa",
        "blue_act":  "#74c7ec",
        "green":     "#a6e3a1",
        "green_act": "#94e2d5",
        "yellow":    "#f9e2af",
        "red":       "#f38ba8",
    },
    "light": {
        "bg":        "#eff1f5",
        "bg_dark":   "#e6e9ef",
        "surface":   "#ccd0da",
        "surface1":  "#bcc0cc",
        "overlay0":  "#9ca0b0",
        "dim":       "#7c7f93",
        "subtext":   "#5c5f77",
        "fg":        "#4c4f69",
        "blue":      "#1e66f5",
        "blue_act":  "#209fb5",
        "green":     "#40a02b",
        "green_act": "#179299",
        "yellow":    "#df8e1d",
        "red":       "#d20f39",
    },
    "black": {
        "bg":        "#000000",
        "bg_dark":   "#0a0a0a",
        "surface":   "#141414",
        "surface1":  "#242424",
        "overlay0":  "#3c3c3c",
        "dim":       "#858585",
        "subtext":   "#aaaaaa",
        "fg":        "#f8f8f8",
        "blue":      "#5fa8f5",
        "blue_act":  "#4fc9de",
        "green":     "#4de87c",
        "green_act": "#3dccbd",
        "yellow":    "#ffd500",
        "red":       "#ff4444",
    },
}

AVAILABLE_THEMES: list[str] = list(_THEMES)


def _apply(cp: configparser.ConfigParser) -> None:
    """Write all parsed values into this module's globals."""
    g = globals()
    g["OLLAMA_URL"]        = _s  (cp, "ollama_url",          "http://localhost:11434")
    g["SERVE_HOST"]        = _s  (cp, "ollama_serve_host",   "127.0.0.1:11434")
    g["MIN_OLLAMA"]        = _ver(cp, "min_ollama_version",  (0, 1, 14))
    g["STATS_INTERVAL"]    = _i  (cp, "stats_interval",      1)
    g["STATUS_INTERVAL"]   = _i  (cp, "status_interval",     5)
    g["TOGGLE_DEBOUNCE_S"] = _f  (cp, "toggle_debounce",     0.6)
    g["ICON_SIZE"]         = _i  (cp, "icon_size",           64)
    g["SERVICE_NAME"]      = _s  (cp, "service_name",        "Ollama")
    g["TASK_NAME"]         = _s  (cp, "task_name",           "OllamaTray")
    g["AUTOSTART_NAME"]    = _s  (cp, "autostart_name",      "ollama-tray")
    g["STATUS_COLOR"]      = {
        "running":  _rgb(cp, "color_running",  (72,  199, 116)),
        "stopped":  _rgb(cp, "color_stopped",  (220,  53,  69)),
        "starting": _rgb(cp, "color_starting", (255, 193,   7)),
        "stopping": _rgb(cp, "color_stopping", (255, 193,   7)),
        "unknown":  _rgb(cp, "color_unknown",  (255, 193,   7)),
    }
    theme_name             = _s(cp, "ui_theme", "dark")
    g["UI_THEME"]          = theme_name
    g["UI_COLOR"]          = dict(_THEMES.get(theme_name, _THEMES["dark"]))
    # ── Ollama GPU / performance env vars ──────────────────────────────────
    g["OLLAMA_MODELS_DIR"]        = _s(cp, "ollama_models_dir",        "")
    g["OLLAMA_NUM_GPU"]           = _s(cp, "ollama_num_gpu",            "")
    g["OLLAMA_FLASH_ATTENTION"]   = _s(cp, "ollama_flash_attention",    "0")
    g["OLLAMA_KV_CACHE_TYPE"]     = _s(cp, "ollama_kv_cache_type",      "f16")
    g["OLLAMA_NUM_PARALLEL"]      = _i(cp, "ollama_num_parallel",       1)
    g["OLLAMA_MAX_LOADED_MODELS"] = _i(cp, "ollama_max_loaded_models",  1)
    g["HSA_ENABLE_SDMA"]          = _s(cp, "hsa_enable_sdma",           "")
    g["PRELOAD_MODEL"]            = _s(cp, "preload_model",             "")
    g["AUTO_START"]               = _s(cp, "auto_start",               "false").lower() == "true"
    g["AUTO_RECOVER"]             = _s(cp, "auto_recover",              "false").lower() == "true"
    g["CHECK_FOR_UPDATES"]        = _s(cp, "check_for_updates",         "true").lower()  == "true"


# ── initial load ──────────────────────────────────────────────────────────────

def _init_default_config() -> Path | None:
    """Write default config.properties to the user config dir; return its path."""
    dest = Path.home() / ".ollama-tray" / "config.properties"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_DEFAULT_CONFIG_TEXT, encoding="utf-8")
        return dest
    except Exception:
        return None


_config_path: Path | None = _find_config()
_mtime:        float       = 0.0

_apply(_parse(""))  # populate defaults

if _config_path is None:
    _config_path = _init_default_config()

if _config_path:
    try:
        _apply(_parse(_config_path.read_text(encoding="utf-8")))
        _mtime = _config_path.stat().st_mtime
    except Exception:
        pass


# ── hot-reload ────────────────────────────────────────────────────────────────

_callbacks:       list[Callable[[], None]] = []
_watcher_started: bool                     = False
_watcher_lock:    threading.Lock           = threading.Lock()


def on_change(callback: Callable[[], None]) -> None:
    """Register a zero-argument callback invoked after every successful reload."""
    _callbacks.append(callback)


def reload() -> bool:
    """
    Re-read config.properties and update all module-level values.
    Calls all registered on_change callbacks afterwards.
    Returns True if the file was read successfully.
    """
    global _mtime
    if not _config_path or not _config_path.exists():
        return False
    try:
        text  = _config_path.read_text(encoding="utf-8")
        _apply(_parse(text))
        _mtime = _config_path.stat().st_mtime
    except Exception:
        return False
    for cb in list(_callbacks):
        try:
            cb()
        except Exception:
            pass
    return True


def set_theme(name: str) -> None:
    """Apply theme immediately and persist to config.properties when possible."""
    import re
    g = globals()
    g["UI_THEME"] = name
    g["UI_COLOR"] = dict(_THEMES.get(name, _THEMES["dark"]))
    if _config_path and _config_path.exists():
        try:
            text = _config_path.read_text(encoding="utf-8")
            if re.search(r"^ui_theme\s*=", text, re.MULTILINE):
                text = re.sub(r"^ui_theme\s*=.*$", f"ui_theme = {name}", text, flags=re.MULTILINE)
            else:
                text += f"\nui_theme = {name}\n"
            _config_path.write_text(text, encoding="utf-8")
        except Exception:
            pass
    for cb in list(_callbacks):
        try:
            cb()
        except Exception:
            pass


def build_serve_env() -> dict[str, str]:
    """Return an environment dict for `ollama serve` built from current config globals."""
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


def start_watcher() -> None:
    """Start watchdog observer for config.properties (idempotent, daemonic)."""
    global _watcher_started
    if not _config_path:
        return
    with _watcher_lock:
        if _watcher_started:
            return
        _watcher_started = True

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        _target = _config_path.resolve()

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if Path(event.src_path).resolve() == _target:
                    reload()

            def on_created(self, event):
                if Path(event.src_path).resolve() == _target:
                    reload()

        observer = Observer()
        observer.schedule(_Handler(), str(_config_path.parent), recursive=False)
        observer.daemon = True
        observer.start()
    except Exception:
        pass
