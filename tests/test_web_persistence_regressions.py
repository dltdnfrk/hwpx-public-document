from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

import public_document_web.bridge as bridge_module
import public_document_web.native as native_module
from public_document_web.bridge import handle_bridge
from public_document_web.http import serve
from public_document_web.state import StudioState


def _project(title: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "documentID": "document-persistence-regression",
        "title": title,
        "currentRevisionID": "revision-1",
        "elements": [],
        "assets": [],
        "styles": [],
        "templateBinding": {},
        "evidenceLinks": [],
        "revisions": [],
        "history": [],
    }


def _bootstrap(server: Any, origin: str) -> str:
    request = Request(
        f"{origin}/api/bootstrap",
        data=json.dumps({"token": server.bootstrap_token}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return str(json.loads(response.read())["sessionToken"])


def _download_request(url: str, session: str | None = None) -> Request:
    headers = {}
    if session is not None:
        headers["Cookie"] = f"PublicDocumentSession={session}"
    return Request(url, headers=headers)


def _stop(server: Any) -> None:
    server.shutdown()
    server.server_close()


def test_atomic_write_failure_preserves_published_project_and_cleans_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = StudioState(tmp_path / "data")
    state.project_file.write_text('{"title":"published"}\n', encoding="utf-8")

    def fail_publish(source: str | bytes | os.PathLike[str], destination: str | bytes | os.PathLike[str]) -> None:
        del source, destination
        raise OSError("injected publication failure")

    monkeypatch.setattr(os, "replace", fail_publish)

    with pytest.raises(OSError, match="injected publication failure"):
        state.write_json(state.project_file, _project("replacement"))

    assert json.loads(state.project_file.read_text(encoding="utf-8")) == {
        "title": "published"
    }
    assert list(state.data_dir.glob(f".{state.project_file.name}.*.tmp")) == []


@pytest.mark.parametrize(
    "corrupt_bytes",
    [b'{"schemaVersion":1,"title":', b"[]"],
    ids=["truncated-json", "non-object-json"],
)
def test_ready_quarantines_malformed_recovery_and_opens_canonical_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corrupt_bytes: bytes,
) -> None:
    state = StudioState(tmp_path / "data")
    state.write_json(state.project_file, _project("canonical"))
    state.recovery_file.write_bytes(corrupt_bytes)
    monkeypatch.setattr(bridge_module, "run_ai_bridge", lambda _message: {"events": []})

    events = handle_bridge(state, {"action": "ready"})

    opened = next(entry for entry in events if entry["event"] == "opened")
    assert opened["payload"]["project"]["title"] == "canonical"
    assert not state.recovery_file.exists()
    corrupt = state.data_dir / "recovery.json.corrupt"
    assert corrupt.read_bytes() == corrupt_bytes
    assert json.loads(state.project_file.read_text(encoding="utf-8"))["title"] == "canonical"


def test_invalid_export_formats_do_not_persist_submitted_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = StudioState(tmp_path / "data")
    state.write_json(state.project_file, _project("canonical"))

    def unexpected_export(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("native export must not run")

    monkeypatch.setattr(bridge_module, "export_project", unexpected_export)

    events = handle_bridge(
        state,
        {"action": "export", "project": _project("rejected"), "formats": ["unknown"]},
    )

    assert events == [
        {
            "event": "error",
            "payload": {"message": "내보낼 형식을 하나 이상 선택하세요."},
        }
    ]
    assert state.load_json(state.project_file)["title"] == "canonical"


def test_export_timeout_cleans_scratch_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Path] = []
    original_mkdtemp = native_module.tempfile.mkdtemp

    def tracked_mkdtemp(*args: Any, **kwargs: Any) -> str:
        positional = list(args)
        if len(positional) >= 3:
            positional[2] = tmp_path
        else:
            kwargs["dir"] = tmp_path
        path = Path(original_mkdtemp(*positional, **kwargs))
        created.append(path)
        return str(path)

    def timeout(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("export", 90)

    monkeypatch.setattr(native_module.tempfile, "mkdtemp", tracked_mkdtemp)
    monkeypatch.setattr(native_module, "resolve_app_binary", lambda: Path("/unused/exporter"))
    monkeypatch.setattr(native_module.subprocess, "run", timeout)

    with pytest.raises(RuntimeError, match="내보내기가 응답하지 않아 중단했습니다"):
        native_module.export_project(_project("scratch"), ["docx"], False, tmp_path / "downloads")

    assert len(created) == 1
    assert all(not path.exists() for path in created)


def test_download_requires_current_session_and_old_session_is_rejected(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    first = serve("127.0.0.1", 0, data_dir, open_browser=False)
    first_origin = f"http://127.0.0.1:{first.server_address[1]}"
    relative = "downloads/operation/document.md"
    artifact = data_dir / relative
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"download-body")
    korean_name = "공공문서.md"
    korean_artifact = artifact.with_name(korean_name)
    korean_artifact.write_bytes(b"korean-download-body")
    url = f"{first_origin}/{relative}"
    korean_url = f"{first_origin}/downloads/operation/{quote(korean_name)}"

    try:
        with pytest.raises(HTTPError) as unauthenticated:
            urlopen(_download_request(url), timeout=5)
        assert unauthenticated.value.code == 403
        unauthenticated_body = unauthenticated.value.read()

        session = _bootstrap(first, first_origin)
        with urlopen(_download_request(url, session), timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "text/markdown; charset=utf-8"
            assert response.headers["Content-Disposition"] == 'attachment; filename="document.md"'
            assert response.read() == b"download-body"

        with urlopen(_download_request(korean_url, session), timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "text/markdown; charset=utf-8"
            assert response.headers["Content-Disposition"] == (
                'attachment; filename="download.md"; '
                "filename*=UTF-8''%EA%B3%B5%EA%B3%B5%EB%AC%B8%EC%84%9C.md"
            )
            assert response.read() == b"korean-download-body"

        bad_host_request = _download_request(url, session)
        bad_host_request.add_unredirected_header("Host", "evil.example")
        with pytest.raises(HTTPError) as bad_host:
            urlopen(bad_host_request, timeout=5)
        assert bad_host.value.code == 403
        assert b"Forbidden" in bad_host.value.read()

        malformed_cookie = Request(
            url,
            headers={"Cookie": 'PublicDocumentSession="unterminated'},
        )
        with pytest.raises(HTTPError) as malformed:
            urlopen(malformed_cookie, timeout=5)
        assert malformed.value.code == 403
        assert b"Forbidden" in malformed.value.read()
    finally:
        _stop(first)

    second = serve("127.0.0.1", 0, data_dir, open_browser=False)
    second_origin = f"http://127.0.0.1:{second.server_address[1]}"
    old_url = f"{second_origin}/{relative}"
    try:
        with pytest.raises(HTTPError) as old_session:
            urlopen(_download_request(old_url, session), timeout=5)
        assert old_session.value.code == 403
        old_session_body = old_session.value.read()
    finally:
        _stop(second)

    assert b"Forbidden" in unauthenticated_body
    assert b"Forbidden" in old_session_body
