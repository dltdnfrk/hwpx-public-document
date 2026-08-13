from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Final, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .artifact_tree import artifact_tree_digest
from .canonical_json import JsonValue, StrictJsonError, canonicalize, parse_strict, sha256_jcs
from .contract import ContractError

schemas = importlib.import_module("external_stage2.schemas")


RECEIPT_LIMIT: Final = 65536
PAYLOAD_LIMIT: Final = 16384
SIDECAR_LIMIT: Final = 65536
POLICY_LIMIT: Final = 262144
MANIFEST_LIMIT: Final = 1048576


@dataclass(frozen=True)
class VerificationInputs:
    receipt_path: Path
    policy_path: Path
    request_path: Path
    result_path: Path
    manifest_path: Path
    artifact_root: Path
    execution_id: str
    now: datetime
    # Orchestrator-owned trust anchor: lowercase hex SHA-256 of the exact
    # trust-policy snapshot bytes, supplied by the orchestrator out of band.
    # This pins policy provenance independently of the receipt's own
    # policy_sha256 claim, so a candidate cannot substitute a policy carrying
    # a self-generated key and self-sign an approving receipt.
    trust_policy_sha256: str


@dataclass(frozen=True)
class VerificationDecision:
    semantic_pass: bool
    receipt_digest: Optional[str]
    reason_codes: Tuple[str, ...]


def verify(inputs: VerificationInputs) -> VerificationDecision:
    try:
        return _verify(inputs)
    except ContractError as error:
        return VerificationDecision(False, None, (error.reason_code,))
    except (OSError, UnicodeError, ValueError):
        return VerificationDecision(False, None, ("INTERNAL_VERIFIER_ERROR",))


def _verify(inputs: VerificationInputs) -> VerificationDecision:
    # Stage (1): deterministic byte-limit prechecks over every declared input.
    # The trust-policy snapshot must be orchestrator-owned material located
    # outside the evaluated package copy; package-root-internal data is never
    # trusted as a policy source.
    receipt_raw = _read_receipt(inputs.receipt_path)
    _require_policy_outside_package(inputs.policy_path, inputs.artifact_root)
    policy_raw = _read_limited(inputs.policy_path, POLICY_LIMIT, "POLICY_SNAPSHOT_INVALID", "POLICY_SNAPSHOT_INVALID")
    request_raw = _read_limited(inputs.request_path, SIDECAR_LIMIT, "SIDECAR_OVERSIZED", "REQUEST_SCHEMA_INVALID")
    result_raw = _read_limited(inputs.result_path, SIDECAR_LIMIT, "SIDECAR_OVERSIZED", "RESULT_SCHEMA_INVALID")
    manifest_raw = _read_limited(inputs.manifest_path, MANIFEST_LIMIT, "MANIFEST_BINDING_MISMATCH", "MANIFEST_BINDING_MISMATCH")

    # Stages (2)-(3): strict receipt parsing and closed envelope schema.
    envelope_value = _parse(receipt_raw, "RECEIPT_PARSE_INVALID")
    envelope = schemas.Envelope.parse(envelope_value)
    # Stage (4): canonical unpadded base64url decoding.
    payload_raw = _decode_b64url(envelope.payload, PAYLOAD_LIMIT, "RECEIPT_OVERSIZED", "RECEIPT_SCHEMA_INVALID")
    signature = _decode_b64url(envelope.signature, 64, "RECEIPT_SCHEMA_INVALID", "RECEIPT_SCHEMA_INVALID")
    if len(signature) != 64:
        raise ContractError("RECEIPT_SCHEMA_INVALID")

    # Stage (5): Ed25519 signature verification over the exact signed message.
    # Key-material resolution here is tentative: every trust-policy resolution
    # failure is deferred to stage (8) so it can never preempt the
    # receipt-first stages (5)-(7). When the key material does resolve, an
    # invalid signature terminates validation at this stage.
    policy_value: JsonValue = None
    policy = None
    key = None
    policy_error: Optional[ContractError] = None
    try:
        pin = inputs.trust_policy_sha256
        if (
            not isinstance(pin, str)
            or len(pin) != 64
            or any(character not in "0123456789abcdef" for character in pin)
            or hashlib.sha256(policy_raw).hexdigest() != pin
        ):
            raise ContractError("POLICY_SNAPSHOT_INVALID")
        policy_value = _parse(policy_raw, "POLICY_SNAPSHOT_INVALID")
        policy = schemas.TrustPolicy.parse(policy_value)
        key = next((candidate for candidate in policy.keys if candidate.key_id == envelope.key_id), None)
        if key is None:
            raise ContractError("SIGNER_UNAUTHORIZED")
        public_key = _decode_b64url(key.public_key_text, 32, "POLICY_SNAPSHOT_INVALID", "POLICY_SNAPSHOT_INVALID")
        if len(public_key) != 32:
            raise ContractError("POLICY_SNAPSHOT_INVALID")
    except ContractError as error:
        policy_error = error
    if policy_error is None:
        signed_message = (
            b"ouroboros-stage2-receipt-v1\0"
            + envelope.key_id.encode("utf-8")
            + b"\0"
            + payload_raw
        )
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, signed_message)
        except InvalidSignature as error:
            raise ContractError("SIGNATURE_INVALID") from error

    # Stage (6): strict payload parse and JCS byte-identity check.
    payload_value = _parse(payload_raw, "RECEIPT_SCHEMA_INVALID")
    if canonicalize(payload_value) != payload_raw:
        raise ContractError("RECEIPT_SCHEMA_INVALID")
    # Stage (7): closed payload schema validation.
    payload = schemas.ReceiptPayload.parse(payload_value)

    # Stage (8): trust-policy snapshot resolution with signer authorization
    # and revocation evaluated at issued_at.
    if policy_error is not None:
        raise policy_error
    assert policy is not None and key is not None
    if not key.authorized_from <= payload.issued_at < key.authorized_until:
        raise ContractError("SIGNER_UNAUTHORIZED")
    if key.revoked_at is not None and payload.issued_at >= key.revoked_at:
        raise ContractError("SIGNER_REVOKED")
    # Stage (9): policy and evaluator recognition.
    if sha256_jcs(policy_value) != payload.data["policy_sha256"]:
        raise ContractError("POLICY_MISMATCH")
    evaluator = (
        str(payload.data["evaluator_id"]),
        str(payload.data["evaluator_build_sha256"]),
    )
    if evaluator not in policy.evaluators:
        raise ContractError("EVALUATOR_MISMATCH")
    # Stage (10): execution identity validation (payload-internal retry
    # linkage is enforced by the closed payload schema at stage (7)).
    if payload.data["execution_id"] != inputs.execution_id:
        raise ContractError("EXECUTION_MISMATCH")
    # Stage (11): freshness-window validation.
    if payload.issued_at < inputs.now - timedelta(seconds=600):
        raise ContractError("RECEIPT_STALE")
    if payload.issued_at > inputs.now + timedelta(seconds=30):
        raise ContractError("RECEIPT_FUTURE")

    # Stage (12): sidecar validation and recomputed digest bindings.
    request_value = _parse(request_raw, "REQUEST_SCHEMA_INVALID")
    request = schemas.Stage2Request.parse(request_value)
    result_value = _parse(result_raw, "RESULT_SCHEMA_INVALID")
    result = schemas.Stage2Result.parse(result_value)
    if result.completed_at < request.requested_at:
        raise ContractError("FIELD_INCONSISTENCY")
    _require_context_agreement(payload.data, request.data, result.data)

    current_artifact = artifact_tree_digest(inputs.artifact_root)
    current_manifest_value = _parse(manifest_raw, "MANIFEST_BINDING_MISMATCH")
    _require_established_manifest(current_manifest_value)
    if current_artifact != payload.data["artifact_tree_sha256"]:
        raise ContractError("ARTIFACT_BINDING_MISMATCH")
    if sha256_jcs(current_manifest_value) != payload.data["manifest_jcs_sha256"]:
        raise ContractError("MANIFEST_BINDING_MISMATCH")
    if sha256_jcs(request_value) != payload.data["stage2_request_jcs_sha256"]:
        raise ContractError("REQUEST_BINDING_MISMATCH")
    if sha256_jcs(result_value) != payload.data["stage2_result_jcs_sha256"]:
        raise ContractError("RESULT_BINDING_MISMATCH")

    # Stage (13): semantic evaluation of the authenticated verdict.
    semantic_reasons = set()
    if payload.data["final_approved"] is not True:
        semantic_reasons.add("FINAL_APPROVAL_FALSE")
    score = payload.data["score_ppm"]
    if isinstance(score, int) and score < 800000:
        semantic_reasons.add("SCORE_BELOW_THRESHOLD")
        if payload.data["final_approved"] is True:
            semantic_reasons.add("FIELD_INCONSISTENCY")
    if semantic_reasons:
        return VerificationDecision(
            False,
            hashlib.sha256(canonicalize(envelope_value)).hexdigest(),
            tuple(sorted(semantic_reasons)),
        )
    return VerificationDecision(
        True,
        hashlib.sha256(canonicalize(envelope_value)).hexdigest(),
        (),
    )


def _require_policy_outside_package(policy_path: Path, artifact_root: Path) -> None:
    """Reject trust-policy snapshots that are not orchestrator-owned files.

    The snapshot must be an immutable regular file that lives outside the
    evaluated package copy; a policy reachable from the candidate-controlled
    package root could be substituted by the candidate and is never trusted.
    """
    if policy_path.is_symlink():
        raise ContractError("POLICY_SNAPSHOT_INVALID")
    try:
        policy_real = policy_path.resolve()
        root_real = artifact_root.resolve()
    except (OSError, RuntimeError) as error:
        raise ContractError("POLICY_SNAPSHOT_INVALID") from error
    if policy_real == root_real or root_real in policy_real.parents:
        raise ContractError("POLICY_SNAPSHOT_INVALID")


def _require_established_manifest(value: JsonValue) -> None:
    """Validate the manifest against the vendored product 89-key schema.

    The established definition-path set is derived from the brownfield
    format-capability artifact. Missing, unknown, or structurally different
    keys are binding failures. Compatibility fields PASS, approval, score,
    and independentlyProduced may remain as extra data; they are never
    interpreted for authorization and are only bound by manifest_jcs_sha256.
    """
    schemas.require_established_manifest(value)


def _require_context_agreement(
    payload: Dict[str, JsonValue],
    request: Dict[str, JsonValue],
    result: Dict[str, JsonValue],
) -> None:
    identity_fields = {
        "project_id", "execution_id", "stage", "policy_id", "policy_sha256",
        "evaluator_id", "evaluator_build_sha256", "artifact_tree_sha256",
        "manifest_jcs_sha256",
    }
    for field in identity_fields:
        if payload[field] != request[field] or request[field] != result[field]:
            raise ContractError("FIELD_INCONSISTENCY")
    if result["stage2_request_jcs_sha256"] != payload["stage2_request_jcs_sha256"]:
        raise ContractError("FIELD_INCONSISTENCY")
    if result["final_approved"] != payload["final_approved"] or result["score_ppm"] != payload["score_ppm"]:
        raise ContractError("FIELD_INCONSISTENCY")
    payload_retry = payload.get("retry_of_execution_id")
    request_retry = request.get("retry_of_execution_id")
    if payload_retry != request_retry:
        raise ContractError("RETRY_LINK_INVALID")


def _read_limited(path: Path, limit: int, oversized: str, invalid: str) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ContractError(invalid) from error
    if size > limit:
        raise ContractError(oversized)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ContractError(invalid) from error
    if not raw:
        raise ContractError(invalid)
    return raw


def _read_receipt(path: Path) -> bytes:
    try:
        size = path.stat().st_size
    except FileNotFoundError as error:
        raise ContractError("RECEIPT_MISSING") from error
    except OSError as error:
        raise ContractError("RECEIPT_PARSE_INVALID") from error
    if size > RECEIPT_LIMIT:
        raise ContractError("RECEIPT_OVERSIZED")
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise ContractError("RECEIPT_MISSING") from error
    except OSError as error:
        raise ContractError("RECEIPT_PARSE_INVALID") from error
    if not raw:
        raise ContractError("RECEIPT_PARSE_INVALID")
    return raw


def _parse(raw: bytes, reason: str) -> JsonValue:
    try:
        return parse_strict(raw)
    except StrictJsonError as error:
        if reason == "RECEIPT_PARSE_INVALID" and error.detail == "duplicate JSON key":
            raise ContractError("RECEIPT_SCHEMA_INVALID") from error
        raise ContractError(reason) from error


def _decode_b64url(text: str, limit: int, oversized: str, invalid: str) -> bytes:
    if not text or "=" in text or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for character in text):
        raise ContractError(invalid)
    padding = "=" * ((4 - len(text) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(text + padding)
    except (binascii.Error, ValueError) as error:
        raise ContractError(invalid) from error
    if len(decoded) > limit:
        raise ContractError(oversized)
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != text:
        raise ContractError(invalid)
    return decoded
