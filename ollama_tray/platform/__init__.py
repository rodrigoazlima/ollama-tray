import sys

if sys.platform == "win32":
    from ollama_tray.platform.windows import (
        init,
        get_status,
        service_label,
        service_action,
        cli_start,
        cli_stop,
        cli_restart,
        cli_status,
        cli_install,
        cli_uninstall,
    )
else:
    from ollama_tray.platform.linux import (
        init,
        get_status,
        service_label,
        service_action,
        cli_start,
        cli_stop,
        cli_restart,
        cli_status,
        cli_install,
        cli_uninstall,
    )
