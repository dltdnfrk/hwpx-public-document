from __future__ import annotations

import hashlib
import re
from pathlib import Path


SPEC_PATH = Path(__file__).parents[1] / "docs" / "document-core-spec-v1.md"
REQUIRED_HEADINGS = (
    "## 2. Common document model",
    "## 3. Required group checklist",
    "## 4. Critical omissions and `[확인 필요]`",
    "## 5. Numeric-claim grounding",
    "## 6. Correction allowlist and input boundaries",
    "## 8. HWPX Validation Profile v1",
)


def _front_matter_and_body() -> tuple[dict[str, str], str]:
    raw = SPEC_PATH.read_text(encoding="utf-8")
    front_matter, body = raw.split("\n---\n", maxsplit=1)
    values = dict(re.findall(r"^([a-z_]+): [\"]?([^\"]+?)[\"]?$", front_matter, re.MULTILINE))
    return values, body


def test_approved_spec_has_exact_version_and_approval_tuple() -> None:
    values, _ = _front_matter_and_body()

    assert values["spec_id"] == "public-document-core"
    assert values["version"] == "1.0"
    assert values["title"] == "Document Core Spec v1"
    assert values["status"] == "approved"
    assert values["approver"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", values["approved_at"])


def test_approved_spec_hash_covers_canonical_body() -> None:
    values, body = _front_matter_and_body()

    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert values["content_hash"] == f"sha256:{digest}"


def test_spec_contains_required_contract_surfaces() -> None:
    _, body = _front_matter_and_body()

    for heading in REQUIRED_HEADINGS:
        assert heading in body
    assert "[확인 필요]" in body
    assert "evidence" in body
    assert "Raw HWPX XML" in body
    assert "institution template, current official rules" in body
