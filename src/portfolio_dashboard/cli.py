from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

from portfolio_core import PortfolioContext, save_data_directory, validate_data_workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or configure the local portfolio dashboard")
    parser.add_argument("command", nargs="?", choices=("serve", "configure"), default="serve")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser window")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "configure":
        if args.data_dir is None:
            raise SystemExit("configure requires --data-dir")
        validate_data_workspace(args.data_dir)
        config_path = save_data_directory(args.data_dir)
        print(f"Saved portfolio data directory in {config_path}")
        return

    context = PortfolioContext.load(args.data_dir)
    validate_data_workspace(context.paths.root)

    import uvicorn

    from portfolio_dashboard.main import create_app

    url = f"http://127.0.0.1:{args.port}"
    if not args.no_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(context=context), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
