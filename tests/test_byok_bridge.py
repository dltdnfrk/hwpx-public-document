from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import public_document_web as webapp


def _server(tmp_path: Path) -> tuple[webapp.StudioServer, str]:
    server = webapp.serve("127.0.0.1", 0, tmp_path / "data", open_browser=False)
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _bootstrap(server: webapp.StudioServer, origin: str) -> str:
    request = Request(
        f"{origin}/api/bootstrap",
        data=json.dumps({"token": server.bootstrap_token}).encode(),
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    with urlopen(request) as response:
        return str(json.loads(response.read())["sessionToken"])


def _request(origin: str, token: str, payload: dict[str, Any], request_origin: str | None = None) -> Request:
    return Request(
        f"{origin}/api/bridge",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Origin": request_origin or origin,
            "Cookie": f"PublicDocumentSession={token}",
            "X-Public-Document-Session": token,
        },
        method="POST",
    )


def test_bridge_requires_host_origin_cookie_and_session(tmp_path: Path) -> None:
    server, origin = _server(tmp_path)
    try:
        with pytest.raises(HTTPError) as missing:
            urlopen(Request(
                f"{origin}/api/bridge",
                data=b'{"action":"ready"}',
                headers={"Content-Type": "application/json"},
                method="POST",
            ))
        assert missing.value.code == 403
        token = _bootstrap(server, origin)
        with pytest.raises(HTTPError) as wrong_origin:
            urlopen(_request(origin, token, {"action": "ready"}, "http://evil.example"))
        assert wrong_origin.value.code == 403
    finally:
        server.shutdown()


def test_index_does_not_disclose_bridge_credentials(tmp_path: Path) -> None:
    server, origin = _server(tmp_path)
    try:
        with urlopen(f"{origin}/Studio/index.html") as response:
            html = response.read().decode()
            cookie = response.headers.get("Set-Cookie")
        assert 'name="public-document-session"' not in html
        assert cookie is None
    finally:
        server.shutdown()


def test_bridge_bootstrap_token_is_required_and_single_use(tmp_path: Path) -> None:
    server, origin = _server(tmp_path)
    request = Request(
        f"{origin}/api/bootstrap",
        data=json.dumps({"token": server.bootstrap_token}).encode(),
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    try:
        with urlopen(request) as response:
            payload = json.loads(response.read())
            cookie = response.headers["Set-Cookie"]
        assert payload["sessionToken"]
        assert "PublicDocumentSession=" in cookie
        resume = Request(
            f"{origin}/api/bootstrap",
            data=b'{"token":""}',
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "Cookie": cookie.split(";", 1)[0],
            },
            method="POST",
        )
        with urlopen(resume) as response:
            resumed = json.loads(response.read())
        assert resumed["sessionToken"] == payload["sessionToken"]
        with pytest.raises(HTTPError) as replay:
            urlopen(request)
        assert replay.value.code == 403
    finally:
        server.shutdown()


def test_web_byok_forwards_to_swift_without_persisting_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, origin = _server(tmp_path)
    captured: list[dict[str, Any]] = []
    sentinel = "BYOK-BRIDGE-SENTINEL"

    def fake_bridge(message: dict[str, Any]) -> dict[str, Any]:
        captured.append(message)
        return {
            "events": [{
                "event": "aiSettingsSaved",
                "payload": {"settings": {
                    "activeProvider": "openai",
                    "providers": [{
                        "provider": "openai",
                        "endpointIdentity": "https://api.openai.com/v1",
                        "model": "gpt-5-mini",
                        "hasSecret": True,
                        "hostDisclosure": "api.openai.com",
                    }],
                    "catalog": [],
                }},
            }],
        }

    monkeypatch.setattr(webapp, "run_ai_bridge", fake_bridge)
    try:
        token = _bootstrap(server, origin)
        payload = {
            "action": "configureAISettings",
            "provider": "openai",
            "endpointIdentity": "https://api.openai.com/v1",
            "model": "gpt-5-mini",
            "secret": sentinel,
        }
        with urlopen(_request(origin, token, payload)) as response:
            result = json.loads(response.read())
        assert result["events"][0]["event"] == "aiSettingsSaved"
        assert captured == [payload]
        assert sentinel not in "\n".join(
            path.read_text(errors="ignore")
            for path in server.state.data_dir.rglob("*")
            if path.is_file()
        )
    finally:
        server.shutdown()
