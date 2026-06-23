import ctypes
import os
import sys
import time

import pywintypes
import win32service
import winreg

from ollama_tray.icon import set_icon_path

SERVICE_NAME = "Ollama"
TASK_NAME    = "OllamaTray"

_OLLAMA_ICO = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Programs", "Ollama", "app.ico",
)


def init() -> None:
    set_icon_path(_OLLAMA_ICO if os.path.exists(_OLLAMA_ICO) else None)


def _scm(access: int = win32service.SC_MANAGER_CONNECT):
    return win32service.OpenSCManager(None, None, access)


def _svc(hscm, access: int):
    return win32service.OpenService(hscm, SERVICE_NAME, access)


def get_status() -> str:
    try:
        hscm = _scm()
        hsvc = _svc(hscm, win32service.SERVICE_QUERY_STATUS)
        try:
            state = win32service.QueryServiceStatus(hsvc)[1]
        finally:
            win32service.CloseServiceHandle(hsvc)
            win32service.CloseServiceHandle(hscm)
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
    hscm = _scm(win32service.SC_MANAGER_CONNECT)
    hsvc = _svc(hscm, win32service.SERVICE_START)
    try:
        win32service.StartService(hsvc, None)
    finally:
        win32service.CloseServiceHandle(hsvc)
        win32service.CloseServiceHandle(hscm)


def _svc_stop() -> None:
    hscm = _scm(win32service.SC_MANAGER_CONNECT)
    hsvc = _svc(hscm, win32service.SERVICE_STOP)
    try:
        win32service.ControlService(hsvc, win32service.SERVICE_CONTROL_STOP)
    finally:
        win32service.CloseServiceHandle(hsvc)
        win32service.CloseServiceHandle(hscm)


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
        if e.args[0] == 5:  # ERROR_ACCESS_DENIED
            _elevate(action)


def cli_start() -> int:
    try:
        _svc_start()
        print(f"Service '{SERVICE_NAME}' started.")
        return 0
    except pywintypes.error as e:
        print(f"Error: {e}")
        return 1


def cli_stop() -> int:
    try:
        _svc_stop()
        print(f"Service '{SERVICE_NAME}' stopped.")
        return 0
    except pywintypes.error as e:
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
    print(f"Ollama service: {st}")
    return 0 if st == "running" else 1


def cli_install() -> int:
    exe = sys.executable
    if getattr(sys, "frozen", False):
        value = f'"{exe}"'
    else:
        script = os.path.abspath(sys.argv[0])
        value  = f'"{exe}" "{script}"'
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, TASK_NAME, 0, winreg.REG_SZ, value)
    winreg.CloseKey(key)
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
    return 0
