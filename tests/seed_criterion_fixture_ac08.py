from __future__ import annotations

from pathlib import Path

from tests.seed_criterion_fixture_support import evidence, write_json


JOURNEYS = [
    "guided-authoring",
    "AI-proposal-review",
    "AI-consent",
    "official-rule-and-template-guidance",
    "loss-resolution",
    "single-export",
    "batch-export",
]


def write_ac08_fixture(root: Path) -> None:
    studio_hashes = {}
    for name in ["index.html", "styles.css", "app.js"]:
        relative = f"Resources/Studio/{name}"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(name, encoding="utf-8")
        studio_hashes[relative] = evidence(root, relative)["sha256"][7:]
    source_evidence = []
    for index in range(8):
        relative = f"runtime/ac08-evidence-{index}.txt"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(index), encoding="utf-8")
        source_evidence.append(evidence(root, relative))
    commands = [
        {"command": "playwright test tests/ac08-browser-qa.spec.js", "exitCode": 0, "result": "structured browser result"},
        {"command": "python -m pytest -q tests/test_ac08_accessibility.py", "exitCode": 0, "result": "source contract passed"},
        {"command": "visual-qa.mjs image-diff reference-1280.png actual-1280.png", "exitCode": 0, "result": "pass"},
        {"command": "visual-qa.mjs image-diff reference-920.png actual-920.png", "exitCode": 0, "result": "pass"},
    ]
    browser_hashes = {name.rsplit("/", 1)[-1]: digest for name, digest in studio_hashes.items()}
    write_json(root, "artifacts/accessibility/automated-results.json", [{"state": index, "violations": []} for index in range(6)])
    write_json(
        root,
        "artifacts/accessibility/manual-scenarios.json",
        {
            "verificationReceipt": {
                "browserTests": {"passed": 6, "failed": 0},
                "commands": commands,
                "testedSourceSHA256": studio_hashes,
                "freshness": {"sourceHashesMatchedBeforeAndAfterBrowserRun": True},
            },
            "voiceOver": {
                "status": "PASS",
                "recordedAt": "2026-08-10T00:00:00Z",
                "browserTarget": {"sourceSHA256": browser_hashes},
                "journeys": [{"name": name, "status": "PASS"} for name in JOURNEYS],
            },
            "keyboard": {
                "journeys": [{"name": name, "status": "PASS", "criticalActivationInputSource": "keyboard"} for name in JOURNEYS],
                "programmaticStates": {"outlineCurrent": {"passed": True}, "formatToggles": {"onAndOffObserved": True}},
                "focusTransitions": {"approved": {"activeElementMatched": True}, "rejected": {"activeElementMatched": True}},
            },
            "sourceEvidence": source_evidence,
        },
    )
    write_json(
        root,
        "artifacts/ui/reference-comparison.json",
        {
            "comparisons": [
                {"dimensionsMatch": True, "alphaChannelIntact": True, "similarityScore": 99},
                {"dimensionsMatch": True, "alphaChannelIntact": True, "similarityScore": 98},
            ],
            "pinnedReference": {"passed": True, "lineage": "pinned-genoffice-docs-fidelity-v1", "referenceSetHash": "sha256:" + "1" * 64},
            "referenceSource": {"referenceSetHash": "sha256:" + "1" * 64, "upstream": {"commit": "d8305ff2dc152593a1ec5639d77e6860c6a512bd"}},
        },
    )
