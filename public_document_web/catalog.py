from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from .paths import PUBLIC_KEY_HEX


def verify_ed25519(signature: bytes, payload: bytes) -> None:
    field = 2**255 - 19
    order = 2**252 + 27742317777372353535851937790883648493
    curve_d = (-121665 * pow(121666, field - 2, field)) % field
    sqrt_minus_one = pow(2, (field - 1) // 4, field)

    def recover_x(y: int) -> int:
        xx = (y * y - 1) * pow(curve_d * y * y + 1, field - 2, field) % field
        x = pow(xx, (field + 3) // 8, field)
        if (x * x - xx) % field != 0:
            x = x * sqrt_minus_one % field
        if (x * x - xx) % field != 0:
            raise ValueError("invalid catalog envelope")
        return x

    def decode_point(encoded: bytes) -> tuple[int, int]:
        if len(encoded) != 32:
            raise ValueError("invalid catalog envelope")
        raw = int.from_bytes(encoded, "little")
        y = raw & ((1 << 255) - 1)
        if y >= field:
            raise ValueError("invalid catalog envelope")
        x = recover_x(y)
        if (x & 1) != (raw >> 255):
            x = field - x
        if (-x * x + y * y - 1 - curve_d * x * x * y * y) % field != 0:
            raise ValueError("invalid catalog envelope")
        return x, y

    def add(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
        x1, y1 = left
        x2, y2 = right
        product = curve_d * x1 * x2 * y1 * y2 % field
        return (
            (x1 * y2 + x2 * y1) * pow(1 + product, field - 2, field) % field,
            (y1 * y2 + x1 * x2) * pow(1 - product, field - 2, field) % field,
        )

    def multiply(point: tuple[int, int], scalar: int) -> tuple[int, int]:
        result = (0, 1)
        addend = point
        while scalar:
            if scalar & 1:
                result = add(result, addend)
            addend = add(addend, addend)
            scalar >>= 1
        return result

    if len(signature) != 64:
        raise ValueError("invalid catalog envelope")
    public_bytes = bytes.fromhex(PUBLIC_KEY_HEX)
    public_point = decode_point(public_bytes)
    encoded_r = signature[:32]
    point_r = decode_point(encoded_r)
    scalar_s = int.from_bytes(signature[32:], "little")
    if scalar_s >= order or public_point == (0, 1):
        raise ValueError("invalid catalog envelope")
    base_y = 4 * pow(5, field - 2, field) % field
    base_x = recover_x(base_y)
    if base_x & 1:
        base_x = field - base_x
    challenge = int.from_bytes(
        hashlib.sha512(encoded_r + public_bytes + payload).digest(),
        "little",
    ) % order
    if multiply((base_x, base_y), scalar_s) != add(
        point_r,
        multiply(public_point, challenge),
    ):
        raise ValueError("invalid catalog envelope")


def verify_catalog_envelope(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > 262_144:
        raise ValueError("invalid catalog envelope")
    envelope = json.loads(raw.decode("utf-8"))
    if set(envelope) != {"keyID", "payload", "signature"}:
        raise ValueError("invalid catalog envelope")
    if envelope["keyID"] != "studio-template-root-2026":
        raise ValueError("invalid catalog envelope")
    payload = base64.b64decode(envelope["payload"], validate=True)
    signature = base64.b64decode(envelope["signature"], validate=True)
    if not payload or len(payload) > 131_072:
        raise ValueError("invalid catalog envelope")
    if base64.b64encode(payload).decode("ascii") != envelope["payload"]:
        raise ValueError("invalid catalog envelope")
    verify_ed25519(signature, payload)
    catalog = json.loads(payload.decode("utf-8"))
    canonical = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if canonical != payload:
        raise ValueError("invalid catalog envelope")
    types = {entry["documentType"] for entry in catalog["entries"]}
    if types != {"추진계획서", "기안문", "보고서", "결과보고서", "업무협조", "회의록"}:
        raise ValueError("invalid catalog envelope")
    return catalog
