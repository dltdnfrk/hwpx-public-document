from __future__ import annotations

import json
import subprocess
from typing import Any

from .native import export_project, run_ai_bridge
from .official_rules import enforce_official_rules
from .state import StudioState


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


def handle_bridge(state: StudioState, body: dict[str, Any]) -> list[dict[str, Any]]:
    action = body.get("action")
    catalog = state.catalog_status()
    if action == "ready":
        events = [
            event("studioPrefs", state.load_prefs()),
            event("documentLibrary", {"entries": state.list_library()}),
            event("templateCatalog", catalog),
        ]
        startup_project = state.load_recoverable_project()
        settings_request: dict[str, Any] = {"action": "loadAISettings"}
        if startup_project is not None:
            settings_request["project"] = startup_project[1]
        try:
            events.extend(run_ai_bridge(settings_request)["events"])
        except (RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError):
            events.append({
                "event": "aiSettingsUnavailable",
                "payload": {"message": "AI 설정을 불러오지 못했지만 문서 기능은 계속 사용할 수 있습니다."},
            })
        if startup_project is None:
            events.append({"event": "empty", "payload": {}})
        else:
            events.append(event(*startup_project))
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
        recovered = state.load_recoverable_project()
        if recovered is None:
            return [error_event("복구할 프로젝트가 없습니다.")]
        return [event("recovered", recovered[1])]
    if action == "inspect":
        recovered = state.load_recoverable_project()
        if recovered is None:
            return [error_event("검사할 프로젝트가 없습니다.")]
        return [event("inspection", state.inspect(recovered[1]))]
    if action == "export":
        formats = [item for item in body.get("formats") or [] if item in {"hwpx", "hwp", "docx", "markdown"}]
        if not formats:
            return [error_event("내보낼 형식을 하나 이상 선택하세요.")]
        project, official = enforce_official_rules(require_project(body), catalog)
        state.write_json(state.project_file, project)
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
