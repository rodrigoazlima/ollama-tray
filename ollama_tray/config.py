"""
Loads config.properties, exposes typed configuration values,
and hot-reloads when the file changes on disk via watchdog.

Search order for config.properties:
  1. Directory of the frozen executable (PyInstaller builds)
  2. Repository / install root  (two levels above this file)
  3. User config dir:
       Windows → %APPDATA%\\OllamaTray\\config.properties
       Linux   → ~/.config/ollama-tray/config.properties
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
    if sys.platform == "win32":
        candidates.append(
            Path(os.environ.get("APPDATA", "~")) / "OllamaTray" / "config.properties"
        )
    else:
        candidates.append(
            Path.home() / ".config" / "ollama-tray" / "config.properties"
        )
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


# ── initial load ──────────────────────────────────────────────────────────────

_config_path: Path | None = _find_config()
_mtime:        float       = 0.0

_apply(_parse(""))  # populate defaults

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
