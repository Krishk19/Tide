import argparse
import socket
import threading
import webbrowser
from pathlib import Path

import uvicorn

from tide_server.app import create_app
from tide_server.config import Settings


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="tide-server", description="Tide teacher server + console")
    ap.add_argument("--demo", action="store_true", help="seed a demo exam and 59 simulated seats")
    ap.add_argument("--port", type=int)
    ap.add_argument("--data", type=Path, help="data folder (default ./tide-data)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    overrides = {k: v for k, v in {"demo": args.demo or None, "port": args.port,
                                   "data_dir": args.data}.items() if v is not None}
    settings = Settings(**overrides)
    app = create_app(settings)
    mode = "Jev via OpenRouter" if settings.openrouter_api_key else "offline heuristics (no OPENROUTER_API_KEY)"
    print(f"\n  Tide console  http://{lan_ip()}:{settings.port}   PIN {settings.teacher_pin}"
          f"\n  Classifier    {mode}\n  Demo mode     {'on' if settings.demo else 'off'}\n", flush=True)
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [f"http://localhost:{settings.port}"]).start()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
