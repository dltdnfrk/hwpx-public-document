from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _app_binary() -> Path:
    # Given: the native application sources for the AC-02 implementation.
    subprocess.run(
        ["swift", "build"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    assert binary.is_file()
    return binary


def test_native_store_preserves_authoritative_project_through_full_lifecycle(
    tmp_path: Path,
) -> None:
    # Given: a clean location controlled by the native project store.
    project_root = tmp_path / "lifecycle.publicdocument"

    # When: the executable creates, saves, reopens, autosaves, recovers, and inspects it.
    result = subprocess.run(
        [str(_app_binary()), "--project-store-self-test", str(project_root)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(result.stdout)

    # Then: every required lifecycle phase passed against one authoritative identity.
    assert receipt["schemaVersion"] == 1
    assert receipt["stableElementIDs"] is True
    assert receipt["assetsPreserved"] is True
    assert receipt["stylesPreserved"] is True
    assert receipt["templateBindingPreserved"] is True
    assert receipt["evidenceLinksPreserved"] is True
    assert receipt["revisionHistoryPreserved"] is True
    assert receipt["richStructurePreserved"] is True
    assert receipt["recoveredAutosave"] is True
    assert receipt["derivedExportDidNotMutateProject"] is True
    assert receipt["recoveryFileRemovedAfterCommit"] is True


def test_native_store_migrates_legacy_project_without_changing_stable_content(
    tmp_path: Path,
) -> None:
    # Given: a schema-v0 project fixture written by the executable's migration harness.
    project_root = tmp_path / "migration.publicdocument"

    # When: the native store opens and migrates the legacy project.
    result = subprocess.run(
        [str(_app_binary()), "--project-migration-self-test", str(project_root)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(result.stdout)

    # Then: migration is explicit, persisted, and stable identities and history survive.
    assert receipt == {
        "documentID": "document-legacy-001",
        "elementIDs": ["element-legacy-heading", "element-legacy-body"],
        "fromSchemaVersion": 0,
        "historyEvent": "schema-migrated",
        "revisionCount": 1,
        "toSchemaVersion": 1,
    }


def test_editor_exposes_project_lifecycle_without_browser_storage() -> None:
    # Given: the shipped editor and native host sources.
    editor = (ROOT / "Resources/Studio/app.js").read_text(encoding="utf-8")
    host = (ROOT / "Sources/PublicDocumentApp/main.swift").read_text(encoding="utf-8")

    # When/Then: lifecycle actions cross the native bridge and browser storage is absent.
    for action in ("save", "reopen", "recover", "inspect"):
        assert f'data-project-action="{action}"' in (
            ROOT / "Resources/Studio/index.html"
        ).read_text(encoding="utf-8")
    assert "window.webkit.messageHandlers.projectStore" in editor
    assert "localStorage" not in editor
    assert "sessionStorage" not in editor
    assert 'WKScriptMessageHandler' in host


def test_editor_project_projection_preserves_safe_rich_text_and_tables() -> None:
    # Given: the editor projection used by save, reopen, autosave, and recovery.
    editor = (ROOT / "Resources/Studio/app.js").read_text(encoding="utf-8")
    model = (ROOT / "Sources/PublicDocumentApp/DocumentProject.swift").read_text(encoding="utf-8")

    # When/Then: safe structure and stable inline identities cross the native boundary.
    assert "contentHTML" in model
    assert "inlineIDs" in model
    assert "sanitizeRichContent" in editor
    assert "rehydrateRichContent" in editor
    assert "DOMParser" in editor
    assert "data-inline-id" in editor
    assert "target.replaceChildren" in editor
    assert "target.innerHTML = element.contentHTML" not in editor


def test_native_app_launch_keeps_a_visible_studio_window() -> None:
    # Given: the same AppKit launch path used by the unsigned local application.
    # When: the executable observes its window after launch has completed.
    result = subprocess.run(
        [str(_app_binary()), "--window-lifecycle-self-test"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )

    # Then: one visible Public Document Studio window remains retained.
    assert json.loads(result.stdout) == {"visibleWindowCount": 1}
