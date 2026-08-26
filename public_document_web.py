from __future__ import annotations

import argparse
import base64
import json
import posixpath
import secrets
import shutil
import subprocess
import tempfile
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
RESOURCES = ROOT / "Resources"
ENVELOPE = RESOURCES / "Templates" / "catalog-envelope.json"
PUBLIC_KEY_HEX = "a3ca24b7a40d1be062659a9895287e7732e1cf8bbe7de0e3d23783076c67f2ce"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
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
AI_BRIDGE_ACTIONS = {
    "loadAISettings",
    "configureAISettings",
    "testAISettings",
    "deleteAISettings",
    "requestAIProposal",
    "revokeAIConsent",
    "applyAIProposal",
    "rejectAIProposal",
}
AI_PROJECT_EVENTS = {
    "aiProposal",
    "aiConsentRevoked",
    "aiProposalApplied",
    "aiProposalRejected",
}
AI_PROJECT_ACTIONS = {
    "requestAIProposal",
    "revokeAIConsent",
    "applyAIProposal",
    "rejectAIProposal",
}
AI_CANONICAL_PROJECT_ACTIONS = {
    "revokeAIConsent",
    "applyAIProposal",
    "rejectAIProposal",
}
UNSUPPORTED_ACTIONS = {
    "batchExport",
    "cancelBatchExport",
    "retryBatchExport",
    "undoAIRevision",
    "redoAIRevision",
}


class StudioState:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.project_file = data_dir / "project.json"
        self.recovery_file = data_dir / "recovery.json"
        self.previous_envelope = data_dir / "previous-catalog.json"
        self.trusted_envelope = data_dir / "trusted-catalog.json"
        self.downloads = data_dir / "downloads"
        self.prefs_file = data_dir / "studio-prefs.json"
        self.library_dir = data_dir / "library"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.downloads.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        if not self.trusted_envelope.is_file():
            self.trusted_envelope.write_bytes(ENVELOPE.read_bytes())

    def load_prefs(self) -> dict[str, Any]:
        if not self.prefs_file.is_file():
            return default_studio_prefs()
        try:
            return normalize_studio_prefs(self.load_json(self.prefs_file))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return default_studio_prefs()

    def save_prefs(self, prefs: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_studio_prefs(prefs)
        self.write_json(self.prefs_file, normalized)
        return normalized

    def list_library(self) -> list[dict[str, Any]]:
        entries = []
        for path in sorted(self.library_dir.glob("*.json")):
            try:
                project = self.load_json(path)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
            entries.append({
                "documentID": str(project.get("documentID") or path.stem),
                "title": str(project.get("title") or path.stem),
            })
        return entries

    def save_library(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        document_id = _safe_id(str(project.get("documentID") or uuid.uuid4()))
        stored = dict(project)
        stored["documentID"] = document_id
        self.write_json(self.library_dir / f"{document_id}.json", stored)
        return self.list_library()

    def load_library(self, document_id: str) -> dict[str, Any]:
        path = (self.library_dir / f"{_safe_id(document_id)}.json").resolve()
        try:
            path.relative_to(self.library_dir.resolve())
        except ValueError as error:
            raise ValueError("문서함 항목을 찾을 수 없습니다.") from error
        if not path.is_file():
            raise ValueError("문서함 항목을 찾을 수 없습니다.")
        return self.load_json(path)

    def catalog_status(self) -> dict[str, Any]:
        catalog = verify_catalog_envelope(self.trusted_envelope.read_bytes())
        return {
            "catalogVersion": catalog["version"],
            "publishedAt": catalog["publishedAt"],
            "entries": catalog["entries"],
            "rollbackAvailable": self.previous_envelope.is_file(),
        }

    def load_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def inspect(self, project: dict[str, Any]) -> dict[str, Any]:
        binding = project.get("templateBinding") or {}
        return {
            "schemaVersion": project.get("schemaVersion"),
            "documentID": project.get("documentID"),
            "currentRevisionID": project.get("currentRevisionID"),
            "elementCount": len(project.get("elements") or []),
            "assetCount": len(project.get("assets") or []),
            "styleCount": len(project.get("styles") or []),
            "evidenceLinkCount": len(project.get("evidenceLinks") or []),
            "revisionCount": len(project.get("revisions") or []),
            "historyEventCount": len(project.get("history") or []),
            "templateID": binding.get("templateID"),
            "templateVersion": binding.get("version"),
        }


def verify_catalog_envelope(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > 262_144:
        raise ValueError("invalid catalog envelope")
    envelope = json.loads(raw.decode("utf-8"))
    if set(envelope) != {"keyID", "payload", "signature"}:
        raise ValueError("invalid catalog envelope")
    if envelope["keyID"] != "studio-template-root-2026":
        raise ValueError("invalid catalog envelope")
    payload = base64.b64decode(envelope["payload"], validate=True)
    signature = base64.b64decode(envelope["signature"], validate=True)
    if not payload or len(payload) > 131_072:
        raise ValueError("invalid catalog envelope")
    if base64.b64encode(payload).decode("ascii") != envelope["payload"]:
        raise ValueError("invalid catalog envelope")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX)).verify(signature, payload)
    catalog = json.loads(payload.decode("utf-8"))
    canonical = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if canonical != payload:
        raise ValueError("invalid catalog envelope")
    types = {entry["documentType"] for entry in catalog["entries"]}
    if types != {"추진계획서", "기안문", "보고서", "결과보고서", "업무협조", "회의록"}:
        raise ValueError("invalid catalog envelope")
    return catalog


def enforce_official_rules(project: dict[str, Any], catalog: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = project.get("templateBinding") or {}
    template_id = binding.get("templateID")
    rules = [
        rule
        for entry in catalog.get("entries", [])
        if entry.get("templateID") == template_id
        for rule in entry.get("officialRules") or []
        if rule.get("field") == "title"
    ]
    rules.sort(key=lambda rule: int(rule.get("precedence") or 0), reverse=True)
    if not rules:
        return project, {"appliedRules": [], "conflicts": [], "contentChanged": False}
    rule = rules[0]
    required = rule["requiredValue"]
    elements = list(project.get("elements") or [])
    title_elements = [
        element
        for element in elements
        if element.get("styleID") == "style-title" or element.get("elementID") == "element-title"
    ]
    submitted = project.get("title") if project.get("title") != required else next(
        (element.get("text") for element in title_elements if element.get("text") != required),
        None,
    )
    if submitted is None:
        return project, {"appliedRules": rules, "conflicts": [], "contentChanged": False}

    updated_elements = []
    for element in elements:
        if (
            element.get("styleID") == "style-title" or element.get("elementID") == "element-title"
        ) and element.get("text") != required:
            updated = dict(element)
            updated["text"] = required
            updated_elements.append(updated)
        else:
            updated_elements.append(element)
    created_at = _now()
    revision_id = f"revision-official-rule-{uuid.uuid4()}"
    governed = dict(project)
    governed["title"] = required
    governed["elements"] = updated_elements
    governed["currentRevisionID"] = revision_id
    governed["revisions"] = list(project.get("revisions") or []) + [{
        "revisionID": revision_id,
        "parentRevisionID": project.get("currentRevisionID"),
        "createdAt": created_at,
        "summary": "official-rule-enforced:title",
        "elementIDs": [element.get("elementID") for element in updated_elements],
        "snapshotElements": updated_elements,
    }]
    governed["history"] = list(project.get("history") or []) + [{
        "eventID": f"history-official-rule-{uuid.uuid4()}",
        "kind": "official-rule-enforced:title",
        "revisionID": revision_id,
        "createdAt": created_at,
    }]
    return governed, {
        "appliedRules": rules,
        "conflicts": [{
            "field": "title",
            "submittedValue": submitted,
            "requiredValue": required,
            "precedence": rule.get("precedence"),
            "source": rule.get("source"),
            "warning": (
                f"공식 규칙 충돌: 제출 제목 '{submitted}' 대신 공식 규칙"
                f"(우선순위 {rule.get('precedence')})의 필수 제목을 적용했습니다: '{required}'."
            ),
        }],
        "contentChanged": True,
    }


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_app_binary() -> Path:
    debug = ROOT / ".build" / "debug" / "PublicDocumentApp"
    sources = list((ROOT / "Sources" / "PublicDocumentApp").glob("*.swift"))
    newest_source = max((path.stat().st_mtime for path in sources), default=0)
    if not debug.is_file() or (newest_source and debug.stat().st_mtime < newest_source):
        subprocess.run(
            ["swift", "build", "--product", "PublicDocumentApp"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    return debug


def run_ai_bridge(message: dict[str, Any]) -> dict[str, Any]:
    result = subprocess.run(
        [str(resolve_app_binary()), "--ai-bridge-stdin"],
        cwd=ROOT,
        input=json.dumps(message, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("AI 제공자 작업을 완료하지 못했습니다.")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise RuntimeError("AI 제공자 응답 형식이 올바르지 않습니다.")
    return payload


def export_project(project: dict[str, Any], formats: list[str], consent: bool, downloads: Path) -> dict[str, Any]:
    operation = uuid.uuid4().hex
    work = Path(tempfile.mkdtemp(prefix="public-document-web-export-"))
    destination = work / "out"
    destination.mkdir()
    source = work / "project.json"
    source.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    command = [
        str(resolve_app_binary()),
        "--export-project",
        str(source),
        str(destination),
        "--formats",
        ",".join(formats),
    ]
    if consent:
        command.append("--flattening-consent")
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("내보내기가 응답하지 않아 중단했습니다.") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "export failed").strip()
        raise RuntimeError(detail) from error
    receipt = json.loads(result.stdout)
    public = downloads / operation
    public.mkdir(parents=True)
    title = _safe_filename(str(project.get("title") or "공공문서"))
    for item in receipt.get("results") or []:
        name = item.get("fileName") or item.get("relativePath")
        if not name:
            continue
        produced = destination / name
        if not produced.is_file():
            continue
        suffix = Path(name).suffix
        published_name = f"{title}{suffix}"
        published = public / published_name
        shutil.copy2(produced, published)
        item["fileName"] = published_name
        item["relativePath"] = published_name
        item["downloadURL"] = f"/downloads/{operation}/{published_name}"
    shutil.rmtree(work, ignore_errors=True)
    return receipt


def _safe_filename(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "._- " else "_" for character in value)
    cleaned = cleaned.strip() or "공공문서"
    return cleaned[:80]


def _safe_id(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "-_" else "-" for character in value)
    return cleaned[:80] or "document"


def default_studio_prefs() -> dict[str, Any]:
    return {
        "autosaveIntervalMs": 180000,
        "favorites": [],
        "myForms": [],
    }


def normalize_studio_prefs(raw: Any) -> dict[str, Any]:
    prefs = default_studio_prefs()
    if not isinstance(raw, dict):
        return prefs
    interval = raw.get("autosaveIntervalMs")
    if interval in {60000, 180000, 300000, 600000}:
        prefs["autosaveIntervalMs"] = interval
    favorites = raw.get("favorites")
    if isinstance(favorites, list):
        prefs["favorites"] = [
            str(item)[:80]
            for item in favorites
            if isinstance(item, (str, int)) and str(item).strip()
        ][:20]
    forms = raw.get("myForms")
    if isinstance(forms, list):
        cleaned = []
        for item in forms[:20]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()[:80]
            text = str(item.get("text") or "").strip()[:4000]
            form_id = str(item.get("id") or "").strip()[:80]
            if not name or not text:
                continue
            cleaned.append({
                "id": form_id or f"form-{len(cleaned) + 1}",
                "name": name,
                "text": text,
            })
        prefs["myForms"] = cleaned
    return prefs


def handle_bridge(state: StudioState, body: dict[str, Any]) -> list[dict[str, Any]]:
    action = body.get("action")
    catalog = state.catalog_status()
    if action == "ready":
        events = [
            event("studioPrefs", state.load_prefs()),
            event("documentLibrary", {"entries": state.list_library()}),
            event("templateCatalog", catalog),
        ]
        settings_request: dict[str, Any] = {"action": "loadAISettings"}
        settings_source = state.recovery_file if state.recovery_file.is_file() else state.project_file
        if settings_source.is_file():
            settings_request["project"] = state.load_json(settings_source)
        try:
            events.extend(run_ai_bridge(settings_request)["events"])
        except (RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError):
            events.append({
                "event": "aiSettingsUnavailable",
                "payload": {"message": "AI 설정을 불러오지 못했지만 문서 기능은 계속 사용할 수 있습니다."},
            })
        if state.recovery_file.is_file():
            events.append(event("recovered", state.load_json(state.recovery_file)))
        elif state.project_file.is_file():
            events.append(event("opened", state.load_json(state.project_file)))
        else:
            events.append({"event": "empty", "payload": {}})
        return events
    if action == "saveStudioPrefs":
        return [event("studioPrefs", state.save_prefs(body.get("prefs") or {}))]
    if action == "saveLibraryDocument":
        return [event("documentLibrary", {"entries": state.save_library(require_project(body))})]
    if action == "loadLibraryDocument":
        return [event("libraryDocument", state.load_library(str(body.get("documentID") or "")))]
    if action in {"save", "autosave"}:
        project, official = enforce_official_rules(require_project(body), catalog)
        target = state.project_file if action == "save" else state.recovery_file
        state.write_json(target, project)
        if action == "save" and state.recovery_file.is_file():
            state.recovery_file.unlink()
        return [enforcement_event("saved" if action == "save" else "autosaved", project, official)]
    if action == "reopen":
        if not state.project_file.is_file():
            return [error_event("저장된 프로젝트가 없습니다.")]
        return [event("opened", state.load_json(state.project_file))]
    if action == "recover":
        source = state.recovery_file if state.recovery_file.is_file() else state.project_file
        if not source.is_file():
            return [error_event("복구할 프로젝트가 없습니다.")]
        return [event("recovered", state.load_json(source))]
    if action == "inspect":
        source = state.recovery_file if state.recovery_file.is_file() else state.project_file
        if not source.is_file():
            return [error_event("검사할 프로젝트가 없습니다.")]
        return [event("inspection", state.inspect(state.load_json(source)))]
    if action == "export":
        project, official = enforce_official_rules(require_project(body), catalog)
        state.write_json(state.project_file, project)
        formats = [item for item in body.get("formats") or [] if item in {"hwpx", "hwp", "docx", "markdown"}]
        if not formats:
            return [error_event("내보낼 형식을 하나 이상 선택하세요.")]
        receipt = export_project(project, formats, bool(body.get("flatteningConsent")), state.downloads)
        return [
            enforcement_event("officialRuleEnforced", project, official),
            event("exportCompleted", receipt),
        ]
    if action == "rollbackTemplateCatalog":
        if not state.previous_envelope.is_file():
            return [error_event("되돌릴 이전 템플릿 카탈로그가 없습니다.")]
        current = state.trusted_envelope.read_bytes()
        previous = state.previous_envelope.read_bytes()
        state.trusted_envelope.write_bytes(previous)
        state.previous_envelope.write_bytes(current)
        return [event("templateCatalog", state.catalog_status())]
    if action == "updateTemplateCatalog":
        return [error_event("로컬 웹앱은 번들된 서명 카탈로그를 사용합니다. 카탈로그 파일 선택은 앱에서 하세요.")]
    if action in AI_BRIDGE_ACTIONS:
        ai_body = dict(body)
        if action in AI_PROJECT_ACTIONS:
            project = body.get("project")
            if action in AI_CANONICAL_PROJECT_ACTIONS and state.project_file.is_file():
                project = state.load_json(state.project_file)
            if isinstance(project, dict):
                ai_body["project"] = enforce_official_rules(project, catalog)[0]
        response = run_ai_bridge(ai_body)
        for entry in response["events"]:
            if entry.get("event") not in AI_PROJECT_EVENTS:
                continue
            project = (entry.get("payload") or {}).get("project")
            if not isinstance(project, dict) or "schemaVersion" not in project:
                continue
            governed, official = enforce_official_rules(project, catalog)
            entry["payload"]["project"] = governed
            entry["payload"]["officialRuleState"] = official
            state.write_json(state.project_file, governed)
            state.recovery_file.unlink(missing_ok=True)
        return response["events"]
    if action in UNSUPPORTED_ACTIONS:
        return [error_event("로컬 웹앱에서는 이 작업을 아직 지원하지 않습니다.")]
    return [error_event("지원하지 않는 프로젝트 작업입니다.")]


def require_project(body: dict[str, Any]) -> dict[str, Any]:
    project = body.get("project")
    if not isinstance(project, dict):
        raise ValueError("프로젝트 본문이 없습니다.")
    return project


def event(name: str, project: dict[str, Any]) -> dict[str, Any]:
    return {"event": name, "payload": {"project": project}}


def enforcement_event(name: str, project: dict[str, Any], official: dict[str, Any]) -> dict[str, Any]:
    return {"event": name, "payload": {"project": project, "officialRuleState": official}}


def error_event(message: str) -> dict[str, Any]:
    return {"event": "error", "payload": {"message": message}}


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
            events = handle_bridge(self._studio_server.state, body)
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


def main() -> None:
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
    server = serve(args.host, args.port, Path(args.data_dir), open_browser=not args.no_open)
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


if __name__ == "__main__":
    main()
