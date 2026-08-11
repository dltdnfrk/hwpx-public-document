from __future__ import annotations

import json
from pathlib import Path

from tests.seed_criterion_contract_support import run_contract
from tests.seed_criterion_fixture_ac08 import write_ac08_fixture
from tests.seed_criterion_fixture_support import write_json


def test_ac08_accepts_structured_exact_six_of_six_browser_result(tmp_path: Path) -> None:
    # Given: current AC-08 evidence records six passed and zero failed browser tests.
    write_ac08_fixture(tmp_path)

    # When: AC-08 independently evaluates the structured browser count.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-08", "root": str(tmp_path)})

    # Then: the complete six-test browser suite passes.
    assert evaluation["verdict"] == "pass"


def test_ac08_accepts_exact_six_of_six_command_fallback(tmp_path: Path) -> None:
    # Given: a legacy receipt has no structured count but records an exact 6/6 command result.
    write_ac08_fixture(tmp_path)
    manual_path = tmp_path / "artifacts/accessibility/manual-scenarios.json"
    manual = json.loads(manual_path.read_text())
    manual["verificationReceipt"].pop("browserTests")
    manual["verificationReceipt"]["commands"][0]["result"] = "6/6 passed in 5.8 seconds."
    write_json(tmp_path, "artifacts/accessibility/manual-scenarios.json", manual)

    # When: AC-08 evaluates the fallback command receipt.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-08", "root": str(tmp_path)})

    # Then: the exact final count passes without accepting the obsolete 5/5 result.
    assert evaluation["verdict"] == "pass"


def test_ac08_rejects_incomplete_structured_browser_count(tmp_path: Path) -> None:
    # Given: the browser command exits zero but only five tests are recorded as passed.
    write_ac08_fixture(tmp_path)
    manual_path = tmp_path / "artifacts/accessibility/manual-scenarios.json"
    manual = json.loads(manual_path.read_text())
    manual["verificationReceipt"]["browserTests"] = {"passed": 5, "failed": 0}
    manual["verificationReceipt"]["commands"][0]["result"] = "6/6 passed in 5.8 seconds."
    write_json(tmp_path, "artifacts/accessibility/manual-scenarios.json", manual)

    # When: AC-08 evaluates the incomplete suite.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-08", "root": str(tmp_path)})

    # Then: exit zero cannot substitute for the exact six-test outcome.
    assert evaluation["verdict"] == "fail"
    assert any(check["id"] == "accessibility.browser" and not check["passed"] for check in evaluation["checks"])
