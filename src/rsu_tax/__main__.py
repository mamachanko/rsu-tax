"""Entry point: launches the web server and opens the browser."""

from __future__ import annotations

import sys
import threading
import time
import webbrowser


def main() -> None:
    import uvicorn

    host = "127.0.0.1"
    port = 8765

    def open_browser() -> None:
        time.sleep(0.8)
        webbrowser.open(f"http://{host}:{port}")

    threading.Thread(target=open_browser, daemon=True).start()

    print(f"RSU Tax Calculator → http://{host}:{port}")
    print("Press Ctrl+C to stop.")

    uvicorn.run(
        "rsu_tax.app:app",
        host=host,
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    sys.exit(main())
