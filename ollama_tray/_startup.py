import os
import sys


def redirect_frozen_streams(log_base: str | None = None) -> None:
    """
    When running as a PyInstaller windowed exe (console=False), stdout/stderr
    are invalid file descriptors that raise OSError on any write. Redirect both
    to a rolling log file so print() calls in CLI and startup-check code don't
    crash the process.
    """
    if not getattr(sys, "frozen", False):
        return
    try:
        sys.stdout.write("")
        sys.stderr.write("")
        # Streams writable but may use a narrow codec (e.g. cp1252).
        # Reconfigure both to UTF-8 so non-ASCII chars don't crash.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass
        return
    except (AttributeError, OSError):
        pass

    if log_base is None:
        log_base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    log_dir = os.path.join(log_base, "ollama-tray")
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, "ollama-tray.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = log
    sys.stderr = log
