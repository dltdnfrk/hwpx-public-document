from __future__ import annotations

import argparse
import threading
from pathlib import Path

from .paths import DEFAULT_HOST, DEFAULT_PORT


def main() -> None:
    import public_document_web as package

    parser = argparse.ArgumentParser(description="문서작성기 로컬 웹앱")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--data-dir",
        default=str(Path.home() / ".public-document-studio"),
    )
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("로컬 웹앱은 127.0.0.1에서만 엽니다.")
    server = package.serve(args.host, args.port, Path(args.data_dir), open_browser=not args.no_open)
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    url = f"http://{host}:{port}/Studio/index.html"
    if args.no_open:
        url += f"#bridge-bootstrap={server.bootstrap_token}"
    print(url, flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
