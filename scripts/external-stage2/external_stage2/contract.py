from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Final, List, Optional, Set, Tuple

from .canonical_json import JsonValue


IDENTIFIER: Final = re.compile(r"^[A-Za-z0-9._:-]+$")
DIGEST: Final = re.compile(r"^[0-9a-f]{64}$")
REASON: Final = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
UUID4: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
TIMESTAMP: Final = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})Z$"
)


@dataclass(frozen=True)
class ContractError(Exception):
    reason_code: str

    def __str__(self) -> str:
        return self.reason_code


def require_object(value: JsonValue, reason: str) -> Dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ContractError(reason)
    return value


def require_fields(
    value: Dict[str, JsonValue],
    required: Set[str],
    optional: Set[str],
    reason: str,
) -> None:
    if set(value) - required - optional or required - set(value):
        raise ContractError(reason)
    if any(item is None for item in value.values()):
        raise ContractError(reason)


def require_string(value: JsonValue, reason: str) -> str:
    if not isinstance(value, str):
        raise ContractError(reason)
    return value


def require_bool(value: JsonValue, reason: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(reason)
    return value


def require_int(value: JsonValue, minimum: int, maximum: int, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(reason)
    if value < minimum or value > maximum:
        raise ContractError(reason)
    return value


def require_const(value: JsonValue, expected: JsonValue, reason: str) -> None:
    if value != expected or type(value) is not type(expected):
        raise ContractError(reason)


def require_identifier(value: JsonValue, reason: str) -> str:
    identifier = require_string(value, reason)
    size = len(identifier.encode("utf-8"))
    if not 1 <= size <= 128 or IDENTIFIER.fullmatch(identifier) is None:
        raise ContractError(reason)
    return identifier


def require_digest(value: JsonValue, reason: str) -> str:
    digest = require_string(value, reason)
    if DIGEST.fullmatch(digest) is None:
        raise ContractError(reason)
    return digest


def parse_timestamp(value: JsonValue, reason: str) -> datetime:
    text = require_string(value, reason)
    match = TIMESTAMP.fullmatch(text)
    if match is None or match.group(6) == "60":
        raise ContractError(reason)
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise ContractError(reason) from error


def require_reason_codes(value: JsonValue) -> List[str]:
    reason = "RESULT_SCHEMA_INVALID"
    if not isinstance(value, list) or len(value) > 64:
        raise ContractError(reason)
    codes: List[str] = []
    for item in value:
        code = require_string(item, reason)
        if REASON.fullmatch(code) is None:
            raise ContractError(reason)
        codes.append(code)
    if codes != sorted(set(codes), key=lambda item: item.encode("utf-8")):
        raise ContractError(reason)
    return codes


def require_identity_fields(value: Dict[str, JsonValue], reason: str) -> None:
    require_const(value["project_id"], "hwpx-public-document", reason)
    require_identifier(value["execution_id"], reason)
    require_const(value["stage"], "stage2", reason)
    require_const(value["policy_id"], "stage2-semantic-v1", reason)
    require_digest(value["policy_sha256"], reason)
    require_identifier(value["evaluator_id"], reason)
    require_digest(value["evaluator_build_sha256"], reason)
    require_digest(value["artifact_tree_sha256"], reason)
    require_digest(value["manifest_jcs_sha256"], reason)


def retry_fields() -> Tuple[Set[str], Set[str]]:
    return set(), {"retry_of_execution_id"}
