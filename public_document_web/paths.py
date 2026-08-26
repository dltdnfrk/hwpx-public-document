from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "Resources"
ENVELOPE = RESOURCES / "Templates" / "catalog-envelope.json"
PUBLIC_KEY_HEX = "a3ca24b7a40d1be062659a9895287e7732e1cf8bbe7de0e3d23783076c67f2ce"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
