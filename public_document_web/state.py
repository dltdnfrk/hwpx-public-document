from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .catalog import verify_catalog_envelope
from .paths import ENVELOPE


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
