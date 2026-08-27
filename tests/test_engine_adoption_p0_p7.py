from __future__ import annotations

import json
from pathlib import Path

from public_document_web.official_rules import enforce_official_rules
from public_document_web.official_style_lint import apply_lint, dry_run_lint
from public_document_web.statute_citations import review_citations, verified_citations
from public_document_web.typst_sidecar import typst_source


ROOT = Path(__file__).resolve().parents[1]


def _catalog() -> dict:
    return json.loads((ROOT / "Resources/Templates/catalog-entries.json").read_text(encoding="utf-8"))


def _project(template_id: str, title: str, elements: list, assets: list | None = None) -> dict:
    return {
        "schemaVersion": 1,
        "documentID": "document-engine-adoption",
        "locale": "ko-KR",
        "title": title,
        "currentRevisionID": "revision-1",
        "elements": elements,
        "assets": assets or [],
        "styles": [],
        "templateBinding": {
            "templateID": template_id,
            "version": "1.0",
            "publishingAuthority": "기관 표준",
            "requiredSections": ["본문"],
            "checklistResults": {},
        },
        "evidenceLinks": [],
        "revisions": [],
        "history": [],
        "aiProposalHistory": [],
    }


def _title_element(text: str) -> dict:
    return {
        "elementID": "element-title",
        "kind": "heading",
        "order": 0,
        "text": text,
        "styleID": "style-title",
        "evidenceIDs": [],
    }


def test_p0_catalog_and_studio_do_not_advertise_hwpx_mandate() -> None:
    catalog = _catalog()
    blob = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "Resources/Templates/catalog-entries.json",
            *sorted((ROOT / "Resources/Studio").glob("*.js")),
            ROOT / "Resources/Studio/index.html",
        ]
    )
    assert "HWPX 의무화" not in blob
    assert "10월 고시" not in blob
    assert "공공문서 작성 지침 제4조" not in blob
    plan = next(entry for entry in catalog["entries"] if entry["templateID"] == "public-plan")
    assert plan["officialRules"][0]["source"] == "기관 표준"


def test_p1_public_draft_skeleton_and_public_plan_title_overwrite() -> None:
    catalog = _catalog()
    plan, plan_state = enforce_official_rules(
        _project("public-plan", "웹앱 제목", [_title_element("웹앱 제목")]),
        catalog,
    )
    assert plan["title"] == "기관 공식 제목을 사용하세요"
    assert plan_state["contentChanged"] is True
    assert plan["history"][-1]["kind"] == "official-rule-enforced:title"

    draft, draft_state = enforce_official_rules(
        _project("public-draft", "기안 제목", [_title_element("기안 제목")]),
        catalog,
    )
    texts = [element["text"] for element in draft["elements"]]
    assert "끝" in texts
    assert "발신명의" in texts
    assert "붙임" not in texts
    assert draft["title"] == "기안 제목"
    assert draft_state["contentChanged"] is True
    again, again_state = enforce_official_rules(draft, catalog)
    assert again_state["contentChanged"] is False
    assert again["elements"] == draft["elements"]

    attached, attached_state = enforce_official_rules(
        _project(
            "public-draft",
            "기안 제목",
            [_title_element("기안 제목")],
            assets=[{"assetID": "a1", "contentHash": "sha256:x", "mediaType": "text/plain", "relativePath": "a.txt"}],
        ),
        catalog,
    )
    assert "붙임" in [element["text"] for element in attached["elements"]]
    assert attached_state["contentChanged"] is True


def test_p2_numbering_profiles_stay_separate() -> None:
    toolkit = json.loads((ROOT / "Resources/Templates/official-style-toolkit-1.0.0.json").read_text(encoding="utf-8"))
    assert toolkit["statutoryList"] == ["1. ", "가. ", "1) ", "가) ", "(1) ", "(가) ", "① ", "㉮ "]
    assert toolkit["guidebookList"] == ["□ ", "○", "-", "※", "*"]
    assert toolkit["listMarkers"] == toolkit["guidebookList"]
    studio = "\n".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "Resources/Studio").glob("*.js")))
    assert 'templateID === \'public-draft\' ? `${index + 1}. ${section}` : `□ ${section}`' in studio
    assert 'templateID === \'public-draft\' ? `가. ${section}` : `○ ${section}`' in studio


def test_p4_lint_is_dry_run_and_does_not_revert_title() -> None:
    catalog = _catalog()
    project = _project("public-plan", "기관 공식 제목을 사용하세요", [_title_element("기관 공식 제목을 사용하세요")])
    report = dry_run_lint(project, catalog)
    assert report["dryRun"] is True
    assert all(item["ruleID"] != "lint-title-lock" for item in report["findings"])
    reverted = dict(project)
    reverted["title"] = "되돌린 제목"
    locked, result = apply_lint(reverted, catalog)
    assert locked["title"] == "되돌린 제목"
    assert result["applied"] is False
    assert any(item["ruleID"] == "lint-title-lock" for item in result["findings"])
    draft = _project("public-draft", "기안", [_title_element("기안")])
    findings = {item["ruleID"] for item in dry_run_lint(draft, catalog)["findings"]}
    assert "lint-end-mark" in findings
    assert "lint-sender-name" in findings


def test_p5_unverified_statute_is_not_confirmed() -> None:
    verified = verified_citations()
    assert "행정업무의 운영 및 혁신에 관한 규정 제13조" in verified
    confirmed = review_citations("발신명의는 행정업무의 운영 및 혁신에 관한 규정 제13조를 따른다.")
    assert confirmed[0]["verified"] is True
    assert confirmed[0]["label"] == "확인됨"
    folklore = review_citations("공공문서 작성 지침 제4조와 편람 제7조")
    assert {item["label"] for item in folklore} == {"법령 인용 미확인"}
    studio = (ROOT / "Resources/Studio/statute-citations.js").read_text(encoding="utf-8")
    assert "확인됨" in studio
    assert "법령 인용 미확인" in studio


def test_p6_checklist_is_optional_and_not_mois_standard() -> None:
    html = (ROOT / "Resources/Studio/index.html").read_text(encoding="utf-8")
    js = (ROOT / "Resources/Studio/checklist-consent.js").read_text(encoding="utf-8")
    assert "행정안전부 표준이 아닙니다" in html
    assert "data-checklist-consent" in html
    assert "checklistConsent" in js


def test_p7_typst_sidecar_is_not_hwpx_replacement() -> None:
    tokens = json.loads((ROOT / "Resources/Print/print-tokens-1.0.0.json").read_text(encoding="utf-8"))
    assert "HWPX" in tokens["note"]
    source = typst_source(_project("public-plan", "미리보기 제목", [_title_element("미리보기 제목")]))
    assert "미리보기 제목" in source
    assert "a4" in source
    assert "HWPX 대체" in source
