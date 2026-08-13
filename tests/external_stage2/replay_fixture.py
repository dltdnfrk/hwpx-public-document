from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


KEY_ID: Final = "stage2-key-replay"
EVALUATOR_ID: Final = "ouroboros-stage2"
EVALUATOR_BUILD_SHA256: Final = "2" * 64
ISSUED_AT: Final = "2026-08-13T12:00:00.000Z"


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class ReplayFixture:
    artifact_root: Path
    receipt_path: Path
    policy_path: Path
    request_path: Path
    result_path: Path
    manifest_path: Path
    execution_id: str
    receipt_digest: str


def build_replay_fixture(
    root: Path,
    execution_id: str,
    retry_of_execution_id: Optional[str] = None,
    final_approved: bool = True,
    score_ppm: int = 800000,
) -> ReplayFixture:
    root.mkdir()
    artifact_root = root / "package-copy"
    artifact_root.mkdir()
    artifact = artifact_root / "document.bin"
    artifact.write_bytes(b"replay-bound candidate artifact\n")
    artifact_tree = [{
        "path": "document.bin",
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "size_bytes": artifact.stat().st_size,
    }]
    artifact_tree_sha256 = digest(artifact_tree)

    manifest = {f"manifest_key_{index:02d}": f"value-{index}" for index in range(89)}
    manifest_path = root / "manifest.json"
    manifest_path.write_bytes(canonical(manifest))
    manifest_jcs_sha256 = digest(manifest)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    policy = {
        "evaluators": [{
            "evaluator_build_sha256": EVALUATOR_BUILD_SHA256,
            "evaluator_id": EVALUATOR_ID,
        }],
        "keys": [{
            "authorized_from": "2026-08-13T00:00:00.000Z",
            "authorized_until": "2026-08-14T00:00:00.000Z",
            "ed25519_public_key_b64url": b64url(public_key),
            "key_id": KEY_ID,
        }],
        "policy_id": "stage2-semantic-v1",
        "project_id": "hwpx-public-document",
        "snapshot_version": 1,
    }
    policy_path = root / "policy.json"
    policy_path.write_bytes(canonical(policy))
    policy_sha256 = digest(policy)

    identity = {
        "artifact_tree_sha256": artifact_tree_sha256,
        "evaluator_build_sha256": EVALUATOR_BUILD_SHA256,
        "evaluator_id": EVALUATOR_ID,
        "execution_id": execution_id,
        "manifest_jcs_sha256": manifest_jcs_sha256,
        "policy_id": "stage2-semantic-v1",
        "policy_sha256": policy_sha256,
        "project_id": "hwpx-public-document",
        "stage": "stage2",
    }
    request = {
        **identity,
        "request_version": 1,
        "requested_at": "2026-08-13T11:59:59.000Z",
    }
    if retry_of_execution_id is not None:
        request["retry_of_execution_id"] = retry_of_execution_id
    request_path = root / "stage2-request.json"
    request_path.write_bytes(canonical(request))

    result = {
        **identity,
        "completed_at": ISSUED_AT,
        "final_approved": final_approved,
        "result_version": 1,
        "score_ppm": score_ppm,
        "semantic_reason_codes": [] if final_approved else ["STAGE2_REJECTED"],
        "stage2_request_jcs_sha256": digest(request),
    }
    result_path = root / "stage2-result.json"
    result_path.write_bytes(canonical(result))

    payload = {
        **identity,
        "final_approved": final_approved,
        "issued_at": ISSUED_AT,
        "receipt_id": "1e8a90ac-764a-4f86-810f-1f6ffde40f22",
        "receipt_version": 1,
        "score_ppm": score_ppm,
        "stage2_request_jcs_sha256": digest(request),
        "stage2_result_jcs_sha256": digest(result),
    }
    if retry_of_execution_id is not None:
        payload["retry_of_execution_id"] = retry_of_execution_id
    payload_bytes = canonical(payload)
    envelope = {
        "key_id": KEY_ID,
        "payload": b64url(payload_bytes),
        "schema_version": 1,
        "signature": b64url(private_key.sign(
            b"ouroboros-stage2-receipt-v1\0"
            + KEY_ID.encode("utf-8")
            + b"\0"
            + payload_bytes
        )),
    }
    receipt_path = root / "stage2-receipt.json"
    receipt_path.write_bytes(canonical(envelope))
    return ReplayFixture(
        artifact_root=artifact_root,
        receipt_path=receipt_path,
        policy_path=policy_path,
        request_path=request_path,
        result_path=result_path,
        manifest_path=manifest_path,
        execution_id=execution_id,
        receipt_digest=digest(envelope),
    )
