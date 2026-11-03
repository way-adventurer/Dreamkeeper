"""Double-click entry point for the Dreamkeeper Windows desktop build."""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from urllib.request import urlopen

from runrelay.config import state_dir
from runrelay.service import RunRelayService
from runrelay.web import serve


def main() -> None:
    if "--dreamkeeper-daemon" in sys.argv:
        home = None
        interval = 5.0
        if "--home" in sys.argv:
            home = sys.argv[sys.argv.index("--home") + 1]
        if "--interval" in sys.argv:
            interval = float(sys.argv[sys.argv.index("--interval") + 1])
        RunRelayService(state_dir(home)).daemon(interval)
        return

    host = os.environ.get("DREAMKEEPER_HOST", "127.0.0.1")
    port = int(os.environ.get("DREAMKEEPER_PORT", "8765"))
    url = f"http://{host}:{port}"

    # Reuse the running server, but still open its page on every double-click.
    try:
        with urlopen(url, timeout=0.35):  # noqa: S310
            pass
    except Exception:
        pass
    else:
        webbrowser.open(url)
        return

    service = RunRelayService(state_dir())

    # Open the page once the HTTP listener accepts requests. Startup time varies
    # on slower Windows machines and with a cold PyInstaller extraction.
    def open_dashboard() -> None:
        for _ in range(40):
            try:
                with urlopen(url, timeout=0.35):  # noqa: S310
                    pass
            except Exception:
                time.sleep(0.25)
            else:
                webbrowser.open(url)
                return

    threading.Thread(target=open_dashboard, daemon=True).start()
    serve(service, host, port)


if __name__ == "__main__":
    main()
