from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / ".build" / "debug" / "PublicDocumentApp"


class _ProbeHandler(BaseHTTPRequestHandler):
    requests: list[str] = []

    def do_GET(self) -> None:
        self.requests.append(self.path)
        body = b"window.networkSubresourceExecuted = true;"
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_native_host_loads_genoffice_sibling_and_denies_network(tmp_path: Path) -> None:
    resources = tmp_path / "Resources"
    studio = resources / "Studio"
    genoffice = resources / "GenOffice"
    studio.mkdir(parents=True)
    genoffice.mkdir()
    (genoffice / "public-document-genoffice.js").write_text(
        "window.genOfficeSiblingReady = true;",
        encoding="utf-8",
    )

    _ProbeHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    network_script = f"http://127.0.0.1:{server.server_port}/network-probe.js"
    websocket_probe = f"ws://127.0.0.1:{server.server_port}/websocket-probe"
    html = "\n".join(
        [
            "<!doctype html>",
            "<html>",
            "<body>",
            "  <script>window.networkSubresourceExecuted = false;</script>",
            f'  <script>new WebSocket("{websocket_probe}");</script>',
            f'  <script src="{network_script}"></script>',
            '  <script src="../GenOffice/public-document-genoffice.js"></script>',
            "  <script>",
            '    window.addEventListener("load", () => {',
            "      setTimeout(() => window.webkit.messageHandlers.hostSecurityProbe.postMessage({",
            "        siblingReady: window.genOfficeSiblingReady === true,",
            "        networkExecuted: window.networkSubresourceExecuted === true",
            "      }), 100);",
            "    });",
            "  </script>",
            "</body>",
            "</html>",
        ]
    )
    (studio / "index.html").write_text(html, encoding="utf-8")

    try:
        completed = subprocess.run(
            [str(BINARY), "--studio-host-security-self-test", str(resources)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=25,
        )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout)
    assert receipt["status"] == "PASS"
    assert Path(receipt["readAccessRoot"]).samefile(resources)
    assert receipt["siblingResourceLoaded"] is True
    assert receipt["contentRuleListInstalled"] is True
    assert receipt["networkSubresourceExecuted"] is False
    assert receipt["allowedNavigationSchemes"] == ["file", "about"]
    assert receipt["blockedNetworkSchemes"] == ["http", "https", "ws", "wss"]
    assert receipt["escapedFileNavigationBlocked"] is True
    assert _ProbeHandler.requests == []


def test_production_host_uses_common_resources_root_and_keeps_bridge() -> None:
    source = (ROOT / "Sources/PublicDocumentApp/main.swift").read_text(encoding="utf-8")

    assert "allowingReadAccessTo: studioResources.readAccessRoot" in source
    assert 'appendingPathComponent("Resources", isDirectory: true)' in source
    assert 'appendingPathComponent("Studio/index.html")' in source
    assert 'configuration.userContentController.add(self, name: "projectStore")' in source
    assert 'encodedContentRuleList: encodedContentRuleList' in source
    assert '"url-filter": "^https?://"' in source
    assert '"url-filter": "^wss?://"' in source
