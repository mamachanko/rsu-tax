"""Entry point: launches the web server, or runs CLI sub-commands."""

from __future__ import annotations

import sys
import threading
import time
import webbrowser


def _serve() -> None:
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


def _anonymize(args: list[str]) -> None:
    import argparse
    import os

    from .anonymize import AnonConfig, anonymize_file

    parser = argparse.ArgumentParser(
        prog="rsu-tax anonymize",
        description="Anonymize Schwab CSV exports for safe sharing and testing.",
    )
    parser.add_argument("file", help="Path to the CSV file to anonymize")
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: <input>-anonymized.csv)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible output",
    )
    opts = parser.parse_args(args)

    if not os.path.isfile(opts.file):
        print(f"Error: file not found: {opts.file}", file=sys.stderr)
        sys.exit(1)

    if opts.output:
        output_path = opts.output
    else:
        base, ext = os.path.splitext(opts.file)
        output_path = f"{base}-anonymized{ext}"

    config = AnonConfig(seed=opts.seed)
    anonymize_file(opts.file, output_path, config)
    print(f"Anonymized → {output_path}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "anonymize":
        _anonymize(sys.argv[2:])
    else:
        _serve()


if __name__ == "__main__":
    sys.exit(main())
