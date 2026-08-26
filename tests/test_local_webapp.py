from __future__ import annotations

import json
import shutil
import subprocess
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

_SESSIONS: dict[str, str] = {}


def _start(tmp_path: Path):
    server = webapp.serve("127.0.0.1", 0, tmp_path / "data", open_browser=False)
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    request = Request(
        f"{origin}/api/bootstrap",
        data=json.dumps({"token": server.bootstrap_token}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    with urlopen(request) as response:
        _SESSIONS[origin] = str(json.loads(response.read())["sessionToken"])
    return server, origin


def _json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    origin = url.split("/api/", 1)[0]
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=_auth_headers(origin),
        method="POST",
    )
    with urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _auth_headers(origin: str) -> dict[str, str]:
    token = _SESSIONS[origin]
    return {
        "Content-Type": "application/json",
        "Origin": origin,
        "Cookie": f"PublicDocumentSession={token}",
        "X-Public-Document-Session": token,
    }


def _governed_project(title: str = "웹앱 제목") -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "documentID": "document-web-ai",
        "locale": "ko-KR",
        "title": title,
        "currentRevisionID": "revision-1",
        "elements": [{
            "elementID": "element-title",
            "kind": "heading",
            "order": 0,
            "text": title,
            "styleID": "style-title",
            "evidenceIDs": [],
        }],
        "assets": [],
        "styles": [],
        "templateBinding": {
            "templateID": "public-plan",
            "version": "3.2",
            "publishingAuthority": "기관 표준",
            "requiredSections": ["개요"],
            "checklistResults": {},
        },
        "evidenceLinks": [],
        "revisions": [],
        "history": [],
        "aiProposalHistory": [],
        "providerConfigurations": [],
        "consentGrants": [],
        "redoRevisionIDs": [],
    }


def test_local_webapp_serves_studio_and_allows_same_origin_api(tmp_path: Path) -> None:
    server, origin = _start(tmp_path)
    try:
        with urlopen(f"{origin}/Studio/index.html") as response:
            html = response.read().decode("utf-8")
        assert "connect-src 'self'" in html
        assert "connect-src 'none'" not in html
        with urlopen(f"{origin}/GenOffice/public-document-genoffice.js") as response:
            assert response.status == 200
        app = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "Resources" / "Studio").glob("*.js")))
        assert "fetch('/api/bridge'" in app
        assert "window.webkit.messageHandlers.projectStore" in app
    finally:
        server.shutdown()


def test_local_webapp_ready_save_and_reopen_use_signed_catalog(tmp_path: Path) -> None:
    server, origin = _start(tmp_path)
    try:
        ready = _json(f"{origin}/api/bridge", {"action": "ready"})
        events = {entry["event"]: entry["payload"] for entry in ready["events"]}
        catalog = events["templateCatalog"]["project"]
        assert {entry["documentType"] for entry in catalog["entries"]} == {
            "추진계획서",
            "기안문",
            "보고서",
            "결과보고서",
            "업무협조",
            "회의록",
        }
        assert events["empty"] == {}

        project = {
            "schemaVersion": 1,
            "documentID": "document-web",
            "locale": "ko-KR",
            "title": "웹앱 제목",
            "currentRevisionID": "revision-1",
            "elements": [{
                "elementID": "element-title",
                "kind": "heading",
                "order": 0,
                "text": "웹앱 제목",
                "styleID": "style-title",
                "evidenceIDs": [],
            }],
            "assets": [],
            "styles": [],
            "templateBinding": {
                "templateID": "public-plan",
                "version": "3.2",
                "publishingAuthority": "기관 표준",
                "requiredSections": ["개요"],
                "checklistResults": {},
            },
            "evidenceLinks": [],
            "revisions": [],
            "history": [],
            "aiProposalHistory": [],
            "providerConfigurations": [],
            "consentGrants": [],
            "redoRevisionIDs": [],
        }
        saved = _json(f"{origin}/api/bridge", {"action": "save", "project": project})
        assert saved["events"][0]["event"] == "saved"
        assert saved["events"][0]["payload"]["project"]["title"] == "기관 공식 제목을 사용하세요"
        assert saved["events"][0]["payload"]["officialRuleState"]["contentChanged"] is True

        reopened = _json(f"{origin}/api/bridge", {"action": "reopen"})
        assert reopened["events"][0]["payload"]["project"]["title"] == "기관 공식 제목을 사용하세요"
    finally:
        server.shutdown()


def test_web_ai_project_events_enforce_official_rules_before_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = webapp.StudioState(tmp_path / "data")

    def fake_bridge(message: dict[str, Any]) -> dict[str, Any]:
        return {
            "events": [{
                "event": "aiProposal",
                "payload": {"project": message["project"]},
            }],
        }

    monkeypatch.setattr(webapp, "run_ai_bridge", fake_bridge)
    events = webapp.handle_bridge(
        state,
        {
            "action": "requestAIProposal",
            "project": _governed_project(),
            "provider": "openai",
            "operation": "rewrite",
            "payloadScope": "whole-document",
            "consent": True,
        },
    )

    assert events[0]["payload"]["project"]["title"] == "기관 공식 제목을 사용하세요"
    assert state.load_json(state.project_file)["title"] == "기관 공식 제목을 사용하세요"


def test_ready_keeps_document_features_when_ai_settings_are_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = webapp.StudioState(tmp_path / "data")

    def unavailable_bridge(message: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("AI bridge unavailable")

    monkeypatch.setattr(webapp, "run_ai_bridge", unavailable_bridge)
    events = webapp.handle_bridge(state, {"action": "ready"})
    names = [entry["event"] for entry in events]

    assert "templateCatalog" in names
    assert "empty" in names
    assert "aiSettingsUnavailable" in names


def test_resolve_app_binary_uses_workspace_cli() -> None:
    binary = webapp.resolve_app_binary()
    assert binary == ROOT / ".build" / "debug" / "PublicDocumentApp"
    assert "Applications/PublicDocument.app" not in str(binary)


def test_local_web_main_supports_declared_python_38(tmp_path: Path) -> None:
    python38 = shutil.which("python3.8")
    if python38 is None:
        pytest.skip("python3.8 is not installed")
    script = (
        "import sys, threading\n"
        "import public_document_web as web\n"
        "class Server:\n"
        "    server_address = ('127.0.0.1', 8765)\n"
        "    bootstrap_token = 'python-38-bootstrap'\n"
        "    def shutdown(self): pass\n"
        "web.serve = lambda *args, **kwargs: Server()\n"
        "threading.Event.wait = lambda self: (_ for _ in ()).throw(KeyboardInterrupt())\n"
        f"sys.argv = ['public_document_web.py', '--data-dir', {str(tmp_path)!r}, '--no-open']\n"
        "web.main()\n"
    )
    completed = subprocess.run(
        [python38, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_local_webapp_persists_prefs_and_document_library(tmp_path: Path) -> None:
    server, origin = _start(tmp_path)
    try:
        ready = _json(f"{origin}/api/bridge", {"action": "ready"})
        events = {entry["event"]: entry["payload"] for entry in ready["events"]}
        assert events["studioPrefs"]["project"]["autosaveIntervalMs"] == 180000
        assert events["studioPrefs"]["project"]["favorites"] == []
        assert events["studioPrefs"]["project"]["myForms"] == []
        assert events["documentLibrary"]["project"]["entries"] == []

        saved_prefs = _json(
            f"{origin}/api/bridge",
            {
                "action": "saveStudioPrefs",
                "prefs": {
                    "autosaveIntervalMs": 60000,
                    "favorites": ["public-plan"],
                    "myForms": [{"id": "form-date", "name": "시행일", "text": "○ 시행일: "}],
                },
            },
        )
        prefs = saved_prefs["events"][0]["payload"]["project"]
        assert prefs["autosaveIntervalMs"] == 60000
        assert prefs["favorites"] == ["public-plan"]
        assert prefs["myForms"][0]["name"] == "시행일"

        rejected = _json(
            f"{origin}/api/bridge",
            {"action": "saveStudioPrefs", "prefs": {"autosaveIntervalMs": 12, "favorites": ["x" * 200]}},
        )
        assert rejected["events"][0]["payload"]["project"]["autosaveIntervalMs"] == 180000

        source = {
            "schemaVersion": 1,
            "documentID": "document-library-a",
            "locale": "ko-KR",
            "title": "취합 원본",
            "currentRevisionID": "revision-1",
            "elements": [{
                "elementID": "element-title",
                "kind": "heading",
                "order": 0,
                "text": "취합 원본",
                "styleID": "style-title",
                "evidenceIDs": [],
            }, {
                "elementID": "element-section-1-body",
                "kind": "paragraph",
                "order": 1,
                "text": "○ 결과",
                "styleID": "style-body",
                "evidenceIDs": [],
            }],
            "assets": [],
            "styles": [],
            "templateBinding": {
                "templateID": "public-plan",
                "version": "3.2",
                "publishingAuthority": "기관 표준",
                "requiredSections": ["개요"],
                "checklistResults": {},
            },
            "evidenceLinks": [],
            "revisions": [],
            "history": [],
            "aiProposalHistory": [],
            "providerConfigurations": [],
            "consentGrants": [],
            "redoRevisionIDs": [],
        }
        stored = _json(f"{origin}/api/bridge", {"action": "saveLibraryDocument", "project": source})
        entries = stored["events"][0]["payload"]["project"]["entries"]
        assert entries[0]["title"] == "취합 원본"
        loaded = _json(
            f"{origin}/api/bridge",
            {"action": "loadLibraryDocument", "documentID": "document-library-a"},
        )
        assert loaded["events"][0]["payload"]["project"]["elements"][1]["text"] == "○ 결과"
    finally:
        server.shutdown()


def test_local_webapp_rejects_path_escape(tmp_path: Path) -> None:
    server, origin = _start(tmp_path)
    try:
        try:
            urlopen(f"{origin}/../Package.swift")
            raise AssertionError("escaped")
        except HTTPError as error:
            assert error.code == 404
    finally:
        server.shutdown()


def test_local_webapp_exports_docx_with_fractional_revision_timestamp(tmp_path: Path) -> None:
    server, origin = _start(tmp_path)
    try:
        project = {
            "schemaVersion": 1,
            "documentID": "document-docx-ms",
            "locale": "ko-KR",
            "title": "기안문",
            "currentRevisionID": "revision-ms",
            "elements": [{
                "elementID": "element-title",
                "kind": "heading",
                "order": 0,
                "text": "기안문",
                "styleID": "style-title",
                "evidenceIDs": [],
            }, {
                "elementID": "element-section-1-heading",
                "kind": "heading",
                "order": 1,
                "text": "□ 본문",
                "styleID": "style-section-heading",
                "evidenceIDs": [],
            }, {
                "elementID": "element-section-1-body",
                "kind": "paragraph",
                "order": 2,
                "text": "○ 본문",
                "styleID": "style-body",
                "evidenceIDs": [],
            }],
            "assets": [],
            "styles": [],
            "templateBinding": {
                "templateID": "public-draft",
                "version": "1.0",
                "publishingAuthority": "기관 표준",
                "requiredSections": ["본문"],
                "checklistResults": {},
            },
            "evidenceLinks": [],
            "revisions": [{
                "revisionID": "revision-ms",
                "createdAt": "2026-08-20T02:32:36.697Z",
                "summary": "created",
                "elementIDs": ["element-title", "element-section-1-heading", "element-section-1-body"],
            }],
            "history": [{
                "eventID": "history-ms",
                "kind": "created",
                "revisionID": "revision-ms",
                "createdAt": "2026-08-20T02:32:36.697Z",
            }],
            "aiProposalHistory": [],
            "providerConfigurations": [],
            "consentGrants": [],
            "redoRevisionIDs": [],
        }
        request = Request(
            f"{origin}/api/bridge",
            data=json.dumps({
                "action": "export",
                "project": project,
                "formats": ["docx"],
                "flatteningConsent": True,
            }).encode("utf-8"),
            headers=_auth_headers(origin),
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            exported = json.loads(response.read().decode("utf-8"))
        receipt = exported["events"][-1]["payload"]["project"]
        assert receipt.get("failedFormats") == []
        assert "docx" in receipt.get("publishedFormats", [])
    finally:
        server.shutdown()


def test_local_webapp_exports_docx_with_empty_easy_table(tmp_path: Path) -> None:
    server, origin = _start(tmp_path)
    try:
        table_html = (
            '<table data-easy-table="true" style="border-collapse:collapse;border:1px solid #1d1d1f">'
            "<tbody>"
            '<tr><td style="border:1px solid #1d1d1f"></td>'
            '<td style="border:1px solid #1d1d1f"></td>'
            '<td style="border:1px solid #1d1d1f"></td></tr>'
            '<tr><td style="border:1px solid #1d1d1f"></td>'
            '<td style="border:1px solid #1d1d1f"></td>'
            '<td style="border:1px solid #1d1d1f"></td></tr>'
            "</tbody></table>"
        )
        project = {
            "schemaVersion": 1,
            "documentID": "document-docx-table",
            "locale": "ko-KR",
            "title": "기안문",
            "currentRevisionID": "revision-table",
            "elements": [{
                "elementID": "element-title",
                "kind": "heading",
                "order": 0,
                "text": "기안문",
                "styleID": "style-title",
                "evidenceIDs": [],
            }, {
                "elementID": "element-section-1-heading",
                "kind": "heading",
                "order": 1,
                "text": "□ 본문",
                "styleID": "style-section-heading",
                "evidenceIDs": [],
            }, {
                "elementID": "element-section-1-body",
                "kind": "paragraph",
                "order": 2,
                "text": "○ 본문",
                "styleID": "style-body",
                "evidenceIDs": [],
            }, {
                "elementID": "element-table-easy",
                "kind": "table",
                "order": 3,
                "text": "",
                "contentHTML": table_html,
                "inlineIDs": [],
                "styleID": "style-table",
                "evidenceIDs": [],
            }],
            "assets": [],
            "styles": [],
            "templateBinding": {
                "templateID": "public-draft",
                "version": "1.0",
                "publishingAuthority": "기관 표준",
                "requiredSections": ["본문"],
                "checklistResults": {},
            },
            "evidenceLinks": [],
            "revisions": [{
                "revisionID": "revision-table",
                "createdAt": "2026-08-20T02:32:36Z",
                "summary": "easy-table",
                "elementIDs": [
                    "element-title",
                    "element-section-1-heading",
                    "element-section-1-body",
                    "element-table-easy",
                ],
            }],
            "history": [{
                "eventID": "history-table",
                "kind": "easy-table",
                "revisionID": "revision-table",
                "createdAt": "2026-08-20T02:32:36Z",
            }],
            "aiProposalHistory": [],
            "providerConfigurations": [],
            "consentGrants": [],
            "redoRevisionIDs": [],
        }
        request = Request(
            f"{origin}/api/bridge",
            data=json.dumps({
                "action": "export",
                "project": project,
                "formats": ["docx"],
                "flatteningConsent": True,
            }).encode("utf-8"),
            headers=_auth_headers(origin),
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            exported = json.loads(response.read().decode("utf-8"))
        receipt = exported["events"][-1]["payload"]["project"]
        assert receipt.get("failedFormats") == []
        assert "docx" in receipt.get("publishedFormats", [])
    finally:
        server.shutdown()


def test_local_webapp_exports_docx_with_genoffice_prosemirror_table(tmp_path: Path) -> None:
    server, origin = _start(tmp_path)
    try:
        table_html = (
            '<table data-easy-table="true" style="border-collapse:collapse;border:1px solid #1d1d1f">'
            "<tbody><tr>"
            '<td style="border:1px solid #1d1d1f"><p><br class="ProseMirror-trailingBreak"></p></td>'
            '<td style="border:1px solid #1d1d1f"><p><br class="ProseMirror-trailingBreak"></p></td>'
            '<td style="border:1px solid #1d1d1f"><p><br class="ProseMirror-trailingBreak"></p></td>'
            "</tr></tbody></table>"
        )
        project = {
            "schemaVersion": 1,
            "documentID": "document-docx-prosemirror-table",
            "locale": "ko-KR",
            "title": "기안문",
            "currentRevisionID": "revision-pm-table",
            "elements": [{
                "elementID": "element-title",
                "kind": "heading",
                "order": 0,
                "text": "기안문",
                "styleID": "style-title",
                "evidenceIDs": [],
            }, {
                "elementID": "element-table-easy",
                "kind": "table",
                "order": 1,
                "text": "",
                "contentHTML": table_html,
                "inlineIDs": [],
                "styleID": "style-table",
                "evidenceIDs": [],
            }],
            "assets": [],
            "styles": [],
            "templateBinding": {
                "templateID": "public-draft",
                "version": "1.0",
                "publishingAuthority": "기관 표준",
                "requiredSections": ["본문"],
                "checklistResults": {},
            },
            "evidenceLinks": [],
            "revisions": [{
                "revisionID": "revision-pm-table",
                "createdAt": "2026-08-20T02:32:36Z",
                "summary": "easy-table",
                "elementIDs": ["element-title", "element-table-easy"],
            }],
            "history": [{
                "eventID": "history-pm-table",
                "kind": "easy-table",
                "revisionID": "revision-pm-table",
                "createdAt": "2026-08-20T02:32:36Z",
            }],
            "aiProposalHistory": [],
            "providerConfigurations": [],
            "consentGrants": [],
            "redoRevisionIDs": [],
        }
        request = Request(
            f"{origin}/api/bridge",
            data=json.dumps({
                "action": "export",
                "project": project,
                "formats": ["docx"],
                "flatteningConsent": True,
            }).encode("utf-8"),
            headers=_auth_headers(origin),
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            exported = json.loads(response.read().decode("utf-8"))
        receipt = exported["events"][-1]["payload"]["project"]
        assert receipt.get("failedFormats") == []
        assert "docx" in receipt.get("publishedFormats", [])
    finally:
        server.shutdown()
