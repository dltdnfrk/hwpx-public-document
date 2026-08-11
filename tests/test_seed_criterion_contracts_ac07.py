from __future__ import annotations

import json
from pathlib import Path

from tests.seed_criterion_contract_support import run_contract, run_node
from tests.seed_criterion_fixture_support import evidence, write_ac07_fixture, write_json


def test_ac07_local_projection_excludes_producer_verdicts() -> None:
    # Given: the compatibility receipt contains nested local facts and producer-authored verdicts.
    compatibility = {
        "corpusVersion": "1.0.0",
        "manifestVersion": "1.0.0",
        "requiredClientOperations": {"hwpx": ["polaris-office-reopen"]},
        "capabilityGaps": {},
        "artifacts": [{"format": "hwpx", "validation": {"structuralValid": False}}],
        "dispositions": [{"format": "hwpx", "disposition": "artifact-validated"}],
        "structuralVerdict": "pass",
        "semanticVerdict": "pass",
        "overallVerdict": "pass",
    }

    # When: materialization projects local compatibility facts.
    projection = json.loads(run_node({"action": "project-compatibility", "compatibility": compatibility}))

    # Then: nested validation is retained and every producer verdict is excluded.
    assert projection["artifacts"][0]["validation"]["structuralValid"] is False
    assert not {
        "structuralVerdict",
        "semanticVerdict",
        "visualVerdict",
        "clientVerdict",
        "overallVerdict",
    } & projection.keys()


def test_ac07_blocks_only_after_local_contracts_pass(tmp_path: Path) -> None:
    # Given: current local corpus/artifact evidence passes and external observations are absent.
    write_ac07_fixture(tmp_path, structural_verdict="pass")
    blocked = run_contract({"action": "evaluate", "criterion": "AC-07", "root": str(tmp_path)})
    assert blocked["verdict"] == "blocked"
    assert blocked["blockers"]

    # When: an internal structural assertion fails.
    write_ac07_fixture(tmp_path, structural_verdict="fail")
    failed = run_contract({"action": "evaluate", "criterion": "AC-07", "root": str(tmp_path)})

    # Then: FAIL has priority over external BLOCKED.
    assert failed["verdict"] == "fail"


def test_ac07_raw_client_failure_overrides_stored_pass(tmp_path: Path) -> None:
    # Given: a bound client observation says pass while its raw opened assertion is false.
    write_ac07_fixture(tmp_path, structural_verdict="pass")
    summary = json.loads((tmp_path / "artifacts/compatibility/verdict-summary.json").read_text())
    artifact = summary["artifacts"][0]
    observation = {
        "observationID": "client-raw-failure",
        "clientID": "polaris-office",
        "clientName": "Polaris Office",
        "clientVersion": "1.0",
        "clientBuild": "build-1",
        "osVersion": "test-macOS",
        "osBuild": "test-build",
        "fonts": ["Apple SD Gothic Neo Regular"],
        "timestamp": "2026-08-10T00:00:00Z",
        "fixtureID": artifact["fixtureID"],
        "fixtureHash": artifact["fixtureHash"],
        "format": artifact["format"],
        "artifactHash": artifact["artifactHash"],
        "operation": "polaris-office-reopen",
        "opened": False,
        "extensionWarningCount": 0,
        "expectedTextCount": 3,
        "observedTextCount": 0,
        "expectedPageCount": 1,
        "observedPageCount": 0,
        "unexpectedBlankPageCount": 0,
        "evidencePath": "runtime/compatibility.json",
        "evidenceHash": evidence(tmp_path, "runtime/compatibility.json")["sha256"],
        "diagnostics": "producer-authored pass label",
        "verdict": "pass",
    }
    write_json(tmp_path, "artifacts/compatibility/observations.jsonl", [observation])

    # When: AC-07 recomputes the client outcome from raw assertions.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-07", "root": str(tmp_path)})

    # Then: the raw failure wins over both the stored pass and remaining external blockers.
    assert evaluation["verdict"] == "fail"


def test_ac07_raw_visual_failure_overrides_stored_pass(tmp_path: Path) -> None:
    # Given: the summary says visual pass while bound raw coverage is below the frozen tolerance.
    write_ac07_fixture(tmp_path, structural_verdict="pass")
    summary_path = tmp_path / "artifacts/compatibility/verdict-summary.json"
    summary = json.loads(summary_path.read_text())
    artifact = summary["artifacts"][0]
    summary["visualObservations"] = [
        {
            "observationID": "visual-raw-failure",
            "toolID": "visual-checker",
            "clientName": "Compatibility Renderer",
            "clientVersion": "1.0",
            "clientBuild": "build-1",
            "osVersion": "test-macOS",
            "osBuild": "test-build",
            "fonts": ["Apple SD Gothic Neo Regular"],
            "timestamp": "2026-08-10T00:00:00Z",
            "fixtureID": artifact["fixtureID"],
            "fixtureHash": artifact["fixtureHash"],
            "format": artifact["format"],
            "artifactHash": artifact["artifactHash"],
            "expectedPageCount": 1,
            "observedPageCount": 1,
            "missingAuthoredElementIDs": [],
            "unexpectedBlankPageNumbers": [],
            "textBoundsCoverage": 0.5,
            "evidencePath": "runtime/compatibility.json",
            "evidenceHash": evidence(tmp_path, "runtime/compatibility.json")["sha256"],
        }
    ]
    write_json(tmp_path, "artifacts/compatibility/verdict-summary.json", summary)

    # When: AC-07 recomputes the visual outcome from raw assertions.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-07", "root": str(tmp_path)})

    # Then: the raw visual failure is not softened by a stored verdict or blocker.
    assert evaluation["verdict"] == "fail"


def test_ac07_accepts_evidence_bound_blockers_without_legacy_projection_fields(tmp_path: Path) -> None:
    # Given: every external blocker uses the final evidence-bound raw schema only.
    write_ac07_fixture(tmp_path, structural_verdict="pass")
    summary_path = tmp_path / "artifacts/compatibility/verdict-summary.json"
    summary = json.loads(summary_path.read_text())
    for blocker in summary["externalBlockers"]:
        for legacy_field in ["blockerID", "verdictClass", "fixtureID", "reasonCode"]:
            blocker.pop(legacy_field, None)
    write_json(tmp_path, "artifacts/compatibility/verdict-summary.json", summary)

    # When: AC-07 derives identity and blocker class from raw artifact and operation facts.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-07", "root": str(tmp_path)})

    # Then: the locally passing criterion remains externally blocked rather than failing schema projection.
    assert evaluation["verdict"] == "blocked"
