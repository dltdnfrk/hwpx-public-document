from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Final, FrozenSet, List, Optional, Set

from .canonical_json import JsonValue
from .contract import (
    ContractError,
    parse_timestamp,
    require_bool,
    require_const,
    require_digest,
    require_fields,
    require_identifier,
    require_identity_fields,
    require_int,
    require_object,
    require_reason_codes,
    require_string,
)


# Established 89-key manifest schema (v1). The key-name set is normative for
# the preserved compatibility manifest: a bound manifest must contain exactly
# these keys. Manifest values stay untrusted compatibility data; they are
# digest-bound via manifest_jcs_sha256 and never interpreted for
# authorization. Any key-schema change requires a new version and a new or
# updated Seed.
MANIFEST_KEYS_V1: Final[FrozenSet[str]] = frozenset(
    "manifest_key_{index:02d}".format(index=index) for index in range(89)
)


@dataclass(frozen=True)
class Envelope:
    key_id: str
    payload: str
    signature: str

    @classmethod
    def parse(cls, value: JsonValue) -> "Envelope":
        reason = "RECEIPT_SCHEMA_INVALID"
        data = require_object(value, reason)
        require_fields(data, {"schema_version", "key_id", "payload", "signature"}, set(), reason)
        require_const(data["schema_version"], 1, reason)
        return cls(
            key_id=require_identifier(data["key_id"], reason),
            payload=require_string(data["payload"], reason),
            signature=require_string(data["signature"], reason),
        )


@dataclass(frozen=True)
class ReceiptPayload:
    data: Dict[str, JsonValue]
    issued_at: datetime

    @classmethod
    def parse(cls, value: JsonValue) -> "ReceiptPayload":
        reason = "RECEIPT_SCHEMA_INVALID"
        data = require_object(value, reason)
        required = {
            "receipt_version", "receipt_id", "project_id", "execution_id", "stage",
            "policy_id", "policy_sha256", "evaluator_id", "evaluator_build_sha256",
            "issued_at", "artifact_tree_sha256", "manifest_jcs_sha256",
            "stage2_request_jcs_sha256", "stage2_result_jcs_sha256",
            "final_approved", "score_ppm",
        }
        require_fields(data, required, {"retry_of_execution_id"}, reason)
        require_const(data["receipt_version"], 1, reason)
        receipt_id = require_string(data["receipt_id"], reason)
        from .contract import UUID4
        if UUID4.fullmatch(receipt_id) is None:
            raise ContractError(reason)
        require_identity_fields(data, reason)
        require_digest(data["stage2_request_jcs_sha256"], reason)
        require_digest(data["stage2_result_jcs_sha256"], reason)
        require_bool(data["final_approved"], reason)
        require_int(data["score_ppm"], 0, 1000000, reason)
        _validate_retry(data, reason)
        return cls(data=data, issued_at=parse_timestamp(data["issued_at"], reason))


@dataclass(frozen=True)
class Stage2Request:
    data: Dict[str, JsonValue]
    requested_at: datetime

    @classmethod
    def parse(cls, value: JsonValue) -> "Stage2Request":
        reason = "REQUEST_SCHEMA_INVALID"
        data = require_object(value, reason)
        required = {
            "request_version", "project_id", "execution_id", "stage", "policy_id",
            "policy_sha256", "evaluator_id", "evaluator_build_sha256",
            "artifact_tree_sha256", "manifest_jcs_sha256", "requested_at",
        }
        require_fields(data, required, {"retry_of_execution_id"}, reason)
        require_const(data["request_version"], 1, reason)
        require_identity_fields(data, reason)
        _validate_retry(data, reason)
        return cls(data=data, requested_at=parse_timestamp(data["requested_at"], reason))


@dataclass(frozen=True)
class Stage2Result:
    data: Dict[str, JsonValue]
    completed_at: datetime
    reason_codes: List[str]

    @classmethod
    def parse(cls, value: JsonValue) -> "Stage2Result":
        reason = "RESULT_SCHEMA_INVALID"
        data = require_object(value, reason)
        required = {
            "result_version", "project_id", "execution_id", "stage", "policy_id",
            "policy_sha256", "evaluator_id", "evaluator_build_sha256",
            "artifact_tree_sha256", "manifest_jcs_sha256", "stage2_request_jcs_sha256",
            "final_approved", "score_ppm", "semantic_reason_codes", "completed_at",
        }
        require_fields(data, required, set(), reason)
        require_const(data["result_version"], 1, reason)
        require_identity_fields(data, reason)
        require_digest(data["stage2_request_jcs_sha256"], reason)
        approved = require_bool(data["final_approved"], reason)
        require_int(data["score_ppm"], 0, 1000000, reason)
        codes = require_reason_codes(data["semantic_reason_codes"])
        if (approved and codes) or (not approved and not codes):
            raise ContractError(reason)
        return cls(
            data=data,
            completed_at=parse_timestamp(data["completed_at"], reason),
            reason_codes=codes,
        )


@dataclass(frozen=True)
class PolicyKey:
    key_id: str
    public_key_text: str
    authorized_from: datetime
    authorized_until: datetime
    revoked_at: Optional[datetime]


@dataclass(frozen=True)
class TrustPolicy:
    data: Dict[str, JsonValue]
    evaluators: Set[tuple[str, str]]
    keys: List[PolicyKey]

    @classmethod
    def parse(cls, value: JsonValue) -> "TrustPolicy":
        reason = "POLICY_SNAPSHOT_INVALID"
        data = require_object(value, reason)
        require_fields(
            data,
            {"snapshot_version", "project_id", "policy_id", "evaluators", "keys"},
            set(),
            reason,
        )
        require_const(data["snapshot_version"], 1, reason)
        require_const(data["project_id"], "hwpx-public-document", reason)
        require_const(data["policy_id"], "stage2-semantic-v1", reason)
        evaluators_value = data["evaluators"]
        keys_value = data["keys"]
        if not isinstance(evaluators_value, list) or not evaluators_value:
            raise ContractError(reason)
        if not isinstance(keys_value, list) or not keys_value:
            raise ContractError(reason)
        evaluators: Set[tuple[str, str]] = set()
        for item in evaluators_value:
            evaluator = require_object(item, reason)
            require_fields(evaluator, {"evaluator_id", "evaluator_build_sha256"}, set(), reason)
            pair = (
                require_identifier(evaluator["evaluator_id"], reason),
                require_digest(evaluator["evaluator_build_sha256"], reason),
            )
            if pair in evaluators:
                raise ContractError(reason)
            evaluators.add(pair)
        keys = [_parse_policy_key(item, reason) for item in keys_value]
        if len({key.key_id for key in keys}) != len(keys):
            raise ContractError(reason)
        return cls(data=data, evaluators=evaluators, keys=keys)


def _parse_policy_key(value: JsonValue, reason: str) -> PolicyKey:
    data = require_object(value, reason)
    require_fields(
        data,
        {"key_id", "ed25519_public_key_b64url", "authorized_from", "authorized_until"},
        {"revoked_at"},
        reason,
    )
    authorized_from = parse_timestamp(data["authorized_from"], reason)
    authorized_until = parse_timestamp(data["authorized_until"], reason)
    if authorized_from >= authorized_until:
        raise ContractError(reason)
    revoked = parse_timestamp(data["revoked_at"], reason) if "revoked_at" in data else None
    return PolicyKey(
        key_id=require_identifier(data["key_id"], reason),
        public_key_text=require_string(data["ed25519_public_key_b64url"], reason),
        authorized_from=authorized_from,
        authorized_until=authorized_until,
        revoked_at=revoked,
    )


def _validate_retry(data: Dict[str, JsonValue], reason: str) -> None:
    if "retry_of_execution_id" not in data:
        return
    retry = require_identifier(data["retry_of_execution_id"], reason)
    execution = require_identifier(data["execution_id"], reason)
    if retry == execution:
        raise ContractError("RETRY_LINK_INVALID")
