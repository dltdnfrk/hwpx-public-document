from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import RESOURCES

PRINT_TOKENS = RESOURCES / "Print" / "print-tokens-1.0.0.json"


def load_print_tokens(path=None):
    return json.loads((path or PRINT_TOKENS).read_text(encoding="utf-8"))


def escape_typst(value: str) -> str:
    escaped = []
    for character in value or "":
        if character in "\\#_[]":
            escaped.append("\\" + character)
        else:
            escaped.append(character)
    return "".join(escaped)


def typst_source(project: dict[str, Any], tokens=None) -> str:
    tokens = tokens or load_print_tokens()
    margin = tokens["page"]["marginMm"]
    fonts = tokens["fonts"]
    sizes = tokens["sizesPt"]
    lines = [
        "#set page(paper: \"{0}\", margin: (top: {1}mm, right: {2}mm, bottom: {3}mm, left: {4}mm))".format(
            tokens["page"]["paper"],
            margin["top"],
            margin["right"],
            margin["bottom"],
            margin["left"],
        ),
        "#set text(font: (\"{0}\", \"{1}\"), size: {2}pt, lang: \"ko\")".format(
            fonts["body"],
            fonts["title"],
            sizes["body"],
        ),
        "#align(center, text({0}pt, weight: \"bold\")[{1}])".format(
            sizes["title"],
            escape_typst(str(project.get("title") or "")),
        ),
        "#v(1em)",
    ]
    elements = sorted(project.get("elements") or [], key=lambda item: int(item.get("order") or 0))
    for element in elements:
        text = escape_typst(str(element.get("text") or ""))
        if not text:
            continue
        if element.get("kind") == "heading" or element.get("styleID") == "style-section-heading":
            lines.append("#text({0}pt, weight: \"bold\")[{1}]".format(sizes["heading"], text))
        else:
            lines.append(text)
        lines.append("#v(0.6em)")
    lines.append("// HWPX 대체가 아닌 미리보기 사이드카")
    return "\n".join(lines) + "\n"
