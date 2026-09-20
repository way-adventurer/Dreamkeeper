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

    # A second double-click should reuse the running dashboard instead of
    # opening another server/browser instance.
    try:
        with urlopen(url, timeout=0.35):  # noqa: S310
            return
    except Exception:
        pass

    service = RunRelayService(state_dir())

    # Start the browser just after the HTTP listener begins accepting requests.
    def open_dashboard() -> None:
        time.sleep(0.8)
        webbrowser.open(url)

    threading.Thread(target=open_dashboard, daemon=True).start()
    serve(service, host, port)


if __name__ == "__main__":
    main()
