import ctypes
import os
import sys
import time

import pywintypes
import win32service
import winreg

from ollama_tray.config import SERVICE_NAME, TASK_NAME
from ollama_tray.icon import set_icon_path

_OLLAMA_ICO = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Programs", "Ollama", "app.ico",
)

# win32 error codes used explicitly
_ERROR_ACCESS_DENIED          = 5
_ERROR_SERVICE_NOT_ACTIVE     = 1062
_ERROR_SERVICE_ALREADY_RUNNING = 1056
_ERROR_SERVICE_DOES_NOT_EXIST  = 1060


def init() -> None:
    set_icon_path(_OLLAMA_ICO if os.path.exists(_OLLAMA_ICO) else None)


def _scm(access: int = win32service.SC_MANAGER_CONNECT):
    return win32service.OpenSCManager(None, None, access)


def _svc(hscm, access: int):
    return win32service.OpenService(hscm, SERVICE_NAME, access)


def _with_svc(scm_access: int, svc_access: int):
    """Context manager yielding (hscm, hsvc), closing both on exit."""
    class _Ctx:
        def __enter__(self):
            self.hscm = _scm(scm_access)
            try:
                self.hsvc = _svc(self.hscm, svc_access)
            except Exception:
                win32service.CloseServiceHandle(self.hscm)
                raise
            return self.hscm, self.hsvc

        def __exit__(self, *_):
            try:
                win32service.CloseServiceHandle(self.hsvc)
            finally:
                win32service.CloseServiceHandle(self.hscm)

    return _Ctx()


def get_status() -> str:
    try:
        with _with_svc(win32service.SC_MANAGER_CONNECT,
                       win32service.SERVICE_QUERY_STATUS) as (_, hsvc):
            state = win32service.QueryServiceStatus(hsvc)[1]
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
    with _with_svc(win32service.SC_MANAGER_CONNECT,
                   win32service.SERVICE_START) as (_, hsvc):
        win32service.StartService(hsvc, None)


def _svc_stop() -> None:
    with _with_svc(win32service.SC_MANAGER_CONNECT,
                   win32service.SERVICE_STOP) as (_, hsvc):
        win32service.ControlService(hsvc, win32service.SERVICE_CONTROL_STOP)


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate(action: str) -> None:
    exe = sys.executable
    if getattr(sys, "frozen", False):
        args = f"--{action}"
    else:
        script = os.path.abspath(sys.argv[0])
        args   = f'"{script}" --{action}'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 0)


def service_action(action: str) -> None:
    try:
        if action == "start":
            _svc_start()
        elif action == "stop":
            _svc_stop()
    except pywintypes.error as e:
        code = e.args[0]
        if code == _ERROR_ACCESS_DENIED:
            _elevate(action)
        elif code in (_ERROR_SERVICE_ALREADY_RUNNING, _ERROR_SERVICE_NOT_ACTIVE):
            pass  # already in target state — not an error
        elif code == _ERROR_SERVICE_DOES_NOT_EXIST:
            from ollama_tray.checks import _show_warning
            _show_warning(
                "ollama-tray: service not found",
                f"'{SERVICE_NAME}' Windows service is not registered.\n"
                "Ensure Ollama is installed: https://ollama.com/download/windows",
            )


def _win_error_message(code: int) -> str:
    messages = {
        _ERROR_ACCESS_DENIED:           "Access denied — try running as administrator.",
        _ERROR_SERVICE_ALREADY_RUNNING: f"Service '{SERVICE_NAME}' is already running.",
        _ERROR_SERVICE_NOT_ACTIVE:      f"Service '{SERVICE_NAME}' is not running.",
        _ERROR_SERVICE_DOES_NOT_EXIST:  (
            f"Service '{SERVICE_NAME}' not found. "
            "Is Ollama installed? https://ollama.com/download/windows"
        ),
    }
    return messages.get(code, f"Windows error {code}")


def cli_start() -> int:
    try:
        _svc_start()
        print(f"Service '{SERVICE_NAME}' started.")
        return 0
    except pywintypes.error as e:
        print(f"Error: {_win_error_message(e.args[0])}", file=sys.stderr)
        return 1


def cli_stop() -> int:
    try:
        _svc_stop()
        print(f"Service '{SERVICE_NAME}' stopped.")
        return 0
    except pywintypes.error as e:
        print(f"Error: {_win_error_message(e.args[0])}", file=sys.stderr)
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
    exe = sys.executable
    if getattr(sys, "frozen", False):
        value = f'"{exe}"'
    else:
        script = os.path.abspath(sys.argv[0])
        value  = f'"{exe}" "{script}"'
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, TASK_NAME, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
    except OSError as e:
        print(f"Error: could not write autostart registry key: {e}", file=sys.stderr)
        return 1
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
    except OSError as e:
        print(f"Error: could not modify autostart registry key: {e}", file=sys.stderr)
        return 1
    return 0
