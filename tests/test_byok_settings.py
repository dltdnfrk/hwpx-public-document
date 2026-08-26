from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TypedDict, cast


ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / ".build" / "debug" / "PublicDocumentApp"


class ProviderCatalogEntry(TypedDict):
    provider: str
    endpointIdentity: str
    defaultModel: str
    endpointReadOnly: bool


class SettingsSnapshot(TypedDict):
    catalog: list[ProviderCatalogEntry]


class SettingsPayload(TypedDict):
    settings: SettingsSnapshot


class BridgeEvent(TypedDict):
    event: str
    payload: SettingsPayload


class BridgeResponse(TypedDict):
    events: list[BridgeEvent]


def _build() -> None:
    _ = subprocess.run(
        ["swift", "build", "--product", "PublicDocumentApp"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _bridge(tmp_path: Path, payload: dict[str, object]) -> BridgeResponse:
    environment = os.environ.copy()
    environment["PUBLIC_DOCUMENT_STUDIO_AI_SETTINGS_ROOT"] = str(tmp_path / "settings")
    environment["PUBLIC_DOCUMENT_STUDIO_AI_KEYCHAIN_SERVICE"] = (
        f"com.muni.public-document.byok-test.{tmp_path.name}"
    )
    completed = subprocess.run(
        [str(BINARY), "--ai-bridge-stdin"],
        cwd=ROOT,
        env=environment,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return cast(BridgeResponse, json.loads(completed.stdout))


def test_studio_byok_surface_exposes_machine_consumed_controls() -> None:
    html = (ROOT / "Resources/Studio/index.html").read_text(encoding="utf-8")
    for marker in (
        'data-action="open-settings"',
        "data-byok-provider",
        "data-byok-endpoint",
        "data-byok-model",
        "data-byok-secret",
        "data-byok-status",
        "data-byok-save",
        "data-byok-test",
        "data-byok-delete",
        "data-byok-policy-list",
    ):
        assert marker in html
    assert "data-ai-secret" not in html


def test_studio_script_is_valid_and_uses_no_browser_storage() -> None:
    _ = subprocess.run(
        ["node", "--check", "Resources/Studio/app.js"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    script = (ROOT / "Resources/Studio/app.js").read_text(encoding="utf-8")
    assert "localStorage" not in script
    assert "sessionStorage" not in script


def test_cli_load_returns_the_authoritative_provider_catalog(tmp_path: Path) -> None:
    _build()
    response = _bridge(tmp_path, {"action": "loadAISettings"})
    catalog = {
        item["provider"]: item
        for item in response["events"][0]["payload"]["settings"]["catalog"]
    }

    assert set(catalog) == {"openai", "anthropic", "gemini", "openai-compatible"}
    assert catalog["openai"]["endpointIdentity"] == "https://api.openai.com/v1"
    assert catalog["openai"]["defaultModel"] == "gpt-5.6-terra"
    assert catalog["anthropic"]["defaultModel"] == "claude-sonnet-5"
    assert catalog["openai-compatible"]["endpointReadOnly"] is False


def test_ai_settings_self_test_covers_security_and_migration(tmp_path: Path) -> None:
    _build()
    completed = subprocess.run(
        [str(BINARY), "--ai-settings-self-test", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = cast("dict[str, bool]", json.loads(completed.stdout))

    assert receipt["endpointChangeRequiresReplacementSecret"] is True
    assert receipt["legacyCredentialMigrated"] is True
    assert receipt["providerCatalogIncluded"] is True
    assert all(receipt.values())
