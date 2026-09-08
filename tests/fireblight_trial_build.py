#!/usr/bin/env python3
"""Build the Aside content-trial script with the user-supplied 정책 제언."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("/tmp/public-document-studio-fireblight-trial")
TITLE = "과수화상병 예방체계 고도화를 위한 과원 위생관리 정책 제언"


def el(element_id, kind, text, style_id, **extra):
    item = {
        "elementID": element_id,
        "kind": kind,
        "text": text,
        "contentHTML": extra.pop("contentHTML", text),
        "styleID": style_id,
        "evidenceIDs": [],
    }
    item.update(extra)
    return item


def heading(element_id, text):
    return el(element_id, "heading", text, "style-section-heading")


def body(element_id, text):
    return el(element_id, "paragraph", text, "style-body")


def table_html():
    rows = [
        ("평가영역", "주요 지표"),
        ("교육", "교육 이수율, 이해도, 실제 절차 재현율"),
        ("위생행동", "작업 전후 적정 세척·소독 완료율"),
        ("작업기록", "기록 완결률, 오류율, 역학정보 확인 소요시간"),
        ("재조치", "이상 확인 후 적정 재조치율과 소요시간"),
        ("독립지표", "표면 오염률, 기준초과율 또는 오염농도 변화"),
        ("사용성", "작업시간, 기록시간, 장비 휴대·사용 편의성"),
        ("안전성", "오경보, 미조치, 불필요한 폐기·격리 사례"),
        ("비용", "농가·작업팀·행정기관의 추가비용과 편익"),
        ("수용성", "농가·작업자·지도기관의 참여·유지 의향"),
        ("지속성", "3개월·6개월 후 절차 준수율과 실제 사용률"),
        ("장기효과", "화상병 발생 및 역학적 연관성에 대한 탐색평가"),
    ]
    body_html = "".join("<tr><td>{0}</td><td>{1}</td></tr>".format(a, b) for a, b in rows)
    return '<table data-easy-table="true"><tbody>{0}</tbody></table>'.format(body_html)


def elements():
    items = [
        el("element-title", "heading", TITLE, "style-title"),
        heading("element-section-1-heading", "1. 수신·제목"),
        body(
            "element-section-1-body",
            "가. 수신 농림축산식품부장관(경유 농림축산검역본부장, 농촌진흥청장). "
            "제목 「과수화상병 예방체계 고도화를 위한 과원 위생관리 정책 제언」.",
        ),
        heading("element-section-2-heading", "2. 본문"),
        body(
            "element-section-2-body",
            "과수화상병 방역의 실효성을 높이기 위해 예찰·신고·진단 및 발생 후 방제와 함께, "
            "농작업 전후 작업도구·복장·신발의 위생관리, 이동 작업팀 교육 및 작업이력 관리를 "
            "하나의 예방체계로 연계할 것을 제언함.",
        ),
    ]
    blocks = load_policy_blocks()
    items.extend(blocks)
    items.extend(
        [
            heading("element-section-3-heading", "3. 끝·붙임"),
            body("element-section-3-body", "가. 붙임 1. 성과지표 및 판단기준 표. 끝."),
            heading("element-section-4-heading", "4. 발신명의"),
            body(
                "element-section-4-body",
                "가. 발신명의. 원문에 발신 기관이 명시되지 않아 기안문 골격의 발신명의 절만 유지함.",
            ),
        ]
    )
    return items


def load_policy_blocks():
    source = Path(__file__).with_name("fireblight_policy_blocks.json")
    data = json.loads(source.read_text(encoding="utf-8"))
    out = []
    for item in data:
        kind = item["kind"]
        if kind == "heading":
            out.append(heading(item["id"], item["text"]))
        elif kind == "table":
            out.append(
                el(
                    item["id"],
                    "table",
                    item["text"],
                    "style-table",
                    contentHTML=table_html(),
                    rows=12,
                )
            )
        else:
            out.append(body(item["id"], item["text"]))
    return out


def render_script(studio_url):
    template = Path(__file__).with_name("fireblight_content_trial.tpl.js").read_text(encoding="utf-8")
    return (
        template.replace("__STUDIO_URL__", json.dumps(studio_url))
        .replace("__EVIDENCE_DIR__", json.dumps(str(ROOT)))
        .replace("__INJECTED_ELEMENTS__", json.dumps(elements(), ensure_ascii=False))
        .replace("__EXPECTED_TITLE__", json.dumps(TITLE, ensure_ascii=False))
    )


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    payload = {"title": TITLE, "elements": elements()}
    (ROOT / "elements.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("elements={0} chars={1}".format(len(payload["elements"]), sum(len(item["text"]) for item in payload["elements"])))


if __name__ == "__main__":
    main()

