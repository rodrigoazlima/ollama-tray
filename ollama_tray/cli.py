import argparse
import sys


def main() -> None:
    p = argparse.ArgumentParser(description="Ollama system tray manager")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--start",     action="store_true")
    g.add_argument("--stop",      action="store_true")
    g.add_argument("--restart",   action="store_true")
    g.add_argument("--status",    action="store_true")
    g.add_argument("--install",   action="store_true")
    g.add_argument("--uninstall", action="store_true")
    args = p.parse_args()

    from ollama_tray import platform as _plat

    for name, fn in {
        "start":     _plat.cli_start,
        "stop":      _plat.cli_stop,
        "restart":   _plat.cli_restart,
        "status":    _plat.cli_status,
        "install":   _plat.cli_install,
        "uninstall": _plat.cli_uninstall,
    }.items():
        if getattr(args, name):
            _plat.init()
            sys.exit(fn())

    from ollama_tray.tray import OllamaTray
    OllamaTray().run()
