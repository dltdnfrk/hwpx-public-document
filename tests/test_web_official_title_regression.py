from __future__ import annotations

import json
from copy import deepcopy
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pytest

from public_document_web.http import serve
from public_document_web.official_rules import enforce_official_rules


class ParsedTitle(HTMLParser):
    """Accumulate decoded text and tags independently of the governance code."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.tags: list[str] = []
        self.feed(html)
        self.close()

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)

    @property
    def text(self) -> str:
        return "".join(self.parts)


# These fixtures use the existing JSON project/bridge contract, not a second model.
def _project(title: str) -> dict[str, Any]:
    elements = [{
        "elementID": "element-title",
        "kind": "heading",
        "order": 0,
        "text": title,
        "contentHTML": f'<strong data-inline-id="title-run">{escape(title)}</strong>',
        "inlineIDs": ["title-run"],
        "styleID": "style-title",
        "evidenceIDs": ["title-evidence"],
    }, {
        "elementID": "body",
        "kind": "paragraph",
        "order": 1,
        "text": "Body",
        "contentHTML": '<em data-inline-id="body-run">Body</em>',
        "inlineIDs": ["body-run"],
        "styleID": "style-body",
        "evidenceIDs": [],
    }]
    return {
        "schemaVersion": 1,
        "documentID": "document-title-regression",
        "title": title,
        "currentRevisionID": "revision-draft",
        "elements": elements,
        "assets": [],
        "styles": [],
        "templateBinding": {"templateID": "public-plan"},
        "evidenceLinks": [],
        "revisions": [{
            "revisionID": "revision-draft",
            "snapshotElements": elements,
        }],
        "history": [],
    }


def _catalog(title: str) -> dict[str, Any]:
    return {"entries": [{"templateID": "public-plan", "officialRules": [{
        "field": "title",
        "requiredValue": title,
        "precedence": 100,
        "source": "title-regression",
    }]}]}


@pytest.mark.parametrize("required", ["New", 'R&D <plan> > draft "quoted" &amp;'])
@pytest.mark.parametrize("plain_matches", [False, True], ids=["changed-text", "stale-html"])
def test_changed_official_title_has_matching_rendered_text_without_stale_ids(
    required: str, plain_matches: bool,
) -> None:
    # Given a rich draft whose revision shares the original element objects.
    project = _project("Old")
    if plain_matches:
        project["title"] = required
        project["elements"][0]["text"] = required
    before = deepcopy(project)

    # When real governance replaces the authoritative title.
    governed, official = enforce_official_rules(project, _catalog(required))

    # Then both representations agree, with literal safe HTML and no obsolete IDs.
    title = governed["elements"][0]
    parsed = ParsedTitle(title["contentHTML"])
    assert parsed.text == required
    assert title["text"] == governed["title"] == required
    assert parsed.tags == []
    assert title["inlineIDs"] == []
    assert title["elementID"] == "element-title"
    assert title["evidenceIDs"] == ["title-evidence"]
    assert official["contentChanged"] is True
    assert project == before
    assert governed["revisions"][0] == before["revisions"][0]
    assert governed["elements"][1] == before["elements"][1]
    assert governed["revisions"][-1]["snapshotElements"] == governed["elements"]


@pytest.mark.parametrize("metadata_title", ["New & <literal>", "Old metadata"])
def test_unchanged_title_preserves_exact_rich_markup_and_inline_ids(metadata_title: str) -> None:
    # Given an already-correct rich element, even if project metadata disagrees.
    required = "New & <literal>"
    project = _project(required)
    project["title"] = metadata_title
    before = deepcopy(project)

    # When governance checks the title.
    governed, official = enforce_official_rules(project, _catalog(required))

    # Then rich source and identity are untouched, and repeat enforcement is a no-op.
    assert governed["elements"] == before["elements"]
    assert ParsedTitle(governed["elements"][0]["contentHTML"]).text == required
    assert governed["title"] == required
    assert official["contentChanged"] is (metadata_title != required)
    assert project == before
    repeated, repeated_official = enforce_official_rules(governed, _catalog(required))
    assert repeated == governed
    assert repeated_official["contentChanged"] is False


def _post(url: str, payload: dict[str, Any], session: str = "") -> dict[str, Any]:
    origin = url.split("/api/", 1)[0]
    headers = {"Content-Type": "application/json", "Origin": origin}
    if session:
        headers["Cookie"] = f"PublicDocumentSession={session}"
        headers["X-Public-Document-Session"] = session
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urlopen(request, timeout=5) as response:
        assert response.status == 200
        return json.loads(response.read())


@pytest.mark.parametrize("scenario", [
    (None, False), (None, True),
    ('R&D <plan> > draft "quoted" &amp;', False),
    ('R&D <plan> > draft "quoted" &amp;', True),
], ids=["signed-changed", "signed-stale-html", "literal-changed", "literal-stale-html"])
def test_http_save_and_reopen_render_the_actual_governed_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: tuple[str | None, bool],
) -> None:
    # Given a real isolated HTTP server and the verified bundled catalog.
    literal_title, plain_matches = scenario
    server = serve("127.0.0.1", 0, tmp_path / "data", open_browser=False)
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    project = _project("Old")
    try:
        catalog = server.state.catalog_status()
        rules = [rule for entry in catalog["entries"] if entry["templateID"] == "public-plan"
                 for rule in entry["officialRules"] if rule["field"] == "title"]
        rule = max(rules, key=lambda entry: entry["precedence"])
        if literal_title is not None:
            # Vary only catalog input; HTTP routing, enforcement and persistence stay real.
            rule["requiredValue"] = literal_title
            monkeypatch.setattr(server.state, "catalog_status", lambda: catalog)
        required = rule["requiredValue"]
        if plain_matches:
            project["title"] = required
            project["elements"][0]["text"] = required
        before = deepcopy(project)
        bootstrap = _post(f"{origin}/api/bootstrap", {"token": server.bootstrap_token})
        session = bootstrap["sessionToken"]

        # When the client saves the draft and reopens it through the real bridge.
        saved = _post(f"{origin}/api/bridge", {"action": "save", "project": project}, session)
        reopened = _post(f"{origin}/api/bridge", {"action": "reopen"}, session)

        # Then response and persisted/reopened rich text agree with the rule, not Old.
        assert saved["events"][0]["event"] == "saved"
        assert reopened["events"][0]["event"] == "opened"
        payload = saved["events"][0]["payload"]
        governed = payload["project"]
        assert payload["officialRuleState"]["contentChanged"] is True
        assert reopened["events"][0]["payload"]["project"] == governed
        for result in (governed, reopened["events"][0]["payload"]["project"]):
            title = result["elements"][0]
            parsed = ParsedTitle(title["contentHTML"])
            assert parsed.text == required
            assert result["title"] == title["text"] == required
            assert parsed.tags == []
            assert title["inlineIDs"] == []
            assert result["revisions"][0] == before["revisions"][0]
        assert project == before
    finally:
        server.shutdown()
        server.server_close()
