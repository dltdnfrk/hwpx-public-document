from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _app_binary() -> Path:
    # Given: the native AC-03 catalog implementation.
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


def test_signed_catalog_update_preserves_pinned_document_and_failed_update(
    tmp_path: Path,
) -> None:
    # Given: a clean trusted-catalog store and an app-native pinned document fixture.
    catalog_root = tmp_path / "TemplateCatalog"

    # When: the executable bootstraps, installs a signed update, rejects tampering,
    # reloads offline, and rolls back.
    result = subprocess.run(
        [str(_app_binary()), "--template-catalog-self-test", str(catalog_root)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(result.stdout)

    # Then: trust, pinning, offline continuity, and rollback are all observable.
    assert receipt == {
        "authoritativeTitle": "기관 공식 제목을 사용하세요",
        "bootstrappedCatalogVersion": "2026.08.1",
        "conflictWarning": (
            "공식 규칙 충돌: 제출 제목 '템플릿 제안 제목' 대신 공식 규칙"
            "(우선순위 100)의 필수 제목을 적용했습니다: '기관 공식 제목을 사용하세요'."
        ),
        "exportBoundProjectTitle": "# 기관 공식 제목을 사용하세요",
        "exportSnapshotUsedRuleRevision": True,
        "failedUpdatePreservedLastTrusted": True,
        "highestAppliedPrecedence": 100,
        "immutableRevisionCreated": True,
        "lowerPrecedenceCouldNotOverride": True,
        "offlineReloadCatalogVersion": "2026.09.1",
        "officialRuleHistoryRecorded": True,
        "officialRuleTitleElementEnforced": True,
        "pinnedTemplateVersionAfterUpdate": "3.2",
        "pinnedTemplateVersionBeforeUpdate": "3.2",
        "repeatedEnforcementWasIdempotent": True,
        "rollbackCatalogVersion": "2026.08.1",
        "signatureRejected": True,
        "unsupportedOfficialFieldRejected": True,
        "updatedCatalogEntryCount": 2,
        "updatedCatalogVersion": "2026.09.1",
    }


def test_studio_exposes_governed_template_and_guided_workflow() -> None:
    # Given: the shipped editor, native host, and catalog implementation.
    markup = (ROOT / "Resources/Studio/index.html").read_text(encoding="utf-8")
    editor = (ROOT / "Resources/Studio/app.js").read_text(encoding="utf-8")
    host = (ROOT / "Sources/PublicDocumentApp/main.swift").read_text(encoding="utf-8")
    catalog = (ROOT / "Sources/PublicDocumentApp/TemplateCatalog.swift").read_text(
        encoding="utf-8"
    )

    # When/Then: catalog update and rollback are reachable, while the editor keeps
    # required-section, checklist, evidence, and review-marker guidance visible.
    for action in ("update-template", "rollback-template"):
        assert f'data-template-action="{action}"' in markup
    for field in (
        "requiredSections",
        "checklistResults",
        "evidenceLinks",
        "templateBinding",
    ):
        assert field in editor
    assert "[확인 필요]" in markup
    assert "updateTemplateCatalog" in host
    assert "rollbackTemplateCatalog" in host
    assert "openCanonicalProject" in host
    assert "openRecoveringProject" in host
    assert 'event: "officialRuleEnforced"' in host
    assert "isValidSignature" in catalog
    assert "enum CatalogOfficialField" in catalog
    assert "enforceOfficialRules" in catalog
    assert "rule.precedence > current.precedence" in catalog
    assert "write(to: trustedEnvelopeFile, options: [.atomic])" in catalog
    assert "rule.requiredValue" in editor
    assert "rule.precedence" in editor
    assert "officialRuleState" in editor
    assert "officialRuleConflict" in editor
