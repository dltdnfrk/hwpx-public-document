from __future__ import annotations

import json
import posixpath
import secrets
import subprocess
import threading
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .bridge import error_event
from .paths import RESOURCES
from .state import StudioState


MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/vnd.microsoft.icon",
    ".webmanifest": "application/manifest+json",
    ".woff2": "font/woff2",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".hwpx": "application/hwp+zip",
    ".hwp": "application/x-hwp",
    ".md": "text/markdown; charset=utf-8",
}


def safe_resource(path: str) -> Path | None:
    relative = posixpath.normpath(unquote(path).lstrip("/"))
    if relative in {"", "."}:
        relative = "Studio/index.html"
    if relative.startswith("downloads/"):
        return None
    candidate = (RESOURCES / relative).resolve()
    try:
        candidate.relative_to(RESOURCES.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "PublicDocumentWeb/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/Studio", "/Studio/"}:
            self.send_response(302)
            self.send_header("Location", "/Studio/index.html")
            self.end_headers()
            return
        if parsed.path.startswith("/downloads/"):
            self._send_download(parsed.path)
            return
        resource = safe_resource(parsed.path)
        if resource is None:
            self.send_error(404, "Not Found")
            return
        data = resource.read_bytes()
        if resource.name == "index.html" and resource.parent.name == "Studio":
            data = data.replace(b"connect-src 'none'", b"connect-src 'self'")
        self.send_response(200)
        self.send_header("Content-Type", MIME_TYPES.get(resource.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        import public_document_web as package

        path = urlparse(self.path).path
        if path == "/api/bootstrap":
            self._bootstrap_bridge()
            return
        if path != "/api/bridge":
            self.send_error(404, "Not Found")
            return
        if not self._bridge_authorized():
            self._send_json(403, {"events": [error_event("로컬 Studio 세션을 확인할 수 없습니다.")]})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 2_000_000:
            self._send_json(400, {"events": [error_event("요청 본문 크기가 올바르지 않습니다.")]})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            events = package.handle_bridge(self._studio_server.state, body)
            self._send_json(200, {"events": events})
        except Exception as error:  # noqa: BLE001 - local host returns the failure to Studio
            message = str(error) if not isinstance(error, subprocess.SubprocessError) else "AI 제공자 작업을 완료하지 못했습니다."
            self._send_json(400, {"events": [error_event(message)]})

    def do_OPTIONS(self) -> None:
        self._send_json(403, {"events": [error_event("교차 출처 요청은 허용되지 않습니다.")]})

    def _send_download(self, path: str) -> None:
        relative = posixpath.normpath(unquote(path).lstrip("/"))
        candidate = (self._studio_server.state.data_dir / relative).resolve()
        try:
            candidate.relative_to(self._studio_server.state.downloads.resolve())
        except ValueError:
            self.send_error(404, "Not Found")
            return
        if not candidate.is_file():
            self.send_error(404, "Not Found")
            return
        data = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME_TYPES.get(candidate.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{candidate.name}"')
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _bootstrap_bridge(self) -> None:
        server = self._studio_server
        if self.headers.get("Host") not in server.allowed_hosts:
            self._send_json(403, {"error": "invalid bootstrap"})
            return
        if self.headers.get("Origin") not in server.allowed_origins:
            self._send_json(403, {"error": "invalid bootstrap"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 4096:
            self._send_json(400, {"error": "invalid bootstrap"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "invalid bootstrap"})
            return
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        existing_session = cookie.get("PublicDocumentSession")
        session_token = server.resume_or_consume_bootstrap(
            candidate=str(payload.get("token") or ""),
            existing_session=existing_session.value if existing_session is not None else None,
        )
        if session_token is None:
            self._send_json(403, {"error": "invalid bootstrap"})
            return
        data = json.dumps({"sessionToken": session_token}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Set-Cookie",
            f"PublicDocumentSession={session_token}; HttpOnly; SameSite=Strict; Path=/",
        )
        self.end_headers()
        self.wfile.write(data)

    def _bridge_authorized(self) -> bool:
        session_token = self._studio_server.session_token
        if session_token is None:
            return False
        if self.headers.get("Host") not in self._studio_server.allowed_hosts:
            return False
        if self.headers.get("Origin") not in self._studio_server.allowed_origins:
            return False
        if self.headers.get("X-Public-Document-Session") != session_token:
            return False
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("PublicDocumentSession")
        return morsel is not None and morsel.value == session_token

    @property
    def _studio_server(self) -> "StudioServer":
        assert isinstance(self.server, StudioServer)
        return self.server

    def log_message(self, format: str, *args: object) -> None:
        return


class StudioServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], state: StudioState) -> None:
        super().__init__(address, StudioHandler)
        self.state = state
        self.bootstrap_token = secrets.token_urlsafe(32)
        self.session_token: str | None = None
        self._bootstrap_lock = threading.Lock()
        port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.allowed_origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    def resume_or_consume_bootstrap(
        self,
        candidate: str,
        existing_session: str | None,
    ) -> str | None:
        with self._bootstrap_lock:
            if self.session_token is not None and existing_session is not None:
                if secrets.compare_digest(existing_session, self.session_token):
                    return self.session_token
            if not self.bootstrap_token or not secrets.compare_digest(candidate, self.bootstrap_token):
                return None
            self.bootstrap_token = ""
            self.session_token = secrets.token_urlsafe(32)
            return self.session_token


def serve(host: str, port: int, data_dir: Path, open_browser: bool) -> StudioServer:
    server = StudioServer((host, port), StudioState(data_dir))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{host}:{server.server_address[1]}/Studio/index.html"
    if open_browser:
        webbrowser.open(f"{url}#bridge-bootstrap={server.bootstrap_token}")
    return server
