from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .external_stage2.replay_fixture import ReplayFixture, build_replay_fixture


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts/external-stage2/verify_pinned_receipt.py"
FRESH_NOW = "2026-08-13T12:00:00.000Z"
STALE_NOW = "2026-08-13T12:10:00.001Z"


def run_verifier(
    fixture: ReplayFixture,
    pin_db: Path,
    now: str = FRESH_NOW,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--receipt", str(fixture.receipt_path),
            "--trust-policy", str(fixture.policy_path),
            "--trust-policy-sha256", fixture.policy_sha256_pin,
            "--request", str(fixture.request_path),
            "--result", str(fixture.result_path),
            "--manifest", str(fixture.manifest_path),
            "--artifact-root", str(fixture.artifact_root),
            "--execution-id", fixture.execution_id,
            "--pin-db", str(pin_db),
            "--now", now,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def output(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert completed.stderr == ""
    return json.loads(completed.stdout)


def test_exact_approved_receipt_is_idempotent_after_freshness_expiry(tmp_path: Path) -> None:
    # Given: a provenance-valid approval has established the execution's first pin.
    fixture = build_replay_fixture(tmp_path / "approved", "exec-replay-approved")
    pin_db = tmp_path / "orchestrator" / "pins.sqlite3"
    first = run_verifier(fixture, pin_db)
    assert first.returncode == 0

    # When: the exact receipt is replayed after its first-use freshness window.
    replay = run_verifier(fixture, pin_db, STALE_NOW)

    # Then: the stored approval is returned idempotently with the same digest.
    assert replay.returncode == 0
    assert output(replay) == output(first) == {
        "decision": "ACCEPTED",
        "reason_codes": [],
        "receipt_digest": fixture.receipt_digest,
        "semantic_pass": True,
    }


def test_first_provenance_valid_rejection_is_terminal_and_idempotent(tmp_path: Path) -> None:
    # Given: the first provenance-valid terminal receipt is a semantic rejection.
    fixture = build_replay_fixture(
        tmp_path / "rejected",
        "exec-replay-rejected",
        final_approved=False,
    )
    pin_db = tmp_path / "pins.sqlite3"

    # When: it is first evaluated and later replayed after freshness expiry.
    first = run_verifier(fixture, pin_db)
    replay = run_verifier(fixture, pin_db, STALE_NOW)

    # Then: rejection is pinned exactly like approval and remains the terminal decision.
    assert first.returncode == replay.returncode == 2
    assert output(replay) == output(first) == {
        "decision": "NOT_ACCEPTED",
        "reason_codes": ["FINAL_APPROVAL_FALSE"],
        "receipt_digest": fixture.receipt_digest,
        "semantic_pass": False,
    }


def test_inconsistent_terminal_claim_does_not_reserve_execution_id(tmp_path: Path) -> None:
    # Given: an inconsistent approval claim and a corrected receipt share one execution ID.
    pin_db = tmp_path / "pins.sqlite3"
    inconsistent = build_replay_fixture(
        tmp_path / "inconsistent",
        "exec-not-reserved",
        score_ppm=799999,
    )
    corrected = build_replay_fixture(
        tmp_path / "corrected",
        "exec-not-reserved",
    )
    # When: the inconsistent claim is evaluated before the corrected receipt.
    inconsistent_result = run_verifier(inconsistent, pin_db)
    corrected_result = run_verifier(corrected, pin_db)

    # Then: only the corrected provenance-valid terminal receipt establishes the pin.
    assert inconsistent_result.returncode == 2
    assert output(inconsistent_result)["reason_codes"] == [
        "FIELD_INCONSISTENCY",
        "SCORE_BELOW_THRESHOLD",
    ]
    assert corrected_result.returncode == 0
    with sqlite3.connect(pin_db) as connection:
        rows = connection.execute(
            "SELECT receipt_digest FROM pins WHERE execution_id = ?",
            (corrected.execution_id,),
        ).fetchall()
    assert rows == [(corrected.receipt_digest,)]


def test_different_digest_for_pinned_execution_is_recorded_as_equivocation(tmp_path: Path) -> None:
    # Given: one receipt digest is already pinned for an execution.
    pin_db = tmp_path / "pins.sqlite3"
    first = build_replay_fixture(tmp_path / "first", "exec-equivocation")
    conflicting = build_replay_fixture(tmp_path / "conflicting", "exec-equivocation")
    assert run_verifier(first, pin_db).returncode == 0

    # When: a different receipt digest is presented for the same execution.
    completed = run_verifier(conflicting, pin_db)

    # Then: the first pin is immutable and the conflict is retained as metadata.
    assert completed.returncode == 2
    assert output(completed) == {
        "decision": "NOT_ACCEPTED",
        "reason_codes": ["RECEIPT_EQUIVOCATION"],
        "receipt_digest": conflicting.receipt_digest,
        "semantic_pass": False,
    }
    with sqlite3.connect(pin_db) as connection:
        pinned = connection.execute(
            "SELECT receipt_digest FROM pins WHERE execution_id = ?",
            (first.execution_id,),
        ).fetchone()
        conflicts = connection.execute(
            "SELECT conflicting_receipt_digest FROM equivocations",
        ).fetchall()
    assert pinned == (first.receipt_digest,)
    assert conflicts == [(conflicting.receipt_digest,)]


def test_invalid_conflict_fails_at_protocol_stage_before_equivocation(tmp_path: Path) -> None:
    # Given: an execution is pinned and a conflicting envelope is not authenticated.
    pin_db = tmp_path / "pins.sqlite3"
    first = build_replay_fixture(tmp_path / "first-invalid", "exec-invalid-conflict")
    conflicting = build_replay_fixture(
        tmp_path / "conflicting-invalid",
        "exec-invalid-conflict",
    )
    assert run_verifier(first, pin_db).returncode == 0
    envelope = json.loads(conflicting.receipt_path.read_text(encoding="utf-8"))
    signature = envelope["signature"]
    envelope["signature"] = ("A" if signature[0] != "A" else "B") + signature[1:]
    conflicting.receipt_path.write_text(json.dumps(envelope), encoding="utf-8")

    # When: the invalid conflict reaches the pin-aware verifier.
    completed = run_verifier(conflicting, pin_db)

    # Then: mandatory signature validation fails first and no conflict is retained.
    assert completed.returncode == 2
    assert output(completed)["reason_codes"] == ["SIGNATURE_INVALID"]
    with sqlite3.connect(pin_db) as connection:
        conflicts = connection.execute("SELECT COUNT(*) FROM equivocations").fetchone()
    assert conflicts == (0,)


def test_concurrent_terminal_receipts_cross_one_atomic_pin_boundary(tmp_path: Path) -> None:
    # Given: two provenance-valid terminal receipts target one unpinned execution.
    pin_db = tmp_path / "pins.sqlite3"
    candidates = [
        build_replay_fixture(tmp_path / "race-a", "exec-race"),
        build_replay_fixture(tmp_path / "race-b", "exec-race"),
    ]

    # When: independent evaluator processes present both receipts concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_verifier, candidate, pin_db) for candidate in candidates]
        completed = [future.result() for future in futures]

    # Then: atomic uniqueness preserves one first pin and classifies the other as equivocation.
    assert sorted(result.returncode for result in completed) == [0, 2]
    reason_lists = [output(result)["reason_codes"] for result in completed]
    assert reason_lists.count([]) == 1
    assert reason_lists.count(["RECEIPT_EQUIVOCATION"]) == 1
    with sqlite3.connect(pin_db) as connection:
        pin_count = connection.execute("SELECT COUNT(*) FROM pins").fetchone()
        conflict_count = connection.execute("SELECT COUNT(*) FROM equivocations").fetchone()
    assert pin_count == (1,)
    assert conflict_count == (1,)


def test_retry_requires_existing_tombstone_and_new_linked_execution_id(tmp_path: Path) -> None:
    # Given: a terminal original execution and both linked and orphan retry receipts.
    pin_db = tmp_path / "pins.sqlite3"
    original = build_replay_fixture(tmp_path / "original", "exec-original")
    linked = build_replay_fixture(
        tmp_path / "linked",
        "exec-retry-1",
        retry_of_execution_id=original.execution_id,
    )
    orphan = build_replay_fixture(
        tmp_path / "orphan",
        "exec-retry-orphan",
        retry_of_execution_id="exec-never-seen",
    )
    assert run_verifier(original, pin_db).returncode == 0
    original.receipt_path.unlink()

    # When: the linked retry and orphan retry are evaluated.
    linked_result = run_verifier(linked, pin_db)
    orphan_result = run_verifier(orphan, pin_db)

    # Then: only the fresh execution linked to a durable tombstone can be pinned.
    assert linked_result.returncode == 0
    assert orphan_result.returncode == 2
    assert output(orphan_result)["reason_codes"] == ["RETRY_LINK_INVALID"]
    with sqlite3.connect(pin_db) as connection:
        rows = connection.execute(
            "SELECT execution_id, retry_of_execution_id FROM pins ORDER BY execution_id",
        ).fetchall()
    assert rows == [
        ("exec-original", None),
        ("exec-retry-1", "exec-original"),
    ]


def test_exact_replay_rechecks_current_artifact_binding(tmp_path: Path) -> None:
    # Given: an approval is pinned and the package artifact is later changed.
    fixture = build_replay_fixture(tmp_path / "artifact", "exec-replay-artifact")
    pin_db = tmp_path / "pins.sqlite3"
    assert run_verifier(fixture, pin_db).returncode == 0
    (fixture.artifact_root / "document.bin").write_bytes(b"changed after pinning")

    # When: the exact pinned receipt is replayed.
    completed = run_verifier(fixture, pin_db, STALE_NOW)

    # Then: current binding failure prevents reuse of the stored approval.
    assert completed.returncode == 2
    assert output(completed)["reason_codes"] == ["ARTIFACT_BINDING_MISMATCH"]
