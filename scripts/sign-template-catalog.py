#!/usr/bin/env python3
"""Sign Resources/Templates/catalog-envelope.json with the studio root key.

The private key lives at scripts/keys/studio-template-root-2026.ed25519 and is
not shipped inside the app bundle. The matching public key is embedded in
TemplateCatalog.swift.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

ROOT = Path(__file__).resolve().parents[1]
KEY_PATH = ROOT / "scripts" / "keys" / "studio-template-root-2026.ed25519"
ENVELOPE_PATH = ROOT / "Resources" / "Templates" / "catalog-envelope.json"
ENTRIES_PATH = ROOT / "Resources" / "Templates" / "catalog-entries.json"


def load_or_create_key() -> Ed25519PrivateKey:
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if KEY_PATH.exists():
        return Ed25519PrivateKey.from_private_bytes(KEY_PATH.read_bytes())
    key = Ed25519PrivateKey.generate()
    KEY_PATH.write_bytes(
        key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    )
    KEY_PATH.chmod(0o600)
    return key


def public_key_bytes(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def swift_public_key_literal(raw: bytes) -> str:
    groups = [raw[index : index + 8] for index in range(0, len(raw), 8)]
    lines = []
    for group in groups:
        hexes = ", ".join(f"0x{byte:02x}" for byte in group)
        lines.append(f"        {hexes},")
    return "    static let productionPublicKey = Data([\n" + "\n".join(lines) + "\n    ])"


def content_hash(entry: dict) -> str:
    material = {key: value for key, value in entry.items() if key != "contentHash"}
    encoded = json.dumps(material, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_payload() -> dict:
    source = json.loads(ENTRIES_PATH.read_text(encoding="utf-8"))
    entries = []
    for entry in source["entries"]:
        filled = dict(entry)
        filled["contentHash"] = content_hash(filled)
        entries.append(filled)
    return {
        "catalogID": source["catalogID"],
        "version": source["version"],
        "publishedAt": source["publishedAt"],
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-public-key", action="store_true")
    args = parser.parse_args()
    key = load_or_create_key()
    if args.print_public_key:
        print(public_key_bytes(key).hex())
        print(swift_public_key_literal(public_key_bytes(key)))
        return
    payload = build_payload()
    payload_bytes = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    signature = key.sign(payload_bytes)
    envelope = {
        "keyID": "studio-template-root-2026",
        "payload": base64.b64encode(payload_bytes).decode("ascii"),
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    ENVELOPE_PATH.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {ENVELOPE_PATH.relative_to(ROOT)}")
    print(f"entries {len(payload['entries'])}")
    print(f"public {public_key_bytes(key).hex()}")


if __name__ == "__main__":
    main()
