from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .paths import RESOURCES

CITATION_PATH = RESOURCES / "Rules" / "verified-statute-citations-1.0.0.json"
STATUTE_PATTERN = re.compile(
    r"(행정업무의 운영 및 혁신에 관한 규정(?: 시행규칙)? 제\d+조[①②③④⑤⑥⑦⑧⑨⑩]?"
    r"|공공문서 작성 지침 제\d+조"
    r"|편람 제\d+조"
    r"|제\d+조[①②③④⑤⑥⑦⑧⑨⑩]?)"
)


def verified_citations(path=None):
    payload = json.loads((path or CITATION_PATH).read_text(encoding="utf-8"))
    return [str(item) for item in payload.get("verified") or []]


def extract_citations(text: str) -> list[str]:
    found = []
    for match in STATUTE_PATTERN.finditer(text or ""):
        value = match.group(0)
        if value not in found:
            found.append(value)
    return found


def review_citations(text: str, path=None) -> list[dict[str, Any]]:
    verified = set(verified_citations(path))
    reviews = []
    for citation in extract_citations(text):
        confirmed = citation in verified
        reviews.append({
            "citation": citation,
            "verified": confirmed,
            "label": "확인됨" if confirmed else "법령 인용 미확인",
        })
    return reviews


def review_project_or_commands(values) -> list[dict[str, Any]]:
    seen = {}
    for value in values:
        for item in review_citations(str(value or "")):
            seen[item["citation"]] = item
    return list(seen.values())
