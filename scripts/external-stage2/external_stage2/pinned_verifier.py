from __future__ import annotations

import base64
import hashlib
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional, Tuple

from .canonical_json import StrictJsonError, canonicalize, parse_strict
from .contract import ContractError, parse_timestamp
from .pin_store import PinRecord, PinStore
from .schemas import Envelope, ReceiptPayload
from .verifier import RECEIPT_LIMIT, VerificationDecision, VerificationInputs, verify


PROJECT_ID = "hwpx-public-document"


@dataclass(frozen=True)
class PinnedVerificationInputs:
    verification: VerificationInputs
    pin_db_path: Path


def verify_with_pinning(inputs: PinnedVerificationInputs) -> VerificationDecision:
    try:
        return _verify_with_pinning(inputs)
    except (OSError, sqlite3.Error, UnicodeError, ValueError):
        return VerificationDecision(False, None, ("INTERNAL_VERIFIER_ERROR",))


def _verify_with_pinning(inputs: PinnedVerificationInputs) -> VerificationDecision:
    receipt_digest = _receipt_digest(inputs.verification.receipt_path)
    store = PinStore(inputs.pin_db_path)
    store.initialize()
    pinned = store.get(PROJECT_ID, inputs.verification.execution_id)
    if pinned is not None and pinned.receipt_digest == receipt_digest:
        return _verify_exact_replay(inputs.verification, pinned)

    decision = verify(inputs.verification)
    if decision.receipt_digest is None:
        return decision
    if "FIELD_INCONSISTENCY" in decision.reason_codes:
        return decision
    retry_id, issued_at = _trusted_execution_fields(inputs.verification.receipt_path)
    outcome = store.pin_first(
        PROJECT_ID,
        inputs.verification.execution_id,
        decision.receipt_digest,
        decision.semantic_pass,
        decision.reason_codes,
        issued_at,
        retry_id,
    )
    if outcome.status == "EQUIVOCATION":
        return VerificationDecision(
            False,
            decision.receipt_digest,
            ("RECEIPT_EQUIVOCATION",),
        )
    if outcome.status == "RETRY_LINK_INVALID":
        return VerificationDecision(False, decision.receipt_digest, ("RETRY_LINK_INVALID",))
    if outcome.status == "IDEMPOTENT" and outcome.record is not None:
        return _stored_decision(outcome.record)
    return decision


def _verify_exact_replay(
    inputs: VerificationInputs,
    pinned: PinRecord,
) -> VerificationDecision:
    replay_now = parse_timestamp(pinned.issued_at, "INTERNAL_VERIFIER_ERROR")
    current = verify(replace(inputs, now=replay_now))
    if current.receipt_digest != pinned.receipt_digest:
        return current
    return _stored_decision(pinned)


def _stored_decision(pinned: PinRecord) -> VerificationDecision:
    return VerificationDecision(
        pinned.semantic_pass,
        pinned.receipt_digest,
        pinned.reason_codes,
    )


def _receipt_digest(path: Path) -> str:
    try:
        if path.stat().st_size > RECEIPT_LIMIT:
            raise ContractError("RECEIPT_OVERSIZED")
        raw = path.read_bytes()
        value = parse_strict(raw)
        Envelope.parse(value)
    except (OSError, StrictJsonError, ContractError):
        return ""
    return hashlib.sha256(canonicalize(value)).hexdigest()


def _trusted_execution_fields(path: Path) -> Tuple[Optional[str], str]:
    envelope = Envelope.parse(parse_strict(path.read_bytes()))
    padding = "=" * ((4 - len(envelope.payload) % 4) % 4)
    payload = ReceiptPayload.parse(
        parse_strict(base64.urlsafe_b64decode(envelope.payload + padding))
    )
    retry = payload.data.get("retry_of_execution_id")
    issued_at = payload.data["issued_at"]
    if retry is not None and not isinstance(retry, str):
        raise ContractError("RETRY_LINK_INVALID")
    if not isinstance(issued_at, str):
        raise ContractError("RECEIPT_SCHEMA_INVALID")
    return retry, issued_at
