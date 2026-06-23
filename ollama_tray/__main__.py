from ollama_tray._startup import redirect_frozen_streams

redirect_frozen_streams()

from ollama_tray.cli import main  # noqa: E402

main()
