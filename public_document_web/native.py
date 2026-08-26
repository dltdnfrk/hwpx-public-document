from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .paths import ROOT


def resolve_app_binary() -> Path:
    debug = ROOT / ".build" / "debug" / "PublicDocumentApp"
    sources = list((ROOT / "Sources" / "PublicDocumentApp").glob("*.swift"))
    newest_source = max((path.stat().st_mtime for path in sources), default=0)
    if not debug.is_file() or (newest_source and debug.stat().st_mtime < newest_source):
        subprocess.run(
            ["swift", "build", "--product", "PublicDocumentApp"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    return debug


def run_ai_bridge(message: dict[str, Any]) -> dict[str, Any]:
    result = subprocess.run(
        [str(resolve_app_binary()), "--ai-bridge-stdin"],
        cwd=ROOT,
        input=json.dumps(message, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("AI 제공자 작업을 완료하지 못했습니다.")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise RuntimeError("AI 제공자 응답 형식이 올바르지 않습니다.")
    return payload


def export_project(project: dict[str, Any], formats: list[str], consent: bool, downloads: Path) -> dict[str, Any]:
    operation = uuid.uuid4().hex
    work = Path(tempfile.mkdtemp(prefix="public-document-web-export-"))
    destination = work / "out"
    destination.mkdir()
    source = work / "project.json"
    source.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    command = [
        str(resolve_app_binary()),
        "--export-project",
        str(source),
        str(destination),
        "--formats",
        ",".join(formats),
    ]
    if consent:
        command.append("--flattening-consent")
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("내보내기가 응답하지 않아 중단했습니다.") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "export failed").strip()
        raise RuntimeError(detail) from error
    receipt = json.loads(result.stdout)
    public = downloads / operation
    public.mkdir(parents=True)
    title = _safe_filename(str(project.get("title") or "공공문서"))
    for item in receipt.get("results") or []:
        name = item.get("fileName") or item.get("relativePath")
        if not name:
            continue
        produced = destination / name
        if not produced.is_file():
            continue
        suffix = Path(name).suffix
        published_name = f"{title}{suffix}"
        published = public / published_name
        shutil.copy2(produced, published)
        item["fileName"] = published_name
        item["relativePath"] = published_name
        item["downloadURL"] = f"/downloads/{operation}/{published_name}"
    shutil.rmtree(work, ignore_errors=True)
    return receipt


def _safe_filename(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "._- " else "_" for character in value)
    cleaned = cleaned.strip() or "공공문서"
    return cleaned[:80]
