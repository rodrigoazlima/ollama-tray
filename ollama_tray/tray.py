import threading
import time
import webbrowser

import pystray
from pystray import MenuItem as item, Menu

import ollama_tray.config as _cfg
from ollama_tray.dialog import open_resource_dialog
from ollama_tray.settings_dialog import open_settings_dialog
from ollama_tray.icon import make_icon
from ollama_tray.stats import _fmt_bytes, current_stats, refresh_stats


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
        from ollama_tray.platform import service_action
        threading.Thread(target=service_action, args=("start",), daemon=True).start()

    def _stop(self, *_):
        from ollama_tray.platform import service_action
        threading.Thread(target=service_action, args=("stop",), daemon=True).start()

    def _restart(self, *_):
        from ollama_tray.platform import service_action
        def _do():
            service_action("stop")
            time.sleep(3)
            service_action("start")
        threading.Thread(target=_do, daemon=True).start()

    def _open_browser(self, *_):
        webbrowser.open(_cfg.OLLAMA_URL)

    def _toggle_dialog(self, *_):
        open_resource_dialog()

    def _exit(self, *_):
        if self._icon:
            self._icon.stop()

    def _open_settings(self, *_):
        open_settings_dialog()

    def _set_theme(self, name: str, *_) -> None:
        _cfg.set_theme(name)

    def _on_config_change(self) -> None:
        from ollama_tray.icon import invalidate_cache
        invalidate_cache()
        if self._icon:
            with self._lock:
                self._icon.icon  = make_icon(self._status)
                self._icon.title = f"Ollama — {self._status.capitalize()}"

    def _poll(self):
        from ollama_tray.platform import get_status, service_action
        _prev_cpu:   float = -1.0
        _prev_procs: int   = -1
        while True:
            time.sleep(_cfg.STATS_INTERVAL)
            self._tick += 1

            s = refresh_stats()

            status_changed = False
            if self._tick % _cfg.STATUS_INTERVAL == 0:
                new = get_status()
                with self._lock:
                    if new != self._status:
                        if _cfg.AUTO_RECOVER and new == "stopped":
                            threading.Thread(
                                target=service_action, args=("start",), daemon=True
                            ).start()
                        self._status = new
                        status_changed = True
                        if self._icon:
                            self._icon.icon  = make_icon(new)
                            self._icon.title = f"Ollama — {new.capitalize()}"

            # Only rebuild the tray menu when something visible changed.
            stats_changed = (
                abs(s.cpu_pct - _prev_cpu) >= 0.5
                or s.num_procs != _prev_procs
            )
            if (stats_changed or status_changed) and self._icon:
                _prev_cpu   = s.cpu_pct
                _prev_procs = s.num_procs
                try:
                    self._icon.update_menu()
                except Exception:
                    pass

    def run(self):
        import sys
        from ollama_tray.platform import get_status, init as platform_init, service_label
        platform_init()
        self._status = get_status()
        refresh_stats()

        lbl = service_label()

        theme_menu = Menu(
            *(item(name.capitalize(), lambda *_, n=name: self._set_theme(n))
              for name in _cfg.AVAILABLE_THEMES)
        )

        menu = Menu(
            item(self._stats_label, self._toggle_dialog, default=True),
            Menu.SEPARATOR,
            item(f"Start {lbl}",   self._start),
            item(f"Stop {lbl}",    self._stop),
            item(f"Restart {lbl}", self._restart),
            Menu.SEPARATOR,
            item("Open in Browser", self._open_browser),
            item("Theme",           theme_menu),
            item("Settings…",       self._open_settings),
            Menu.SEPARATOR,
            item("Exit",            self._exit),
        )
        self._icon = pystray.Icon(
            "ollama",
            make_icon(self._status),
            f"Ollama — {self._status.capitalize()}",
            menu=menu,
        )
        _cfg.on_change(self._on_config_change)
        _cfg.start_watcher()
        threading.Thread(target=self._poll, daemon=True).start()
        try:
            self._icon.run()
        except Exception as exc:
            from ollama_tray.checks import _show_fatal
            _show_fatal(
                "ollama-tray: tray backend error",
                f"Failed to start system tray icon:\n{exc}\n\n"
                + (
                    "On Linux, ensure system tray libraries are installed:\n"
                    "  sudo apt install gir1.2-ayatanaappindicator3-0.1 python3-gi"
                    if sys.platform != "win32"
                    else ""
                ),
            )
            sys.exit(1)
