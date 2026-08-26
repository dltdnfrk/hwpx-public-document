from __future__ import annotations

import base64
import json
from typing import Any

from .paths import PUBLIC_KEY_HEX


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
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX)).verify(signature, payload)
    catalog = json.loads(payload.decode("utf-8"))
    canonical = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if canonical != payload:
        raise ValueError("invalid catalog envelope")
    types = {entry["documentType"] for entry in catalog["entries"]}
    if types != {"추진계획서", "기안문", "보고서", "결과보고서", "업무협조", "회의록"}:
        raise ValueError("invalid catalog envelope")
    return catalog
