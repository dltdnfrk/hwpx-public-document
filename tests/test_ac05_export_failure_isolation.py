from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Final

import pytest


ROOT: Final = Path(__file__).resolve().parents[1]
SOURCE_ROOT: Final = ROOT / "Sources" / "PublicDocumentApp"
SWIFT_SOURCES: Final = (
    "AIGovernance.swift",
    "AIGovernanceModels.swift",
    "AIGovernanceProposalEngine.swift",
    "AIGovernanceRevisionEngine.swift",
    "DocumentProject.swift",
    "DocumentProjectCoreModels.swift",
    "DocumentProjectAIModels.swift",
    "DocumentProjectState.swift",
    "DocumentProjectStore.swift",
    "ExportModel.swift",
    "FormatCapabilityPolicy.swift",
    "FormatCapabilityObservation.swift",
    "FormatCapabilityReporting.swift",
    "PackageArchive.swift",
    "PackageArchiveModels.swift",
    "PackageArchiveReader.swift",
    "PackageArchiveWriter.swift",
    "OfficialTypeset.swift",
    "OfficialLayoutEngine.swift",
    "ExportSerializers.swift",
    "ExportValidation.swift",
    "GenOfficeDocxAdapter.swift",
    "RhwpExport.swift",
    "RhwpLargeTextCompile.swift",
    "RhwpStyleCompile.swift",
    "RhwpTableCompile.swift",
    "TypstSidecar.swift",
    "DocumentExport.swift",
)


@pytest.fixture(scope="module")
def export_harness(tmp_path_factory: pytest.TempPathFactory) -> Path:
    build_root = tmp_path_factory.mktemp("ac05-export-failure-harness")
    binary = build_root / "export-failure-harness"
    _ = subprocess.run(
        [
            "swiftc",
            *(str(SOURCE_ROOT / name) for name in SWIFT_SOURCES),
            str(ROOT / "tests" / "fixtures" / "ac05_export_failure_harness.swift"),
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return binary


def _runtime_root(
    tmp_path: Path,
    *,
    include_genoffice: bool = False,
    include_rhwp: bool = False,
) -> Path:
    runtime_root = tmp_path / "isolated-runtime"
    capability_root = runtime_root / "Resources" / "Capabilities"
    capability_root.mkdir(parents=True)
    _ = shutil.copyfile(
        ROOT / "Resources" / "Capabilities" / "format-capabilities-1.0.0.json",
        capability_root / "format-capabilities-1.0.0.json",
    )
    template_root = runtime_root / "Resources" / "Templates"
    template_root.mkdir(parents=True)
    _ = shutil.copyfile(
        ROOT / "Resources" / "Templates" / "official-style-toolkit-1.0.0.json",
        template_root / "official-style-toolkit-1.0.0.json",
    )
    print_root = runtime_root / "Resources" / "Print"
    print_root.mkdir(parents=True)
    _ = shutil.copyfile(
        ROOT / "Resources" / "Print" / "print-tokens-1.0.0.json",
        print_root / "print-tokens-1.0.0.json",
    )
    if include_genoffice:
        _ = shutil.copytree(
            ROOT / "Resources" / "GenOffice", runtime_root / "Resources" / "GenOffice"
        )
        engine_root = runtime_root / "Resources" / "Engines"
        engine_root.mkdir(parents=True)
        _ = shutil.copy2(ROOT / "Resources" / "Engines" / "node", engine_root / "node")
    if include_rhwp:
        engine_root = runtime_root / "Resources" / "Engines"
        engine_root.mkdir(parents=True, exist_ok=True)
        _ = shutil.copy2(ROOT / "Resources" / "Engines" / "rhwp", engine_root / "rhwp")
    return runtime_root


def _run_harness(binary: Path, runtime_root: Path, destination: Path) -> str:
    result = subprocess.run(
        [str(binary), str(destination)],
        cwd=runtime_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _run_all_formats_harness(binary: Path, runtime_root: Path, destination: Path) -> str:
    result = subprocess.run(
        [str(binary), str(destination), "all-formats"],
        cwd=runtime_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _receipt_projection(receipt: str) -> str:
    result = subprocess.run(
        [
            "jq",
            "-S",
            "-c",
            "{blockedFormats,failedFormats,failures,publishedFormats}",
        ],
        input=receipt,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_adapter_failure_keeps_exporting_later_selected_formats(
    tmp_path: Path,
    export_harness: Path,
) -> None:
    # Given: HWPX is first, but the isolated runtime has no approved rhwp engine.
    runtime_root = _runtime_root(tmp_path, include_genoffice=True)
    destination = runtime_root / "adapter-failure"

    # When: HWPX, DOCX, and Markdown are exported from the same snapshot.
    receipt = _run_harness(export_harness, runtime_root, destination)

    # Then: HWPX has an exact runtime disposition and later siblings still publish.
    assert _receipt_projection(receipt) == json.dumps(
        {
            "blockedFormats": [],
            "failedFormats": ["hwpx"],
            "failures": [{
                "errorCode": "rhwp-failed",
                "format": "hwpx",
                "stage": "adapter",
                "userDiagnostic": "rhwp HWP 변환 또는 자기 재열기 검증에 실패했습니다: 고정된 rhwp 엔진이 없거나 승인 해시와 다릅니다",
            }],
            "publishedFormats": ["docx", "markdown"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert (destination / "ac05-fixture.docx").read_bytes().startswith(b"PK")
    assert "형식별 실패 격리 본문" in (destination / "ac05-fixture.md").read_text()
    assert not (destination / "ac05-fixture.hwpx").exists()
    assert not list(destination.glob(".*.tmp"))
    assert not list(destination.glob(".rhwp-*"))


def test_destination_failure_preserves_existing_sibling_and_continues(
    tmp_path: Path,
    export_harness: Path,
) -> None:
    # Given: the first selected output is an existing user-owned artifact.
    runtime_root = _runtime_root(tmp_path, include_genoffice=True)
    destination = runtime_root / "destination-failure"
    destination.mkdir()
    existing = destination / "ac05-fixture.hwpx"
    _ = existing.write_bytes(b"user-owned-existing-artifact")
    existing_hash = hashlib.sha256(existing.read_bytes()).hexdigest()

    # When: the same HWPX, DOCX, and Markdown request runs.
    receipt = _run_harness(export_harness, runtime_root, destination)

    # Then: the existing sibling is unchanged and the later formats are published.
    assert hashlib.sha256(existing.read_bytes()).hexdigest() == existing_hash
    assert _receipt_projection(receipt) == json.dumps(
        {
            "blockedFormats": [],
            "failedFormats": ["hwpx"],
            "failures": [{
                "errorCode": "destination-exists",
                "format": "hwpx",
                "stage": "destination",
                "userDiagnostic": "기존 파일은 자동으로 덮어쓰지 않습니다: ac05-fixture.hwpx",
            }],
            "publishedFormats": ["docx", "markdown"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert (destination / "ac05-fixture.docx").is_file()
    assert (destination / "ac05-fixture.md").is_file()
    assert not list(destination.glob(".*.tmp"))


def test_invalid_authored_element_identity_fails_before_any_export(
    tmp_path: Path,
    export_harness: Path,
) -> None:
    # Given: a project repeats an authored element ID in the immutable snapshot.
    runtime_root = _runtime_root(tmp_path)
    destination = runtime_root / "invalid-project"

    # When: the selected-format export is invoked with that invalid project.
    result = subprocess.run(
        [str(export_harness), str(destination), "duplicate-id"],
        cwd=runtime_root,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: project preflight fails before a destination or artifact is created.
    assert result.returncode != 0
    assert "작성 요소 ID가 비어 있거나 중복되었습니다" in result.stderr
    assert not destination.exists()


def test_fully_blocked_export_preserves_user_owned_sidecars(
    tmp_path: Path,
    export_harness: Path,
) -> None:
    runtime_root = _runtime_root(tmp_path)
    destination = runtime_root / "all-blocked"
    destination.mkdir()
    typ = destination / "document.typ"
    pdf = destination / "document.pdf"
    typ.write_bytes(b"user-owned-typ")
    pdf.write_bytes(b"user-owned-pdf")
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (typ, pdf)
    }

    result = subprocess.run(
        [str(export_harness), str(destination), "all-blocked"],
        cwd=runtime_root,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(result.stdout)

    assert receipt["publishedFormats"] == []
    assert set(receipt["blockedFormats"]) == {"hwpx", "hwp", "docx", "markdown"}
    assert before == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (typ, pdf)
    }
    assert sorted(path.name for path in destination.iterdir()) == [
        "document.pdf",
        "document.typ",
    ]


def test_missing_genoffice_runtime_fails_only_docx_and_keeps_hwp_siblings(
    tmp_path: Path,
    export_harness: Path,
) -> None:
    # Given: all non-DOCX engines are present but the approved GenOffice runtime is absent.
    runtime_root = _runtime_root(tmp_path, include_rhwp=True)
    destination = runtime_root / "missing-genoffice"

    # When: the one snapshot is exported to every supported format.
    receipt = _run_all_formats_harness(export_harness, runtime_root, destination)

    # Then: DOCX fails at its adapter boundary while HWPX, HWP, and Markdown publish.
    assert _receipt_projection(receipt) == json.dumps(
        {
            "blockedFormats": [],
            "failedFormats": ["docx"],
            "failures": [{
                "errorCode": "missing-genoffice-docx-engine",
                "format": "docx",
                "stage": "adapter",
                "userDiagnostic": "고정된 GenOffice DOCX 정규화 엔진을 찾을 수 없거나 무결성 검증에 실패했습니다.",
            }],
            "publishedFormats": ["hwpx", "hwp", "markdown"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert not (destination / "ac05-fixture.docx").exists()
    assert not list(destination.glob(".*.tmp"))
    assert not list(destination.glob(".genoffice-*"))


def test_tampered_genoffice_runtime_fails_only_docx_and_cleans_work_files(
    tmp_path: Path,
    export_harness: Path,
) -> None:
    # Given: the required runtime is copied but its signed normalizer bytes are modified.
    runtime_root = _runtime_root(tmp_path, include_genoffice=True, include_rhwp=True)
    normalizer = runtime_root / "Resources" / "GenOffice" / "genoffice-docx-normalize.cjs"
    _ = normalizer.write_bytes(normalizer.read_bytes() + b"\\n// tampered")
    destination = runtime_root / "tampered-genoffice"

    # When: the same all-format request is executed.
    receipt = _run_all_formats_harness(export_harness, runtime_root, destination)

    # Then: only DOCX is rejected before execution and no adapter temporary output remains.
    assert json.loads(receipt)["failedFormats"] == ["docx"]
    assert json.loads(receipt)["publishedFormats"] == ["hwpx", "hwp", "markdown"]
    assert not (destination / "ac05-fixture.docx").exists()
    assert not list(destination.glob(".*.tmp"))
    assert not list(destination.glob(".genoffice-*"))
