from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_studio_has_dedicated_byok_settings_surface() -> None:
    html = (ROOT / "Resources/Studio/index.html").read_text(encoding="utf-8")
    assert 'data-action="open-settings"' in html
    assert 'class="project-inspector byok-settings"' in html
    assert 'id="byok-settings-title">BYOK 설정<' in html
    for marker in (
        "data-byok-provider",
        "data-byok-endpoint",
        "data-byok-model",
        "data-byok-secret",
        "data-byok-status",
        "data-byok-save",
        "data-byok-test",
        "data-byok-delete",
    ):
        assert marker in html
    assert 'data-ai-secret' not in html


def test_studio_wires_settings_actions_and_rebinds_consent() -> None:
    script = (ROOT / "Resources/Studio/app.js").read_text(encoding="utf-8")
    for action in (
        "loadAISettings",
        "configureAISettings",
        "testAISettings",
        "deleteAISettings",
    ):
        assert action in script
    assert "applyProviderDefaults" in script
    assert "focusedEditorElementID ? [focusedEditorElementID] : []" in script
    start = script.rindex("document.querySelectorAll('[data-ai-operation]').forEach")
    operation_handler = script[start:script.index("document.querySelector('[data-ai-request]')", start)]
    assert "[data-ai-consent]" in operation_handler
    assert "checked = false" in operation_handler


def test_web_host_routes_ai_through_workspace_cli_and_authenticates_bridge() -> None:
    source = (ROOT / "public_document_web.py").read_text(encoding="utf-8")
    assert "--ai-bridge-stdin" in source
    assert "AI_BRIDGE_ACTIONS" in source
    assert "PublicDocumentSession" in source
    assert "secrets.token_urlsafe" in source
    assert "configureAIProvider" not in source[source.index("UNSUPPORTED_ACTIONS"):]


def test_swift_settings_are_global_model_aware_and_deletable() -> None:
    settings = (ROOT / "Sources/PublicDocumentApp/AISettings.swift").read_text(encoding="utf-8")
    transport = (ROOT / "Sources/PublicDocumentApp/AIProviderTransport.swift").read_text(encoding="utf-8")
    governance = (ROOT / "Sources/PublicDocumentApp/AIGovernance.swift").read_text(encoding="utf-8")
    assert "final class AISettingsStore" in settings
    assert "struct AIProviderSetting" in settings
    assert "func delete" in settings
    assert "keychainAccountReference" in settings
    assert "let model: String" in governance
    assert '"model": binding.model' in transport
    assert "delete(accountReference:" in transport


def test_cli_exposes_stdin_only_ai_bridge() -> None:
    host = (ROOT / "Sources/PublicDocumentApp/main.swift").read_text(encoding="utf-8")
    assert '--ai-bridge-stdin' in host
    assert "FileHandle.standardInput.readDataToEndOfFile()" in host
    assert "CommandLine.arguments" in host


def test_ai_settings_self_test_covers_model_keychain_and_delete(tmp_path: Path) -> None:
    subprocess.run(
        ["swift", "build", "--product", "PublicDocumentApp"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [str(ROOT / ".build/debug/PublicDocumentApp"), "--ai-settings-self-test", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(result.stdout)
    assert all(receipt.values())
