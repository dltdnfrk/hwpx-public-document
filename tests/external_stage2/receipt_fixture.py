from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.external_stage2.loader import load

schemas = load("external_stage2.schemas")


NOW: Final = "2026-08-13T12:00:00.000Z"
EXECUTION_ID: Final = "exec-ac3-001"
KEY_ID: Final = "stage2-key-1"
EVALUATOR_ID: Final = "ouroboros-stage2"
EVALUATOR_BUILD_SHA256: Final = "1" * 64


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class ReceiptFixture:
    root: Path
    artifact_root: Path
    receipt_path: Path
    policy_path: Path
    request_path: Path
    result_path: Path
    manifest_path: Path
    receipt_digest: str
    # Orchestrator-owned trust anchor: SHA-256 of the exact policy snapshot
    # bytes, passed to the verifier out of band (--trust-policy-sha256).
    policy_sha256_pin: str


def build_fixture(
    root: Path,
    final_approved: bool = True,
    score_ppm: int = 800000,
) -> ReceiptFixture:
    artifact_root = root / "package-copy"
    artifact_root.mkdir()
    artifact = artifact_root / "document.bin"
    artifact.write_bytes(b"bound candidate artifact\n")

    # The established key set comes from the closed v1 manifest schema —
    # the single normative source — never regenerated locally.
    manifest_keys = sorted(schemas.MANIFEST_KEYS_V1)
    manifest: dict[str, str | bool | int | dict[str, bool]] = {
        key: f"value-{index}" for index, key in enumerate(manifest_keys)
    }
    manifest[manifest_keys[0]] = "PASS"
    manifest[manifest_keys[1]] = True
    manifest[manifest_keys[2]] = 1000000
    manifest[manifest_keys[3]] = {"independentlyProduced": True}
    manifest_path = root / "manifest.json"
    manifest_path.write_bytes(canonical(manifest))

    artifact_tree = [
        {
            "path": "document.bin",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "size_bytes": artifact.stat().st_size,
        }
    ]
    artifact_tree_sha256 = digest(artifact_tree)
    manifest_jcs_sha256 = digest(manifest)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    policy = {
        "evaluators": [
            {
                "evaluator_build_sha256": EVALUATOR_BUILD_SHA256,
                "evaluator_id": EVALUATOR_ID,
            }
        ],
        "keys": [
            {
                "authorized_from": "2026-08-13T00:00:00.000Z",
                "authorized_until": "2026-08-14T00:00:00.000Z",
                "ed25519_public_key_b64url": b64url(public_key),
                "key_id": KEY_ID,
            }
        ],
        "policy_id": "stage2-semantic-v1",
        "project_id": "hwpx-public-document",
        "snapshot_version": 1,
    }
    policy_path = root / "policy.json"
    policy_path.write_bytes(canonical(policy))
    policy_sha256 = digest(policy)

    request = {
        "artifact_tree_sha256": artifact_tree_sha256,
        "evaluator_build_sha256": EVALUATOR_BUILD_SHA256,
        "evaluator_id": EVALUATOR_ID,
        "execution_id": EXECUTION_ID,
        "manifest_jcs_sha256": manifest_jcs_sha256,
        "policy_id": "stage2-semantic-v1",
        "policy_sha256": policy_sha256,
        "project_id": "hwpx-public-document",
        "request_version": 1,
        "requested_at": "2026-08-13T11:59:59.000Z",
        "stage": "stage2",
    }
    request_path = root / "stage2-request.json"
    request_path.write_bytes(canonical(request))
    request_sha256 = digest(request)

    result = {
        "artifact_tree_sha256": artifact_tree_sha256,
        "completed_at": "2026-08-13T12:00:00.000Z",
        "evaluator_build_sha256": EVALUATOR_BUILD_SHA256,
        "evaluator_id": EVALUATOR_ID,
        "execution_id": EXECUTION_ID,
        "final_approved": final_approved,
        "manifest_jcs_sha256": manifest_jcs_sha256,
        "policy_id": "stage2-semantic-v1",
        "policy_sha256": policy_sha256,
        "project_id": "hwpx-public-document",
        "result_version": 1,
        "score_ppm": score_ppm,
        "semantic_reason_codes": [] if final_approved else ["STAGE2_REJECTED"],
        "stage": "stage2",
        "stage2_request_jcs_sha256": request_sha256,
    }
    result_path = root / "stage2-result.json"
    result_path.write_bytes(canonical(result))

    payload = {
        "artifact_tree_sha256": artifact_tree_sha256,
        "evaluator_build_sha256": EVALUATOR_BUILD_SHA256,
        "evaluator_id": EVALUATOR_ID,
        "execution_id": EXECUTION_ID,
        "final_approved": final_approved,
        "issued_at": NOW,
        "manifest_jcs_sha256": manifest_jcs_sha256,
        "policy_id": "stage2-semantic-v1",
        "policy_sha256": policy_sha256,
        "project_id": "hwpx-public-document",
        "receipt_id": "1e8a90ac-764a-4f86-810f-1f6ffde40f22",
        "receipt_version": 1,
        "score_ppm": score_ppm,
        "stage": "stage2",
        "stage2_request_jcs_sha256": request_sha256,
        "stage2_result_jcs_sha256": digest(result),
    }
    payload_bytes = canonical(payload)
    payload_text = b64url(payload_bytes)
    signed_message = (
        b"ouroboros-stage2-receipt-v1\0"
        + KEY_ID.encode("utf-8")
        + b"\0"
        + payload_bytes
    )
    envelope = {
        "key_id": KEY_ID,
        "payload": payload_text,
        "schema_version": 1,
        "signature": b64url(private_key.sign(signed_message)),
    }
    receipt_path = root / "stage2-receipt.json"
    receipt_path.write_bytes(canonical(envelope))
    return ReceiptFixture(
        root=root,
        artifact_root=artifact_root,
        receipt_path=receipt_path,
        policy_path=policy_path,
        request_path=request_path,
        result_path=result_path,
        manifest_path=manifest_path,
        receipt_digest=digest(envelope),
        policy_sha256_pin=hashlib.sha256(policy_path.read_bytes()).hexdigest(),
    )
