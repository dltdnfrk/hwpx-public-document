#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from typing import Any, Optional, Tuple, TypedDict
import unicodedata
import stat
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from public_document_web.evidence_path import prepare_output_file


GOAL_IDS = tuple(f"G00{number}" for number in range(2, 7))
TREE_PATTERN = re.compile(r"@tree:([0-9a-f]+)")
WORKTREE_PATTERN = re.compile(r"@worktree:([0-9a-f]+)")

REQUIRED_ARTIFACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "G002": {
        "C001": ("layout-parity/result.json", "layout-parity/transcript.txt"),
        "C002": ("malformed/transcript.txt", "malformed/empty-output-inventory.json"),
        "C003": (
            "fireblight/receipt.json",
            "fireblight/package-inspection.json",
            "fireblight/transcript.txt",
        ),
    },
    "G003": {
        "C001": ("roundtrip/matrix.json", "roundtrip/transcript.txt"),
        "C002": ("adversarial/result.json", "adversarial/transcript.txt"),
        "C003": (
            "basic/receipt.json",
            "basic/pytest-transcript.txt",
            "basic/capability-diff.json",
        ),
    },
    "G004": {
        "C001": (
            "happy/action-log.json",
            "happy/before-project.json",
            "happy/after-project.json",
            "happy/screenshot.png",
        ),
        "C002": (
            "invalid/action-log.json",
            "invalid/unchanged-state.json",
            "invalid/screenshot.png",
        ),
        "C003": (
            "export/action-log.json",
            "export/receipt.json",
            "export/package-inspection.json",
            "export/screenshot.png",
        ),
    },
    "G005": {
        "C001": ("verify/summary.json", "verify/transcript.txt"),
        "C002": (
            "tamper/summary.json",
            "tamper/before-status.txt",
            "tamper/after-status.txt",
            "tamper/transcript.txt",
        ),
        "C003": (
            "repeat/summary.json",
            "repeat/transcript.txt",
            "repeat/run-1/summary.json",
            "repeat/run-2/summary.json",
        ),
    },
    "G006": {
        "C001": (
            "app-happy-release/action-log.json",
            "app-happy-release/receipt.json",
            "app-happy-release/package-inspection.json",
            "app-happy-release/batch-receipt.json",
            "app-happy-release/screenshot.png",
            "app-happy-release/transcript.txt",
        ),
        "C002": (
            "app-invalid/action-log.json",
            "app-invalid/destination-hash-diff.json",
            "app-invalid/screenshot.png",
            "app-invalid/transcript.txt",
        ),
        "C003": (
            "release/PublicDocument.zip",
            "release/PublicDocument.SHA256SUMS",
            "release/PublicDocument.verification.json",
            "release/transcript.txt",
            "release/cleanup.json",
        ),
    },
}

CLAUSE_MAPPINGS = (
    (
        "one-maintainable-layout-source",
        "Official layout is shared by DOCX, HWPX/HWP, preview, and macros.",
        ("G002",),
    ),
    (
        "proven-semantic-preservation",
        "Required format semantics round-trip or remain explicitly blocked.",
        ("G003",),
    ),
    (
        "embedded-macro-workflow",
        "The embedded Beompis-style macro workflow works on the real Studio surface.",
        ("G004",),
    ),
    (
        "real-format-and-macos-qa",
        "DOCX, HWPX/HWP, Markdown, and the packaged macOS app have real-surface QA.",
        ("G003", "G006"),
    ),
    (
        "regression-and-provenance",
        "Full-suite regression, generated provenance, tamper rejection, and deterministic goldens pass.",
        ("G005",),
    ),
    (
        "release-recovery-maintenance",
        "Clean release packaging plus recovery and maintenance documentation exist.",
        ("G005", "G006"),
    ),
    (
        "safety-boundaries",
        "No semantic downgrade, cloud/localStorage core, unauthorized commit, or user Applications mutation occurred.",
        ("G003", "G005", "G006"),
    ),
)

REFRESH_ARTIFACTS = (
    "G007/a1/certified/final-verify/summary.json",
    "G007/a1/certified/final-verify/transcript.txt",
    "G007/a1/certified/tamper/summary.json",
    "G007/a1/certified/tamper/transcript.txt",
    "G007/a1/certified/repeat/summary.json",
    "G007/a1/certified/repeat/transcript.txt",
    "G007/a1/certified/app-happy/action-log.json",
    "G007/a1/certified/app-happy/screenshot.png",
    "G007/a1/certified/app-invalid/action-log.json",
    "G007/a1/certified/app-invalid/screenshot.png",
    "G007/a1/certified/macro/action-log.json",
    "G007/a1/certified/macro/screenshot.png",
    "G007/a1/certified/fireblight/package-inspection.json",
    "G007/a1/certified/release/PublicDocument.zip",
    "G007/a1/certified/release/PublicDocument.SHA256SUMS",
    "G007/a1/certified/release/PublicDocument.verification.json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit durable ULW evidence against the original frozen-tree brief."
    )
    parser.add_argument("--session", required=True)
    parser.add_argument("--tree", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--goals", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument(
        "--adversarial-ledger-copy",
        type=Path,
        help="write and audit an isolated ledger copy with one stale stamp and missing artifact",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_stamp(value: str | None) -> str | None:
    if not value:
        return None
    match = TREE_PATTERN.search(value)
    return match.group(1) if match else None


def worktree_stamp(value: str | None) -> str | None:
    match = WORKTREE_PATTERN.search(value or "")
    return match.group(1) if match else None


def captured_artifact_hash(event: dict[str, Any], relative: str) -> str | None:
    # Capturers supply exact-byte hashes in the evidence_captured ledger event.
    # Never derive the expected identity from the file being audited.
    hashes = event.get("artifactHashes")
    value = normalized_sha256(hashes.get(relative)) if isinstance(hashes, dict) else None
    return value if value and re.fullmatch(r"[0-9a-f]{64}", value) else None


def parse_ledger(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"ledger line {index} is invalid JSON: {error}") from error
        if not isinstance(event, dict):
            raise RuntimeError(f"ledger line {index} is not an object")
        events.append(event)
    return events


def write_adversarial_ledger(
    source: Path,
    destination: Path,
    expected_tree: str,
) -> Path:
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"adversarial ledger output already exists: {destination}")
    events = parse_ledger(source)
    target_index = max(
        index
        for index, event in enumerate(events)
        if event.get("kind") == "evidence_captured"
        and event.get("goalId") == "G002"
        and event.get("criterionId") == "C001"
    )
    target = dict(events[target_index])
    for field in ("evidence", "capturedEvidence"):
        value = target.get(field)
        if isinstance(value, str):
            target[field] = value.replace(
                f"@tree:{expected_tree}",
                "@tree:deadbeef",
            )
    target["artifacts"] = ["G002/a1/layout-parity/missing-artifact.json"]
    events[target_index] = target
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )
    return destination


def artifact_paths(
    goal: dict[str, Any],
    criterion_id: str,
    event: dict[str, Any],
) -> list[str]:
    override = event.get("artifacts")
    required = [
        f"{goal['id']}/a{goal['attempt']}/{relative}"
        for relative in REQUIRED_ARTIFACTS[goal["id"]][criterion_id]
    ]
    if isinstance(override, list) and all(isinstance(item, str) for item in override):
        return [*required, *[item for item in override if item not in required]]
    return required


def safe_artifact(
    evidence_root: Path,
    relative: str,
) -> Tuple[Optional[Path], Optional[str]]:
    if (
        not relative
        or Path(relative).is_absolute()
        or "\\" in relative
        or ".." in Path(relative).parts
        or "." in Path(relative).parts
    ):
        return None, f"unsafe artifact path: {relative}"
    candidate = evidence_root / relative
    resolved_root = evidence_root.resolve()
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        return None, f"artifact escapes evidence root: {relative}"
    current = candidate.parent
    while current != evidence_root.parent:
        if current.is_symlink():
            return None, f"artifact path contains symbolic-link ancestor: {relative}"
        if current == evidence_root:
            break
        current = current.parent
    return candidate, None


def valid_png(path: Path) -> bool:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset = 8
    chunk_index = 0
    has_header = False
    compressed = bytearray()
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(data):
            return False
        chunk = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : end])[0]
        if zlib.crc32(chunk_type + chunk) & 0xFFFFFFFF != expected_crc:
            return False
        if chunk_index == 0:
            if chunk_type != b"IHDR" or length != 13:
                return False
            width, height = struct.unpack(">II", chunk[:8])
            if width == 0 or height == 0:
                return False
            has_header = True
        if chunk_type == b"IDAT":
            compressed.extend(chunk)
        if chunk_type == b"IEND":
            if length != 0 or end != len(data) or not has_header or not compressed:
                return False
            try:
                return bool(zlib.decompress(bytes(compressed)))
            except zlib.error:
                return False
        offset = end
        chunk_index += 1
    return False


def valid_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as package:
            members = package.infolist()
            if not members or package.testzip() is not None:
                return False
            for member in members:
                name = member.filename
                parts = Path(name.replace("\\", "/")).parts
                if name.startswith(("/", "\\")) or ".." in parts:
                    return False
                mode = (member.external_attr >> 16) & 0xFFFF
                kind = stat.S_IFMT(mode)
                if member.is_dir():
                    if kind not in (0, stat.S_IFDIR):
                        return False
                elif kind not in (0, stat.S_IFREG):
                    return False
            return True
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return False


def normalized_sha256(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    return value[7:] if value.startswith("sha256:") else value


def valid_release_contents(archive: Path, inventory: Path) -> bool:
    try:
        entries: dict[str, str] = {}
        for line in inventory.read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            if match is None or match.group(2) in entries:
                return False
            entries[match.group(2)] = match.group(1)
        entries = {
            unicodedata.normalize("NFC", name): digest
            for name, digest in entries.items()
        }
        required = {
            "PublicDocument.app/Contents/Info.plist",
            "PublicDocument.app/Contents/MacOS/PublicDocumentApp",
            "PublicDocument.app/Contents/_CodeSignature/CodeResources",
            "Evidence/SHA256SUMS",
        }
        current_provenance = {
            "genoffice-docs-port.json": sha256(
                ROOT / "provenance/genoffice-docs-port.json"
            ),
            "upstream-lock.json": sha256(ROOT / "provenance/upstream-lock.json"),
        }
        for name, digest in current_provenance.items():
            if entries.get(f"Evidence/Provenance/{name}") != digest:
                return False
            if (
                entries.get(
                    f"PublicDocument.app/Contents/Resources/Provenance/{name}"
                )
                != digest
            ):
                return False
        with tempfile.TemporaryDirectory(prefix="public-document-release-audit.") as temporary:
            with zipfile.ZipFile(archive) as package:
                archived_files = [member for member in package.infolist() if not member.is_dir()]
                if len(archived_files) != len(entries):
                    return False
            extracted = subprocess.run(
                ["/usr/bin/ditto", "-x", "-k", str(archive), temporary],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if extracted.returncode != 0:
                return False
            root = Path(temporary)
            extracted_paths = list(root.rglob("*"))
            if any(path.is_symlink() for path in extracted_paths):
                return False
            if any(not path.is_dir() and not path.is_file() for path in extracted_paths):
                return False
            files = {
                unicodedata.normalize("NFC", str(path.relative_to(root))): path
                for path in root.rglob("*")
                if path.is_file() and not path.is_symlink()
            }
            if set(files) != set(entries) or not required.issubset(entries):
                return False
            if any(sha256(path) != entries[name] for name, path in files.items()):
                return False
            app = root / "PublicDocument.app"
            if not app.is_dir():
                return False
            codesign = subprocess.run(
                ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            architecture = subprocess.run(
                ["/usr/bin/lipo", "-archs", str(app / "Contents/MacOS/PublicDocumentApp")],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return (
                codesign.returncode == 0
                and architecture.returncode == 0
                and architecture.stdout.strip() == "arm64"
            )
    except (
        OSError,
        UnicodeDecodeError,
        zipfile.BadZipFile,
        KeyError,
        subprocess.SubprocessError,
    ):
        return False


def release_sibling(directory: Path, value: Any) -> Optional[Path]:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    relative = Path(value)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != value:
        return None
    candidate = directory / relative
    resolved_directory = directory.resolve()
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate.parent != resolved_directory:
        return None
    return candidate


def validate_artifact(relative: str, path: Path, defects: list[str]) -> bool:
    if path.suffix == ".png":
        valid = valid_png(path)
        if not valid:
            defects.append(f"invalid PNG artifact: {relative}")
        return valid
    if path.suffix == ".zip":
        valid = valid_zip(path)
        if not valid:
            defects.append(f"invalid ZIP artifact: {relative}")
        return valid
    if path.name == "transcript.txt":
        try:
            transcript = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            transcript = ""
        lines = [line for line in transcript.splitlines() if line.strip()]
        valid = (
            any(
                line.startswith(("$ ", "## "))
                for line in lines
            )
            and any(
                not line.startswith(("$ ", "## "))
                for line in lines
            )
        )
        if not valid:
            defects.append(f"invalid transcript contract: {relative}")
        return valid
    if path.name.endswith("SHA256SUMS"):
        try:
            lines = [
                line for line in path.read_text(encoding="utf-8").splitlines()
                if line
            ]
        except (OSError, UnicodeDecodeError):
            lines = []
        valid = bool(lines) and all(
            re.fullmatch(r"[0-9a-f]{64}  .+", line) is not None
            for line in lines
        )
        if not valid:
            defects.append(f"invalid SHA256 inventory contract: {relative}")
        return valid
    if path.suffix != ".json":
        try:
            valid = bool(path.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeDecodeError):
            valid = False
        if not valid:
            defects.append(f"unsupported or unreadable evidence artifact: {relative}")
        return valid
    try:
        value = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        defects.append(f"invalid JSON artifact: {path}: {error}")
        return False
    if not isinstance(value, (dict, list)) or not value:
        defects.append(f"empty or unsupported JSON artifact: {relative}")
        return False
    valid = True
    recognized = False
    if isinstance(value, dict) and "status" in value:
        recognized = True
        if value["status"] != "pass":
            defects.append(f"artifact does not report pass: {relative}")
            valid = False
    status_contracts: dict[str, tuple[str, ...]] = {
        "matrix.json": ("formats", "caseCount", "cases", "mismatches"),
        "result.json": ("cleanup",),
        "summary.json": ("schemaVersion", "cleanup"),
        "package-inspection.json": ("status",),
        "action-log.json": ("schemaVersion", "scenario"),
        "cleanup.json": ("schemaVersion", "liveProcesses"),
        "capability-diff.json": ("currentSHA256", "frozenSHA256", "unjustifiedDowngrades"),
    }
    if path.name in status_contracts:
        recognized = True
        required = status_contracts[path.name]
        if not isinstance(value, dict) or value.get("status") != "pass" or any(
            key not in value for key in required
        ):
            defects.append(f"invalid {path.name} contract: {relative}")
            valid = False
        minimum_fields = {
            "result.json": 3,
            "summary.json": 4,
            "package-inspection.json": 3,
            "action-log.json": 4,
        }.get(path.name, 1)
        if not isinstance(value, dict) or len(value) < minimum_fields:
            defects.append(f"incomplete {path.name} contract: {relative}")
            valid = False
    if path.name == "matrix.json" and isinstance(value, dict):
        formats = value.get("formats")
        cases = value.get("cases")
        case_count = value.get("caseCount")
        matrix_valid = (
            isinstance(formats, list)
            and len(formats) == 4
            and set(formats) == {"hwpx", "hwp", "docx", "markdown"}
            and isinstance(cases, list)
            and isinstance(case_count, int)
            and case_count > 0
            and len(cases) == case_count * len(formats)
            and value.get("mismatches") == []
            and all(
                isinstance(row, dict)
                and row.get("status") == "pass"
                and row.get("expected") == row.get("actual")
                and row.get("format") in formats
                for row in cases
            )
        )
        if not matrix_valid:
            defects.append(f"invalid matrix evidence semantics: {relative}")
            valid = False
    if path.name == "result.json" and isinstance(value, dict):
        if relative.endswith("layout-parity/result.json"):
            surfaces = value.get("surfaces")
            profile = value.get("profileSHA256")
            typeset = value.get("typesetProbe")
            result_valid = (
                isinstance(profile, str)
                and re.fullmatch(r"sha256:[0-9a-f]{64}", profile) is not None
                and isinstance(surfaces, dict)
                and set(surfaces) == {"native", "docx", "hwpx", "preview", "macro"}
                and set(surfaces.values()) == {profile}
                and set(value.get("publishedFormats") or []) == {"docx", "hwpx"}
                and value.get("tokenID") == "print-tokens-1.0.0"
                and value.get("margins") == {
                    "top": 20, "right": 20, "bottom": 10, "left": 20
                }
                and isinstance(typeset, dict)
                and typeset.get("native") == typeset.get("macro")
                and typeset.get("native") == typeset.get("preview")
                and isinstance(typeset.get("native"), list)
                and bool(typeset["native"])
            )
        elif relative.endswith("adversarial/result.json"):
            result_valid = (
                set(value.get("blockedFormats") or [])
                == {"hwpx", "hwp", "docx", "markdown"}
                and value.get("publishedFormats") == []
                and value.get("failedFormats") == []
                and value.get("changedDestinations") == []
                and value.get("beforeHashes") == value.get("afterHashes")
                and bool(value.get("semanticLossCapabilities"))
            )
        else:
            result_valid = False
        if not result_valid:
            defects.append(f"invalid result evidence semantics: {relative}")
            valid = False
    if path.name == "receipt.json" and isinstance(value, dict):
        recognized = True
        required_lists = (
            "selectedFormats",
            "publishedFormats",
            "blockedFormats",
            "failedFormats",
            "results",
        )
        selected = value.get("selectedFormats")
        published = value.get("publishedFormats")
        blocked = value.get("blockedFormats")
        failed = value.get("failedFormats")
        results = value.get("results")
        selected_values = selected if isinstance(selected, list) else []
        published_values = published if isinstance(published, list) else []
        blocked_values = blocked if isinstance(blocked, list) else []
        failed_values = failed if isinstance(failed, list) else []
        result_values = results if isinstance(results, list) else []
        if (
            not isinstance(value.get("operationID"), str)
            or not all(isinstance(value.get(key), list) for key in required_lists)
            or not selected_values
            or not set(
                published_values + blocked_values + failed_values
            ).issubset(set(selected_values))
            or not all(
                isinstance(row, dict)
                and row.get("format") in set(published_values + failed_values)
                for row in result_values
            )
        ):
            defects.append(f"invalid export receipt contract: {relative}")
            valid = False
    if path.name in {"before-project.json", "after-project.json", "unchanged-state.json"}:
        recognized = True
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("schemaVersion"), int)
            or not isinstance(value.get("documentID"), str)
            or not isinstance(value.get("currentRevisionID"), str)
            or not isinstance(value.get("elements"), list)
        ):
            defects.append(f"invalid project snapshot contract: {relative}")
            valid = False
    if path.name == "empty-output-inventory.json":
        recognized = True
        if not isinstance(value, dict) or not isinstance(value.get("packages"), list):
            defects.append(f"invalid package inventory contract: {relative}")
            valid = False
    if path.name == "batch-receipt.json":
        recognized = True
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("operationID"), str)
            or not isinstance(value.get("selectedFormats"), list)
            or not isinstance(value.get("items"), list)
            or not isinstance(value.get("state"), str)
        ):
            defects.append(f"invalid batch receipt contract: {relative}")
            valid = False
    if relative.endswith("destination-hash-diff.json") and isinstance(value, dict) and (
        value.get("unchanged") is not True or value.get("publishedFiles") != []
    ):
        recognized = True
        defects.append(f"invalid destination boundary receipt: {relative}")
        valid = False
    elif relative.endswith("destination-hash-diff.json"):
        recognized = True
    if relative.endswith("PublicDocument.verification.json") and isinstance(value, dict):
        recognized = True
        archive = value.get("archive", {})
        inventory = value.get("bundle", {}).get("sha256Inventory", {})
        archive_path = release_sibling(path.parent, archive.get("file"))
        inventory_path = release_sibling(path.parent, inventory.get("file"))
        if archive_path is None or inventory_path is None:
            defects.append(f"release binding points outside release directory: {relative}")
            valid = False
        binding_valid = (
            archive_path is not None
            and archive_path.is_file()
            and not archive_path.is_symlink()
            and valid_zip(archive_path)
            and normalized_sha256(archive.get("sha256")) == sha256(archive_path)
            and inventory_path is not None
            and inventory_path.is_file()
            and not inventory_path.is_symlink()
            and normalized_sha256(inventory.get("sha256")) == sha256(inventory_path)
            and valid_release_contents(archive_path, inventory_path)
        )
        if not binding_valid:
            defects.append(f"release archive contents or inventory binding is invalid: {relative}")
            valid = False
        if (
            value.get("app", {}).get("codesignVerification") != "pass"
            or value.get("verification") != {
            "freshTemporaryExtraction": True,
            "archiveExtendedAttributes": "excluded",
            "extractedInventoryComparison": "pass",
            "sha256InventoryRecheck": "pass",
            }
        ):
            defects.append(f"invalid release verification receipt: {relative}")
            valid = False
    if relative.endswith("action-log.json") and (
        not isinstance(value, dict) or value.get("status") != "pass"
    ):
        recognized = True
        defects.append(f"desktop/browser action log is not pass: {relative}")
        valid = False
    elif relative.endswith("action-log.json") and isinstance(value, dict):
        macro_valid = (
            isinstance(value.get("actions"), list)
            and bool(value["actions"])
            and isinstance(value.get("cleanup"), dict)
            and value["cleanup"].get("browser") == "closed"
            and value["cleanup"].get("httpServer") == "closed"
        )
        desktop_valid = (
            isinstance(value.get("studioReady"), dict)
            and value["studioReady"].get("windowVisible") is True
            and isinstance(value.get("forbiddenApplicationsSnapshot"), dict)
            and value["forbiddenApplicationsSnapshot"].get("unchanged") is True
            and isinstance(value.get("processCleanup"), dict)
            and value["processCleanup"].get("status") == "terminated"
        )
        if not macro_valid and not desktop_valid:
            defects.append(f"invalid action log evidence semantics: {relative}")
            valid = False
    if path.name == "package-inspection.json" and isinstance(value, dict):
        macro_inspection = (
            value.get("staleContentHTMLAbsent") is True
            and isinstance(value.get("officialMarkersPresent"), list)
            and len(value["officialMarkersPresent"]) >= 4
            and isinstance(value.get("tableRowCount"), int)
            and value["tableRowCount"] >= 2
            and re.fullmatch(r"[0-9a-f]{64}", str(value.get("docxSHA256", "")))
            is not None
        )
        fireblight_inspection = (
            value.get("margins") == value.get("expectedMargins")
            and isinstance(value.get("paragraphCount"), int)
            and value["paragraphCount"] > 0
            and isinstance(value.get("markerParagraphCount"), int)
            and value["markerParagraphCount"] > 0
            and isinstance(value.get("tableRowCount"), int)
            and value["tableRowCount"] > 0
            and re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                str(value.get("layoutProfileSHA256", "")),
            )
            is not None
        )
        if not macro_inspection and not fireblight_inspection:
            defects.append(f"invalid package inspection semantics: {relative}")
            valid = False
    if path.name == "summary.json" and isinstance(value, dict):
        common_summary = (
            value.get("schemaVersion") == 1
            and value.get("status") == "pass"
            and isinstance(value.get("cleanup"), str)
            and bool(value["cleanup"])
        )
        if "/tamper/" in f"/{relative}":
            summary_valid = common_summary and (
                value.get("tamperRejected") is True
                and value.get("repositoryUnchanged") is True
            )
        elif relative.endswith("repeat/summary.json"):
            summary_valid = common_summary and (
                isinstance(value.get("repeatCount"), int)
                and value["repeatCount"] >= 2
                and value.get("normalizedManifestsIdentical") is True
                and value.get("normalizedArtifactHashesIdentical") is True
                and bool(value.get("normalizedManifestHashes"))
                and bool(value.get("normalizedArtifactHashes"))
            )
        else:
            identity = value.get("sourceIdentity")
            summary_valid = common_summary and (
                isinstance(value.get("gates"), list)
                and bool(value["gates"])
                and isinstance(value.get("normalizedManifestHashes"), dict)
                and len(value["normalizedManifestHashes"]) == 4
                and isinstance(value.get("normalizedArtifactHashes"), dict)
                and bool(value["normalizedArtifactHashes"])
                and isinstance(identity, dict)
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(identity.get("worktreeSHA256", "")),
                )
                is not None
                and isinstance(identity.get("worktreeDirty"), bool)
                and isinstance(identity.get("headTree"), str)
            )
        if not summary_valid:
            defects.append(f"invalid summary evidence semantics: {relative}")
            valid = False
    if not recognized:
        defects.append(f"invalid or unknown JSON evidence contract: {relative}")
        valid = False
    return valid


class SourceIdentity(TypedDict):
    headTree: str
    worktreeSHA256: str
    worktreeDirty: bool


def audit_safety(
    evidence_root: Path,
    events: list[dict[str, Any]],
    defects: list[str],
    current_identity: SourceIdentity,
) -> dict[str, Any]:
    runtime_files = [
        *sorted((ROOT / "Resources" / "Studio").rglob("*.js")),
        *sorted((ROOT / "Sources" / "PublicDocumentApp").glob("*.swift")),
    ]
    forbidden_hits: list[str] = []
    for path in runtime_files:
        source = path.read_text(encoding="utf-8").lower()
        for token in ("localstorage", "onnara", "document24"):
            if token in source:
                forbidden_hits.append(f"{path.relative_to(ROOT)}:{token}")
    if forbidden_hits:
        defects.extend(f"forbidden runtime core: {hit}" for hit in forbidden_hits)

    commit_events = [
        event for event in events if "commit" in str(event.get("kind", "")).lower()
    ]
    if commit_events:
        defects.append("ledger contains an unauthorized commit event")

    capability = ROOT / "Resources/Capabilities/format-capabilities-1.0.0.json"
    verifier_summary = evidence_root / "G007/a1/certified/final-verify/summary.json"
    verifier = load_json(verifier_summary)
    source_identity = verifier.get("sourceIdentity", {})
    if any(source_identity.get(key) != value for key, value in current_identity.items()) or (
        not isinstance(source_identity.get("worktreeDirty"), bool)
    ):
        defects.append("production gate source identity is stale or incomplete")
    current_manifests = {
        relative: sha256(ROOT / relative)
        for relative in (
            "Resources/Studio/official-layout-profile.js",
            "Resources/Capabilities/format-capabilities-1.0.0.json",
            "provenance/genoffice-docs-port.json",
            "provenance/upstream-lock.json",
        )
    }
    if verifier.get("normalizedManifestHashes") != current_manifests:
        defects.append("production gate manifest hashes differ from the current worktree")
    expected_capability_hash = verifier["normalizedManifestHashes"][
        "Resources/Capabilities/format-capabilities-1.0.0.json"
    ]
    capability_hash_matches = sha256(capability) == expected_capability_hash
    if not capability_hash_matches:
        defects.append("frozen capability matrix differs from the passing production gate")

    happy = load_json(
        evidence_root / "G007/a1/certified/app-happy/action-log.json"
    )
    invalid = load_json(evidence_root / "G007/a1/certified/app-invalid/action-log.json")
    applications_unchanged = (
        happy["forbiddenApplicationsSnapshot"]["unchanged"] is True
        and invalid["forbiddenApplicationsSnapshot"]["unchanged"] is True
    )
    if not applications_unchanged:
        defects.append("~/Applications/PublicDocument.app changed during desktop QA")
    formats = happy["export"]["publishedFormats"]
    if formats != ["hwpx", "hwp", "docx", "markdown"]:
        defects.append("desktop QA did not publish all declared formats")

    documentation = [
        ROOT / "docs/maintenance-and-recovery.md",
        ROOT / "docs/release-and-recovery.md",
    ]
    missing_docs = [str(path.relative_to(ROOT)) for path in documentation if not path.is_file()]
    defects.extend(f"missing operations document: {path}" for path in missing_docs)
    return {
        "forbiddenRuntimeHits": forbidden_hits,
        "unauthorizedCommitEvents": len(commit_events),
        "capabilityMatrixHashMatchesProductionGate": capability_hash_matches,
        "userApplicationsAppUnchanged": applications_unchanged,
        "desktopPublishedFormats": formats,
        "operationsDocuments": [
            str(path.relative_to(ROOT)) for path in documentation if path.is_file()
        ],
    }


def main() -> int:
    arguments = parse_args()
    session_root = ROOT / ".omo" / "ulw-loop" / arguments.session
    goals_path = arguments.goals or session_root / "goals.json"
    ledger_path = arguments.ledger or session_root / "ledger.jsonl"
    evidence_root = arguments.evidence_root or (
        ROOT / ".omo" / "evidence" / "ulw" / arguments.session
    )
    output = arguments.out if arguments.out.is_absolute() else ROOT / arguments.out

    if not goals_path.is_file():
        print(f"goals file is missing: {goals_path}", file=sys.stderr)
        return 2
    if not ledger_path.is_file():
        print(f"ledger file is missing: {ledger_path}", file=sys.stderr)
        return 2
    try:
        output = prepare_output_file(output)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    if arguments.adversarial_ledger_copy:
        adversarial = (
            arguments.adversarial_ledger_copy
            if arguments.adversarial_ledger_copy.is_absolute()
            else ROOT / arguments.adversarial_ledger_copy
        )
        try:
            ledger_path = write_adversarial_ledger(
                ledger_path,
                adversarial,
                arguments.tree,
            )
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
            return 2

    defects: list[str] = []
    current_identity: SourceIdentity = {
        "headTree": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"], text=True,
        ).strip(),
        "worktreeSHA256": subprocess.check_output(
            [sys.executable, str(ROOT / "scripts/worktree-fingerprint.py"), str(ROOT)],
            text=True,
        ).strip(),
        "worktreeDirty": bool(subprocess.check_output(
            ["git", "-C", str(ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            text=True,
        )),
    }
    tree_valid = (
        re.fullmatch(r"[0-9a-f]{7,40}", arguments.tree) is not None
        and current_identity["headTree"].startswith(arguments.tree)
    )
    if not tree_valid:
        defects.append(f"requested tree does not match actual HEAD tree: {arguments.tree}")
    goals_document = load_json(goals_path)
    events = parse_ledger(ledger_path)
    goals_by_id = {goal["id"]: goal for goal in goals_document["goals"]}
    latest_evidence: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        if event.get("kind") == "evidence_captured":
            event_goal = event.get("goalId")
            event_criterion = event.get("criterionId")
            if isinstance(event_goal, str) and isinstance(event_criterion, str):
                latest_evidence[(event_goal, event_criterion)] = event

    criterion_rows: list[dict[str, Any]] = []
    artifact_rows: list[dict[str, Any]] = []
    goal_validity = {goal_id: tree_valid for goal_id in GOAL_IDS}
    for goal_id in GOAL_IDS:
        goal = goals_by_id.get(goal_id)
        if not goal:
            defects.append(f"missing goal: {goal_id}")
            continue
        if goal.get("status") != "complete":
            defects.append(f"goal is not complete: {goal_id}")
            goal_validity[goal_id] = False
        for criterion in goal.get("successCriteria", []):
            criterion_id = criterion["id"]
            key = (goal_id, criterion_id)
            event = latest_evidence.get(key)
            if criterion.get("status") != "pass":
                defects.append(f"criterion is not pass: {goal_id}/{criterion_id}")
                goal_validity[goal_id] = False
            if not criterion.get("capturedEvidence"):
                defects.append(f"criterion evidence is empty: {goal_id}/{criterion_id}")
            goal_tree = tree_stamp(criterion.get("capturedEvidence"))
            if goal_tree != arguments.tree:
                defects.append(
                    f"stale tree stamp in goals: {goal_id}/{criterion_id}: "
                    f"{goal_tree or 'missing'} != {arguments.tree}"
                )
                goal_validity[goal_id] = False
            if not event:
                defects.append(f"ledger evidence event is missing: {goal_id}/{criterion_id}")
                event = {}
            ledger_tree = tree_stamp(
                event.get("capturedEvidence") or event.get("evidence")
            )
            if ledger_tree != arguments.tree:
                defects.append(
                    f"stale tree stamp in ledger: {goal_id}/{criterion_id}: "
                    f"{ledger_tree or 'missing'} != {arguments.tree}"
                )
                goal_validity[goal_id] = False
            goal_worktree = worktree_stamp(criterion.get("capturedEvidence"))
            ledger_worktree = worktree_stamp(event.get("capturedEvidence") or event.get("evidence"))
            for source, captured in (("goals", goal_worktree), ("ledger", ledger_worktree)):
                if captured != current_identity["worktreeSHA256"]:
                    defects.append(f"stale or missing worktree stamp in {source}: {goal_id}/{criterion_id}")
                    goal_validity[goal_id] = False
            paths = artifact_paths(goal, criterion_id, event)
            criterion_rows.append(
                {
                    "goal": goal_id,
                    "criterion": criterion_id,
                    "status": criterion.get("status"),
                    "goalTree": goal_tree,
                    "ledgerTree": ledger_tree,
                    "goalWorktree": goal_worktree,
                    "ledgerWorktree": ledger_worktree,
                    "artifacts": paths,
                }
            )
            for relative in paths:
                artifact, path_error = safe_artifact(evidence_root, relative)
                if path_error:
                    defects.append(path_error)
                    goal_validity[goal_id] = False
                exists = False
                size = 0
                artifact_hash = None
                if artifact is not None:
                    exists = artifact.is_file() and not artifact.is_symlink()
                    if exists:
                        size = artifact.stat().st_size
                        artifact_hash = sha256(artifact) if size > 0 else None
                if not exists:
                    defects.append(f"missing artifact: {relative}")
                    goal_validity[goal_id] = False
                elif size <= 0:
                    defects.append(f"empty artifact: {relative}")
                    goal_validity[goal_id] = False
                else:
                    assert artifact is not None
                    if not validate_artifact(relative, artifact, defects):
                        goal_validity[goal_id] = False
                captured_hash = captured_artifact_hash(event, relative)
                if captured_hash is None or captured_hash != artifact_hash:
                    defects.append(f"missing or mismatched captured artifact hash: {relative}")
                    goal_validity[goal_id] = False
                artifact_rows.append(
                    {
                        "path": relative,
                        "exists": exists,
                        "sizeBytes": size,
                        "sha256": artifact_hash,
                        "capturedSHA256": captured_hash,
                    }
                )

    refresh_rows: list[dict[str, Any]] = []
    refresh_event = latest_evidence.get(("G007", "C001"), {})
    refresh_stamp = refresh_event.get("capturedEvidence") or refresh_event.get("evidence")
    if REFRESH_ARTIFACTS and (
        tree_stamp(refresh_stamp) != arguments.tree
        or worktree_stamp(refresh_stamp) != current_identity["worktreeSHA256"]
    ):
        defects.append("refreshed evidence source identity is stale or incomplete")
    for relative in REFRESH_ARTIFACTS:
        artifact, path_error = safe_artifact(evidence_root, relative)
        if path_error:
            defects.append(path_error)
        exists = False
        size = 0
        artifact_hash = None
        if artifact is not None:
            exists = artifact.is_file() and not artifact.is_symlink()
            if exists:
                size = artifact.stat().st_size
                artifact_hash = sha256(artifact) if size > 0 else None
        if not exists:
            defects.append(f"missing refreshed artifact: {relative}")
        elif size <= 0:
            defects.append(f"empty refreshed artifact: {relative}")
        else:
            assert artifact is not None
            validate_artifact(relative, artifact, defects)
        captured_hash = captured_artifact_hash(refresh_event, relative)
        if captured_hash is None or captured_hash != artifact_hash:
            defects.append(f"missing or mismatched captured artifact hash: {relative}")
        refresh_rows.append(
            {
                "path": relative,
                "exists": exists,
                "sizeBytes": size,
                "sha256": artifact_hash,
                "capturedSHA256": captured_hash,
            }
        )

    brief_path = ROOT / goals_document["briefPath"]
    brief = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""
    if not brief.strip():
        defects.append("original brief is missing or empty")
    clause_rows: list[dict[str, Any]] = []
    for clause_id, statement, mapped_goals in CLAUSE_MAPPINGS:
        mapped_pass = all(
            goal_validity.get(goal_id) is True
            for goal_id in mapped_goals
        )
        if not mapped_pass:
            defects.append(f"brief clause is not covered: {clause_id}")
        clause_rows.append(
            {
                "clause": clause_id,
                "statement": statement,
                "goals": list(mapped_goals),
                "status": "pass" if mapped_pass else "fail",
            }
        )

    safety = audit_safety(evidence_root, events, defects, current_identity)
    result = {
        "schemaVersion": 1,
        "status": "pass" if not defects else "fail",
        "session": arguments.session,
        "tree": arguments.tree,
        "sourceIdentity": current_identity,
        "goals": list(GOAL_IDS),
        "criteria": criterion_rows,
        "artifacts": artifact_rows,
        "refreshedArtifacts": refresh_rows,
        "artifactCount": len(artifact_rows) + len(refresh_rows),
        "brief": str(brief_path.relative_to(ROOT)) if brief_path.is_file() else None,
        "clauseMappings": clause_rows,
        "safety": safety,
        "defects": defects,
        "cleanup": "read-only audit; no processes or temporary directories created",
    }
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if defects:
        for defect in defects:
            print(defect, file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
