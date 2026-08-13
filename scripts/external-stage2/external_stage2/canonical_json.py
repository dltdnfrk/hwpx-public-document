from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Tuple, Union


JsonScalar = Union[None, bool, int, str]
JsonValue = Union[JsonScalar, List["JsonValue"], Dict[str, "JsonValue"]]


@dataclass(frozen=True)
class StrictJsonError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


def parse_strict(raw: bytes) -> JsonValue:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise StrictJsonError("invalid UTF-8") from error

    def reject_duplicate(pairs: List[Tuple[str, JsonValue]]) -> Dict[str, JsonValue]:
        result: Dict[str, JsonValue] = {}
        for key, value in pairs:
            if key in result:
                raise StrictJsonError("duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=reject_duplicate,
            parse_float=lambda _value: _reject_number(),
            parse_constant=lambda _value: _reject_number(),
        )
    except (json.JSONDecodeError, UnicodeError, RecursionError) as error:
        raise StrictJsonError("invalid JSON") from error
    _reject_lone_surrogates(value)
    return value


def _reject_number() -> None:
    raise StrictJsonError("non-integer JSON number")


def _reject_lone_surrogates(value: JsonValue) -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise StrictJsonError("invalid Unicode scalar")
        return
    if isinstance(value, list):
        for item in value:
            _reject_lone_surrogates(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_lone_surrogates(key)
            _reject_lone_surrogates(item)


def canonicalize(value: JsonValue) -> bytes:
    return _serialize(value).encode("utf-8")


def _serialize(value: JsonValue) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        ordered = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        fields = (
            json.dumps(key, ensure_ascii=False) + ":" + _serialize(value[key])
            for key in ordered
        )
        return "{" + ",".join(fields) + "}"
    raise StrictJsonError("unsupported JSON value")


def sha256_jcs(value: JsonValue) -> str:
    return hashlib.sha256(canonicalize(value)).hexdigest()
