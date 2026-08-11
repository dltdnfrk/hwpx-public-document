from __future__ import annotations

import json
import atexit
import hashlib
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024


@lru_cache(maxsize=1)
def _release_binary() -> Path:
    package_root = Path(tempfile.mkdtemp(prefix="public-document-ac09-package."))
    atexit.register(shutil.rmtree, package_root, ignore_errors=True)
    app = package_root / "PublicDocument.app"
    environment = os.environ.copy()
    environment["PUBLIC_DOCUMENT_PACKAGE_PARENT"] = str(package_root)
    subprocess.run(
        [str(ROOT / "scripts" / "package-macos-app.sh"), str(app)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    binary = app / "Contents" / "MacOS" / "PublicDocumentApp"
    assert binary.is_file()
    return binary


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_benchmark_profile_is_frozen_and_executable() -> None:
    # Given: AC-09's versioned benchmark profile.
    profile_path = ROOT / "Resources" / "Performance" / "performance-profile-1.0.0.json"

    # When: the shipped profile is parsed.
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    # Then: every required fixture, format, and interaction threshold is immutable data.
    assert profile["profileVersion"] == "1.0.0"
    assert profile["requiredArchitecture"] == "arm64"
    assert profile["fixtures"] == {
        "100-page": {"minimumPageCount": 100, "elementCount": 2041},
        "50-mb": {
            "minimumSnapshotBytes": 50 * MIB,
            "minimumAuthoredUTF8Bytes": 50 * MIB,
            "elementChunkBytes": 2 * MIB,
        },
    }
    assert profile["formats"] == ["hwpx", "hwp", "docx", "markdown"]
    assert profile["thresholds"] == {
        "exportSeconds": 30.0,
        "mainThreadHeartbeatMilliseconds": 100.0,
        "firstProgressMilliseconds": 250.0,
        "progressGapMilliseconds": 5000.0,
        "cancellationRequestMilliseconds": 100.0,
        "cancellationCompletionMilliseconds": 1000.0,
    }


def test_recorded_apple_silicon_benchmarks_pass_all_thresholds(tmp_path: Path) -> None:
    # Given: separate 100-page and 50 MiB app-native fixtures on this recorded Mac.
    evidence_root = tmp_path / "performance"

    # When: the release executable exports both fixtures through every real adapter.
    result = subprocess.run(
        [str(_release_binary()), "--performance-self-test", str(evidence_root)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    receipt = json.loads(result.stdout)

    # Then: environment, fixture, artifact, validation, and timing evidence are bound.
    execution = receipt["executionIdentity"]
    assert execution["bundleIdentifier"] == "com.muni.public-document"
    assert execution["bundleExecutableRelativePath"] == "Contents/MacOS/PublicDocumentApp"
    assert execution["executableSHA256"] == _sha256(_release_binary())
    assert execution["genOfficeRuntimeManifestSHA256"].startswith("sha256:")
    assert execution["genOfficeBundleSHA256"].startswith("sha256:")
    assert execution["nodeExecutableSHA256"].startswith("sha256:")
    assert execution["rhwpExecutableSHA256"].startswith("sha256:")

    ui = receipt["uiObservation"]
    assert ui["status"] == "pass"
    assert ui["blockReason"] is None
    assert ui["observationSurface"] == "AppKit"
    assert ui["screenLocked"] is False
    assert ui["nsApplicationRunning"] is True
    assert ui["windowVisible"] is True
    assert ui["windowIsKey"] is True or ui["onScreenWindowCount"] > 0
    assert ui["progressIndicatorValueChangesOnMainThread"] > 0
    assert ui["progressLabelChangesOnMainThread"] > 0
    assert ui["cancelButtonActionInvocations"] == 1
    assert ui["cancelButtonActionPath"] == "NSButton.performClick"
    assert ui["cancelledManifestState"] == "cancelled"

    assert receipt["profileVersion"] == "1.0.0"
    assert receipt["environment"]["architecture"] == "arm64"
    hardware = subprocess.run(
        ["sysctl", "-n", "hw.optional.arm64"],
        check=True,
        capture_output=True,
        text=True,
    )
    architecture = subprocess.run(
        ["lipo", "-archs", str(_release_binary())],
        check=True,
        capture_output=True,
        text=True,
    )
    assert hardware.stdout.strip() == "1"
    assert architecture.stdout.strip() == "arm64"
    fixtures = {row["fixtureID"]: row for row in receipt["fixtures"]}
    assert fixtures["100-page"]["declaredPageCount"] == 100
    assert fixtures["50-mb"]["snapshotByteCount"] >= 50 * MIB
    assert fixtures["50-mb"]["authoredElementCount"] > 1
    assert fixtures["50-mb"]["authoredUTF8ByteCount"] >= 50 * MIB
    assert fixtures["50-mb"]["snapshotThresholdPassed"] is True
    assert fixtures["50-mb"]["authoredUTF8ThresholdPassed"] is True
    assert fixtures["100-page"]["snapshotHash"].startswith("sha256:")
    assert fixtures["50-mb"]["snapshotHash"].startswith("sha256:")
    assert fixtures["50-mb"]["authoredContentHash"].startswith("sha256:")

    observations = receipt["exportObservations"]
    assert len(observations) == 8
    assert {(row["fixtureID"], row["format"]) for row in observations} == {
        (fixture, document_format)
        for fixture in ("100-page", "50-mb")
        for document_format in ("hwpx", "hwp", "docx", "markdown")
    }
    assert all(row["durationSeconds"] <= 30.0 for row in observations)
    assert all(row["structuralValid"] and row["semanticValid"] for row in observations)
    assert all(row["artifactHash"].startswith("sha256:") for row in observations)
    assert all(row["snapshotHash"] == fixtures[row["fixtureID"]]["snapshotHash"] for row in observations)
    assert all(row["authoredContentValidated"] for row in observations)
    assert all(
        row["authoredUTF8ByteCount"] == fixtures[row["fixtureID"]]["authoredUTF8ByteCount"]
        for row in observations
    )
    assert all(
        row["authoredContentHash"] == fixtures[row["fixtureID"]]["authoredContentHash"]
        for row in observations
    )
    assert {
        row["format"]: row["authoredContentValidator"]
        for row in observations
        if row["fixtureID"] == "50-mb"
    } == {
        "hwpx": "rhwp-export-text",
        "hwp": "rhwp-export-text",
        "docx": "ooxml-word-document",
        "markdown": "commonmark-utf8",
    }
    assert all((evidence_root / row["artifactRelativePath"]).is_file() for row in observations)
    authored_artifacts = {
        row["format"]: row["artifactByteCount"]
        for row in observations
        if row["fixtureID"] == "50-mb"
    }
    assert authored_artifacts["docx"] >= 50 * MIB
    assert authored_artifacts["markdown"] >= 50 * MIB
    page_observations = {
        row["format"]: row["renderedPageCount"]
        for row in observations
        if row["fixtureID"] == "100-page" and row["format"] in {"hwpx", "hwp"}
    }
    assert page_observations == {"hwpx": 100, "hwp": 100}
    assert receipt["interactionObservation"]["responsive"] is True
    assert receipt["interactionObservation"]["progressPassed"] is True
    assert receipt["interactionObservation"]["cancellationPassed"] is True
    assert receipt["overallVerdict"] == "pass"
    assert (evidence_root / "performance-receipt.json").is_file()
