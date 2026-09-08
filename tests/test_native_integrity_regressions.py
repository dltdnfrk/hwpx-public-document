from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest

from tests.test_ac05_export_failure_isolation import SWIFT_SOURCES

ROOT = Path(__file__).resolve().parents[1]
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@pytest.fixture(scope="module")
def native_integrity():
    # Retain exact RED/GREEN artifacts. No pytest temporary-directory cleanup or deletion.
    root = Path(tempfile.mkdtemp(prefix="native-integrity-", dir=os.environ.get("NATIVE_INTEGRITY_ARTIFACT_ROOT")))
    binary = root / "native-integrity"
    sources = (*SWIFT_SOURCES, "BatchExportModel.swift", "BatchExportStore.swift", "TemplateCatalog.swift",
               "TemplateCatalogModels.swift", "TemplateCatalogVerification.swift", "OfficialRuleEnforcer.swift",
               "OfficialRuleSkeleton.swift", "OfficialStyleLint.swift", "AISettingsStore.swift",
               "AISettingsModels.swift", "AIProviderCatalog.swift", "AIProviderTransport.swift", "AIBridgeCLI.swift")
    build = subprocess.run(
        ["swiftc", *(str(ROOT / "Sources/PublicDocumentApp" / name) for name in sources),
         str(ROOT / "tests/fixtures/native_integrity_regression.swift"), "-o", str(binary)],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    (root / "build.log").write_text(build.stdout + build.stderr)
    assert build.returncode == 0, build.stdout + build.stderr
    print(f"NATIVE_INTEGRITY_ARTIFACTS={root}")
    yield binary, root
    (root / "cleanup-receipt.json").write_text(json.dumps({
        "deletedPaths": [], "retainedRoot": str(root), "userDataTouched": False,
        "policy": "All fixture artifacts retained; no deletion performed.",
    }, indent=2))


@pytest.fixture
def case_root(native_integrity, request):
    root = native_integrity[1] / request.node.name.replace("/", "%2F")
    root.mkdir()
    return root


def element(text="Original", *, kind="paragraph", element_id="body", html=None, inline_ids=None):
    return {"elementID": element_id, "kind": kind, "order": 0, "text": text,
            "contentHTML": text if html is None else html, "inlineIDs": inline_ids or [],
            "styleID": "style-title" if kind == "heading" else "style-body", "evidenceIDs": []}


def project(elements=None, *, document_id="document-integrity") -> dict[str, Any]:
    elements = elements or [element()]
    return {"schemaVersion": 1, "documentID": document_id, "locale": "ko-KR", "title": "Original",
            "currentRevisionID": "revision", "elements": elements, "assets": [], "styles": [],
            "templateBinding": {"templateID": "fixture", "version": "1", "publishingAuthority": "fixture",
                                "requiredSections": [], "checklistResults": {}},
            "evidenceLinks": [], "revisions": [{"revisionID": "revision", "createdAt": "2026-09-05T00:00:00Z",
                                                 "summary": "fixture", "elementIDs": [e["elementID"] for e in elements],
                                                 "snapshotElements": copy.deepcopy(elements)}],
            "history": [], "aiProposalHistory": [], "providerConfigurations": [], "consentGrants": [],
            "redoRevisionIDs": []}


def run(native_integrity, root, mode, value):
    source = root / "input.json"
    source.write_text(json.dumps(value, ensure_ascii=False))
    before = source.read_bytes()
    result = subprocess.run([str(native_integrity[0]), mode, str(source), str(root / "out")],
                            cwd=ROOT, capture_output=True, text=True, timeout=90)
    (root / "stdout.json").write_text(result.stdout)
    (root / "stderr.log").write_text(result.stderr)
    assert source.read_bytes() == before
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("document_id", ["../escape", "../../escape", "", ".", "..", "bad\x00id", "bad\\id"])
def test_batch_rejects_path_document_ids_before_snapshot_write(native_integrity, case_root, document_id):
    out = case_root / "out"
    operation = out / ".public-document-studio-exports/operation"
    operation.mkdir(parents=True)
    sentinel = operation / "escape.json"
    sentinel.write_bytes(b"fixture-owned-existing-snapshot")
    result = run(native_integrity, case_root, "batch", project(document_id=document_id))
    assert result["rejected"], result
    assert sentinel.read_bytes() == b"fixture-owned-existing-snapshot"
    assert list((operation / "snapshots").iterdir()) == []
    assert list((operation / "staging").iterdir()) == []
    assert not (operation / "manifest.json").exists()


def test_batch_safe_unicode_identity_roundtrips_without_rewriting_project(native_integrity, case_root):
    value = project(document_id="문서-한글-42")
    result = run(native_integrity, case_root, "batch", value)
    assert result == {"rejected": False, "retryEqual": True, "stagingConfined": True}
    snapshot = case_root / "out/.public-document-studio-exports/operation/snapshots/문서-한글-42.json"
    assert json.loads(snapshot.read_text()) == value


def test_retry_rejects_manifest_document_id_traversal(native_integrity, case_root):
    out = case_root / "out"
    operation = out / ".public-document-studio-exports/operation"
    (operation / "snapshots").mkdir(parents=True)
    value = project(document_id="../escape")
    (operation / "escape.json").write_text(json.dumps(value))
    manifest = {"schemaVersion": 2, "operationID": "operation", "state": "running", "cleanupState": "pending",
                "manifestPath": str(operation / "manifest.json"), "selectedFormats": ["markdown"],
                "flatteningConsent": [], "items": [{
                    "itemID": "../escape-markdown", "documentID": "../escape", "snapshotRevisionID": "revision",
                    "snapshotHash": "sha256:fixture", "format": "markdown", "destinationFile": "safe.md",
                    "state": "queued", "progressCompleted": 1, "progressTotal": 4,
                    "diagnosticCode": "", "diagnosticMessage": ""}]}
    (operation / "manifest.json").write_text(json.dumps(manifest))
    before = (operation / "escape.json").read_bytes()
    assert run(native_integrity, case_root, "retry", value)["rejected"]
    assert (operation / "escape.json").read_bytes() == before


def table_project(row, cell):
    html = '<table><tr><th>Header</th><th>Other</th></tr><tr><td data-inline-id="target">Old</td><td><strong>Keep</strong></td></tr></table>'
    value = project([element("Header Other Old Keep", kind="table", element_id="table", html=html, inline_ids=["target"])])
    value["aiProposalHistory"] = [{"proposalID": "proposal", "baseRevisionID": "revision", "state": "proposed",
        "targetElementIDs": ["table"], "operation": "table-change", "provider": "openai", "endpointIdentity": "fixture",
        "payloadScope": "selected-elements", "commands": [{"commandID": "command", "name": "table-cell-update",
        "targetElementID": "table", "value": "New", "targetPath": f"table:table/row:{row}/cell:{cell}"}],
        "diffs": [], "approvedCommandIDs": []}]
    return value


@pytest.mark.parametrize("row,cell", [(2, 0), (1, 2), (999999, 0)])
def test_invalid_table_cell_approval_is_atomic(native_integrity, case_root, row, cell):
    value = table_project(row, cell)
    result = run(native_integrity, case_root, "ai", value)
    assert result["rejected"] and result["originalPreserved"], result
    assert json.loads((case_root / "out/project.json").read_text()) == value


def test_existing_table_cell_keeps_structure_and_undo_redo(native_integrity, case_root):
    value = table_project(1, 0)
    result = run(native_integrity, case_root, "ai", value)
    assert not result["rejected"] and result["undoEqual"] and result["redoEqual"]
    approved = json.loads((case_root / "out/project.json").read_text())
    assert approved["elements"][0]["contentHTML"] == value["elements"][0]["contentHTML"].replace(">Old<", ">New<")
    assert approved["elements"][0]["inlineIDs"] == ["target"]
    assert approved["aiProposalHistory"][0]["approvedCommandIDs"] == ["command"]


@pytest.mark.parametrize("last_cell", [1, 99])
def test_every_selected_table_command_is_applied_or_transaction_rejected(native_integrity, case_root, last_cell):
    value = table_project(1, 0)
    command = copy.deepcopy(value["aiProposalHistory"][0]["commands"][0])
    command.update(commandID="second", targetPath=f"table:table/row:1/cell:{last_cell}", value="Second")
    value["aiProposalHistory"][0]["commands"].append(command)
    result = run(native_integrity, case_root, "ai", value)
    current = json.loads((case_root / "out/project.json").read_text())
    if last_cell == 99:
        assert result["rejected"] and result["originalPreserved"], result
        assert current == value
    else:
        assert not result["rejected"] and result["undoEqual"] and result["redoEqual"]
        assert current["elements"][0]["contentHTML"] == value["elements"][0]["contentHTML"].replace(">Old<", ">New<").replace("<strong>Keep</strong>", "Second")
        assert current["aiProposalHistory"][0]["approvedCommandIDs"] == ["command", "second"]


class ParsedRichText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.inline_ids: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.parts.append("\n")
        for name, value in attrs:
            if name == "data-inline-id" and value is not None:
                self.inline_ids.append(value)


def public_title_representations(case_root: Path, governed: dict[str, Any]) -> tuple[str, str, list[str]]:
    # Exercise the shipped public layout consumer, without a browser or a mocked renderer.
    result = subprocess.run([
        "node", "--input-type=module", "-e", """
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const context = vm.createContext({ console });
for (const name of ['official-layout-profile.js', 'page-engine.js']) {
  vm.runInContext(readFileSync(`Resources/Studio/${name}`, 'utf8'), context);
}
const project = JSON.parse(readFileSync(process.argv[1], 'utf8'));
const engine = context.PublicDocumentPageEngine;
process.stdout.write(engine.previewMarkup(engine.paginateProject(project)));
""", str(case_root / "out/project.json")], cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    _ = (case_root / "public-layout.html").write_text(result.stdout)
    layout = ParsedRichText()
    layout.feed(result.stdout)
    with zipfile.ZipFile(case_root / "out/document.docx") as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
        assert "".join(n.text or "" for n in document.findall(".//w:t", NS)) == "".join(layout.parts)
    rich = ParsedRichText()
    rich.feed(governed["elements"][0]["contentHTML"])
    return "".join(layout.parts), "".join(rich.parts), rich.inline_ids


@pytest.mark.parametrize("already_required", [False, True])
@pytest.mark.parametrize("html,inline_ids,retained_ids", [
    ('<strong data-inline-id="title-inline">Original</strong>', ["title-inline"], ["title-inline"]),
    ("<span data-inline-id='outer'><em data-inline-id='inner'>Original</em></span>", ["outer", "inner"], ["outer", "inner"]),
    ('<strong data-inline-id="first">Orig</strong><em data-inline-id="second">inal</em>', ["first", "second"], []),
    ('<strong data-inline-id="title-inline" onclick="bad()">Original</strong>', ["title-inline"], []),
], ids=["strong", "nested", "multi-run", "unsafe"])
def test_official_title_rich_text_agrees_with_public_layout(native_integrity, case_root, already_required, html, inline_ids, retained_ids):
    title = element("Required & title" if already_required else "Original", kind="heading", element_id="element-title",
                    html=html, inline_ids=inline_ids)
    title["evidenceIDs"] = ["evidence-title"]
    value = project([title])
    if already_required:
        value["title"] = title["text"]
    result = run(native_integrity, case_root, "title", value)
    governed = json.loads((case_root / "out/project.json").read_text())
    layout_text, rich_text, actual_ids = public_title_representations(case_root, governed)
    assert rich_text == layout_text == governed["title"] == governed["elements"][0]["text"] == "Required & title"
    assert result == {"changed": True, "idempotent": True}
    assert actual_ids == governed["elements"][0]["inlineIDs"] == retained_ids
    if retained_ids:
        assert "<em" in governed["elements"][0]["contentHTML"] if "<em" in html else "<strong" in governed["elements"][0]["contentHTML"]
    else:
        assert governed["elements"][0]["contentHTML"] == "Required &amp; title"
    assert governed["elements"][0]["evidenceIDs"] == title["evidenceIDs"]
    assert governed["revisions"][0] == value["revisions"][0]
    assert governed["revisions"][-1]["snapshotElements"] == governed["elements"]


def test_consistent_official_rich_title_does_not_create_revision(native_integrity, case_root):
    title = element("Required & title", kind="heading", element_id="element-title",
                    html='<strong data-inline-id="title-inline">Required &amp; title</strong>', inline_ids=["title-inline"])
    value = project([title])
    value["title"] = title["text"]
    result = run(native_integrity, case_root, "title", value)
    governed = json.loads((case_root / "out/project.json").read_text())
    assert result == {"changed": False, "idempotent": True}
    assert governed == value
    assert public_title_representations(case_root, governed) == (title["text"], title["text"], title["inlineIDs"])


@pytest.mark.parametrize("text", ["&\u0301", "<\u0301", ">\u0301", '"\u0301', "'\u0301", "A &\u0301 <\u0301 Z"])
def test_docx_xml_escapes_metacharacters_inside_graphemes(native_integrity, case_root, text):
    run(native_integrity, case_root, "docx", project([element(text)]))
    with zipfile.ZipFile(case_root / "out/document.docx") as archive:
        for name in archive.namelist():
            if name.endswith((".xml", ".rels")):
                ET.fromstring(archive.read(name))
        document = ET.fromstring(archive.read("word/document.xml"))
        assert "".join(n.text or "" for n in document.findall(".//w:t", NS)) == text
        raw = archive.read("word/document.xml").decode()
        if "&" in text:
            assert "&amp;\u0301" in raw
        if "<" in text:
            assert "&lt;\u0301" in raw


@pytest.mark.parametrize("kind", ["paragraph", "heading", "formula"])
@pytest.mark.parametrize("separator", ["\r\n", "\r"])
def test_docx_crlf_and_lone_cr_are_xml_normalized_without_text_loss(native_integrity, case_root, kind, separator):
    text = f"alpha  beta{separator}gamma\tdelta"
    value = project([element(text, kind=kind)])
    run(native_integrity, case_root, "docx", value)
    with zipfile.ZipFile(case_root / "out/document.docx") as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
        nodes = [n for n in document.iter() if n.tag.endswith("}t")]
        assert "".join(n.text or "" for n in nodes) == "alpha  beta\ngamma\tdelta"


@pytest.mark.parametrize("existing", [("document.typ",), ("document.pdf",), ("document.typ", "document.pdf")])
def test_sidecar_collision_is_explicit_and_never_claims_previous_output(native_integrity, case_root, existing):
    out = case_root / "out"
    out.mkdir()
    for name in existing:
        (out / name).write_bytes(b"previous-project-owned-" + name.encode())
    before = {name: (out / name).read_bytes() for name in existing}
    receipt = run(native_integrity, case_root, "export", project())
    assert receipt["publishedFormats"] == ["markdown"]
    assert {name: (out / name).read_bytes() for name in existing} == before
    assert receipt.get("sidecar", {}).get("state") == "skipped", receipt
    assert receipt["sidecar"]["diagnosticCode"] == "destination-exists"
    assert not receipt["sidecar"].get("sourceFile")
    assert not receipt["sidecar"].get("pdfFile")
    assert sorted(p.name for p in out.iterdir()) == sorted([*existing, "ac05-fixture.md"])


def test_new_sidecar_receipt_only_names_outputs_from_current_export(native_integrity, case_root):
    receipt = run(native_integrity, case_root, "export", project())
    sidecar = receipt.get("sidecar", {})
    assert sidecar.get("sourceFile") == "document.typ", receipt
    assert (case_root / "out/document.typ").is_file()
    if any(Path(p).is_file() for p in ("/opt/homebrew/bin/typst", "/usr/local/bin/typst", "/usr/bin/typst")):
        assert sidecar["state"] == "published", sidecar
        assert sidecar["pdfFile"] == "document.pdf"
        assert (case_root / "out/document.pdf").read_bytes().startswith(b"%PDF-")
    else:
        assert sidecar["state"] == "source-only"
        assert sidecar["diagnosticCode"] == "missing-typst-engine"
        assert not sidecar.get("pdfFile")


def test_typst_uses_canonical_mac_fonts_without_changing_word_alias(native_integrity, case_root):
    text = "한글 공문서 본문 보존 확인"
    value = project([element(text)])
    word_root = case_root / "word"
    word_root.mkdir()
    run(native_integrity, word_root, "docx", value)
    with zipfile.ZipFile(word_root / "out/document.docx") as archive:
        styles = ET.fromstring(archive.read("word/styles.xml"))
        fonts = styles.find("w:docDefaults/w:rPrDefault/w:rPr/w:rFonts", NS)
        assert fonts is not None
        assert {fonts.get(f"{{{NS['w']}}}{name}") for name in ("ascii", "eastAsia", "hAnsi")} == {"Apple Myungjo"}
        document = ET.fromstring(archive.read("word/document.xml"))
        assert "".join(n.text or "" for n in document.findall(".//w:t", NS)) == text

    receipt = run(native_integrity, case_root, "export", value)
    assert receipt["publishedFormats"] == ["markdown"]
    source = (case_root / "out/document.typ").read_text()
    assert text in source
    assert "unknown font family" not in (case_root / "stderr.log").read_text().lower()
    toolkit = json.loads((ROOT / "Resources/Templates/official-style-toolkit-1.0.0.json").read_text())
    presets = {p["styleID"]: p for p in toolkit["presets"].values()}
    expected_fonts = ", ".join(json.dumps(presets[s]["macFont"]) for s in ("style-body", "style-title"))
    assert f"font: ({expected_fonts})" in source
    if receipt["sidecar"]["state"] == "published":
        assert (case_root / "out/document.pdf").read_bytes().startswith(b"%PDF-")


def test_semantic_loss_still_blocks_export_without_touching_sidecars(native_integrity, case_root):
    out = case_root / "out"
    out.mkdir()
    for name in ("document.typ", "document.pdf"):
        (out / name).write_bytes(b"previous-project-owned")
    value = project([element(kind="list-item", html="<ul><li>Original</li></ul>")])
    receipt = run(native_integrity, case_root, "export", value)
    assert receipt["publishedFormats"] == []
    assert receipt["blockedFormats"] == ["markdown"]
    assert not receipt.get("sidecar")
    assert sorted(p.name for p in out.iterdir()) == ["document.pdf", "document.typ"]
    assert all(p.read_bytes() == b"previous-project-owned" for p in out.iterdir())


@pytest.mark.parametrize("mode,has_secret", [("settings-present", True), ("settings-missing", False)])
def test_settings_status_checks_existence_without_decrypting(native_integrity, case_root, mode, has_secret):
    response = run(native_integrity, case_root, mode, project())
    audit = json.loads((case_root / "out/query-audit.json").read_text())
    assert audit == {"dataQueries": 0, "metadataQueries": 1, "noninteractive": True,
                     "identityMatched": True, "settingsPreserved": True, "metadataOnly": True}
    assert response["events"][0]["event"] == "aiSettingsLoaded"
    settings = response["events"][0]["payload"]["settings"]
    assert settings["activeProvider"] == "openai"
    assert settings["providers"] == [{"provider": "openai", "endpointIdentity": "https://api.openai.com/v1",
        "model": "fixture-model", "hasSecret": has_secret, "hostDisclosure": "api.openai.com"}]
    assert "fixture-secret-sentinel" not in json.dumps(response)
    assert "keychainAccountReference" not in json.dumps(response)


def test_settings_permission_error_is_not_reported_as_missing_secret(native_integrity, case_root):
    response = run(native_integrity, case_root, "settings-denied", project())
    audit = json.loads((case_root / "out/query-audit.json").read_text())
    assert audit["dataQueries"] == 0 and audit["metadataQueries"] == 1
    assert audit["settingsPreserved"] and audit["noninteractive"] and audit["identityMatched"] and audit["metadataOnly"]
    assert [event["event"] for event in response["events"]] == ["error"]
    assert "hasSecret" not in json.dumps(response)


def test_explicit_credential_request_still_retrieves_password_data(native_integrity, case_root):
    response = run(native_integrity, case_root, "settings-credential", project())
    audit = json.loads((case_root / "out/query-audit.json").read_text())
    assert response == {"credentialRetrieved": True}
    assert audit == {"dataQueries": 1, "metadataQueries": 0, "noninteractive": True,
                     "identityMatched": True, "settingsPreserved": True, "metadataOnly": True}
    assert "fixture-secret-sentinel" not in json.dumps(response)


def test_existing_main_export_remains_untouched(native_integrity, case_root):
    out = case_root / "out"
    out.mkdir()
    (out / "ac05-fixture.md").write_bytes(b"previous-project-owned")
    receipt = run(native_integrity, case_root, "export", project())
    assert receipt["publishedFormats"] == []
    assert receipt["failedFormats"] == ["markdown"]
    assert receipt["failures"][0]["errorCode"] == "destination-exists"
    assert not receipt.get("sidecar")
    assert (out / "ac05-fixture.md").read_bytes() == b"previous-project-owned"
    assert sorted(p.name for p in out.iterdir()) == ["ac05-fixture.md"]
