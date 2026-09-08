#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Thread
from typing import Any, IO

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from public_document_web.evidence_path import create_evidence_directory


APP_PARENT = ROOT / ".build" / "macos-app-qa"
APP = APP_PARENT / "PublicDocument.app"
READY_PREFIX = "PUBLIC_DOCUMENT_STUDIO_QA_READY "
FORMATS = ("hwpx", "hwp", "docx", "markdown")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drive the workspace-contained macOS Studio and capture QA evidence."
    )
    parser.add_argument("--build", action="store_true")
    parser.add_argument(
        "--scenario",
        required=True,
        choices=("happy", "invalid-project"),
    )
    parser.add_argument("--evidence-dir", required=True, type=Path)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_snapshot(root: Path) -> dict[str, Any]:
    if not root.exists() and not root.is_symlink():
        return {"exists": False, "sha256": None, "entryCount": 0}
    digest = hashlib.sha256()
    entries = [root, *sorted(root.rglob("*"))] if root.is_dir() else [root]
    for path in entries:
        metadata = path.lstat()
        relative = "." if path == root else str(path.relative_to(root))
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(
            f"{metadata.st_mode}:{metadata.st_size}:{metadata.st_mtime_ns}".encode()
        )
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(os.readlink(path).encode())
        elif path.is_file():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
    xattrs = subprocess.run(
        ["/usr/bin/xattr", "-lr", str(root)],
        capture_output=True,
        timeout=120,
    )
    if xattrs.returncode != 0:
        raise RuntimeError(f"could not inventory extended attributes: {root}")
    digest.update(xattrs.stdout)
    return {
        "exists": True,
        "sha256": digest.hexdigest(),
        "entryCount": len(entries),
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class Transcript:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.stream = path.open("w", encoding="utf-8")

    def close(self) -> None:
        self.stream.close()

    def command(self, arguments: list[str]) -> None:
        self.stream.write("\n$ " + " ".join(arguments) + "\n")
        self.stream.flush()

    def output(self, value: str) -> None:
        self.stream.write(value)
        if value and not value.endswith("\n"):
            self.stream.write("\n")
        self.stream.flush()


def run(
    arguments: list[str],
    transcript: Transcript,
    *,
    environment: dict[str, str] | None = None,
    timeout: int = 300,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    transcript.command(arguments)
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    transcript.output(result.stdout)
    transcript.output(result.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command exited {result.returncode}: {' '.join(arguments)}"
        )
    return result


def app_binary() -> Path:
    return APP.resolve() / "Contents" / "MacOS" / "PublicDocumentApp"


def assert_workspace_app() -> None:
    current = APP
    while current != ROOT:
        if current.is_symlink():
            raise RuntimeError(f"QA app path contains a symbolic link: {current}")
        current = current.parent
    resolved = APP.resolve()
    workspace = ROOT.resolve()
    applications = (Path.home() / "Applications").resolve()
    if workspace not in resolved.parents:
        raise RuntimeError(f"QA app escaped the workspace: {resolved}")
    if resolved == applications or applications in resolved.parents:
        raise RuntimeError(f"QA app entered the user Applications directory: {resolved}")
    if not app_binary().is_file():
        raise RuntimeError("workspace QA app is missing; run the happy scenario with --build")


def build_app(transcript: Transcript) -> None:
    APP_PARENT.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PUBLIC_DOCUMENT_PACKAGE_PARENT"] = str(APP_PARENT)
    run(
        [str(ROOT / "scripts" / "package-macos-app.sh"), str(APP)],
        transcript,
        environment=environment,
        timeout=600,
    )
    assert_workspace_app()


class StudioOutput:
    """Own stdout until EOF, not merely until the first ready event."""

    def __init__(self, stdout: IO[str], path: Path) -> None:
        self.ready: Future[dict[str, Any]] = Future()
        self.error: Exception | None = None
        self.thread = Thread(target=self._drain, args=(stdout, path), daemon=True)
        self.thread.start()

    def _drain(self, stdout: IO[str], path: Path) -> None:
        try:
            with stdout, path.open("w", encoding="utf-8") as app_stdout:
                for line in stdout:
                    app_stdout.write(line)
                    app_stdout.flush()
                    if not self.ready.done() and line.startswith(READY_PREFIX):
                        value = json.loads(line[len(READY_PREFIX) :])
                        if not isinstance(value, dict):
                            raise RuntimeError("native Studio ready event is not an object")
                        self.ready.set_result(value)
            if not self.ready.done():
                raise RuntimeError("Studio stdout closed before readiness")
        except (OSError, ValueError, RuntimeError) as error:
            self.error = error
            if not self.ready.done():
                self.ready.set_exception(error)

    def finish(self) -> None:
        self.thread.join(timeout=10)
        if self.thread.is_alive():
            raise RuntimeError("Studio stdout did not close after process exit")
        if self.error is not None:
            raise self.error


def wait_for_ready(output: StudioOutput, *, timeout: float = 45.0) -> dict[str, Any]:
    try:
        return output.ready.result(timeout=timeout)
    except FutureTimeoutError as error:
        raise RuntimeError("timed out waiting for the native Studio ready event") from error


def terminate_app(process: subprocess.Popen[str], output: StudioOutput) -> dict[str, Any]:
    try:
        if process.poll() is not None:
            return {"status": "already-exited", "returnCode": process.returncode}
        os.killpg(process.pid, signal.SIGTERM)
        try:
            return {"status": "terminated", "returnCode": process.wait(timeout=10)}
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            return {"status": "killed-after-timeout", "returnCode": process.wait(timeout=10)}
    finally:
        output.finish()


def launch_studio(
    scenario: str,
    project_root: Path,
    catalog_root: Path,
    evidence: Path,
    transcript: Transcript,
) -> tuple[subprocess.Popen[str], dict[str, Any], StudioOutput]:
    environment = os.environ.copy()
    environment.update(
        {
            "PUBLIC_DOCUMENT_STUDIO_PROJECT_ROOT": str(project_root),
            "PUBLIC_DOCUMENT_STUDIO_CATALOG_ROOT": str(catalog_root),
            "PUBLIC_DOCUMENT_STUDIO_AI_SETTINGS_ROOT": str(
                evidence / "runtime" / "ai-settings"
            ),
            "PUBLIC_DOCUMENT_STUDIO_QA_SCENARIO": scenario,
        }
    )
    arguments = [str(app_binary())]
    transcript.command(arguments)
    with (evidence / "app-stderr.txt").open("w", encoding="utf-8") as stderr_stream:
        process = subprocess.Popen(
            arguments,
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=stderr_stream,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    assert process.stdout is not None
    output = StudioOutput(process.stdout, evidence / "app-stdout.txt")
    try:
        ready = wait_for_ready(output)
    except Exception:
        terminate_app(process, output)
        raise
    return process, ready, output


def capture_window(ready: dict[str, Any], evidence: Path, transcript: Transcript) -> Path:
    window_number = ready.get("windowNumber")
    if not isinstance(window_number, int) or window_number <= 0:
        raise RuntimeError(f"invalid native window number: {window_number!r}")
    screenshot = evidence / "screenshot.png"
    run(
        [
            "/usr/sbin/screencapture",
            "-x",
            "-o",
            "-l",
            str(window_number),
            str(screenshot),
        ],
        transcript,
        timeout=30,
    )
    if not screenshot.is_file() or screenshot.stat().st_size == 0:
        raise RuntimeError("native window screenshot was not captured")
    return screenshot


def capture_native_accessibility_tree(
    process: subprocess.Popen[str],
    evidence: Path,
    transcript: Transcript,
) -> dict[str, Any]:
    result = run(
        [
            "swift",
            str(ROOT / "scripts/qa/native-accessibility-snapshot.swift"),
            str(process.pid),
        ],
        transcript,
        timeout=60,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("packaged app accessibility tree is unavailable")
    tree = evidence / "native-accessibility-tree.txt"
    tree.write_text(result.stdout, encoding="utf-8")
    rows = [line for line in result.stdout.splitlines() if line.strip()]
    roles = {
        fields[1]
        for line in rows
        if len(fields := line.split("\t")) > 1
    }
    return {
        "path": tree.name,
        "sha256": sha256(tree),
        "elementCount": len(rows),
        "windowContentAvailable": "AXWindow" in roles,
        "roles": sorted(roles),
    }


def inspect_exports(export_root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    published = receipt.get("publishedFormats")
    if published != list(FORMATS):
        raise RuntimeError(f"declared formats were not all published: {published!r}")
    if receipt.get("blockedFormats") or receipt.get("failedFormats"):
        raise RuntimeError("representative export reported blocked or failed formats")
    if not all(
        row.get("structuralValid") is True
        and row.get("semanticValid") is True
        and row.get("validation", {}).get("evidenceSource") == "artifact-derived"
        and row.get("validation", {}).get("orderedElements")
        for row in receipt.get("results", [])
    ):
        raise RuntimeError("representative export lacks artifact-derived semantic validation")
    artifacts = {row["format"]: export_root / row["fileName"] for row in receipt["results"]}
    if set(artifacts) != set(FORMATS) or not all(path.is_file() for path in artifacts.values()):
        raise RuntimeError("representative export artifacts are incomplete")
    signatures = {
        "hwpx": artifacts["hwpx"].read_bytes()[:4].hex(),
        "hwp": artifacts["hwp"].read_bytes()[:8].hex(),
        "docx": artifacts["docx"].read_bytes()[:4].hex(),
        "markdown": artifacts["markdown"].read_text(encoding="utf-8")[:1],
    }
    if signatures["hwpx"] != "504b0304" or signatures["docx"] != "504b0304":
        raise RuntimeError("ZIP package signature check failed")
    if signatures["hwp"] != "d0cf11e0a1b11ae1":
        raise RuntimeError("HWP compound-file signature check failed")
    if not signatures["markdown"]:
        raise RuntimeError("Markdown artifact is empty")
    return {
        "status": "pass",
        "publishedFormats": published,
        "signatures": signatures,
        "artifacts": {
            name: {
                "path": str(path.relative_to(export_root)),
                "sha256": sha256(path),
                "sizeBytes": path.stat().st_size,
            }
            for name, path in artifacts.items()
        },
    }


def happy(evidence: Path, transcript: Transcript) -> dict[str, Any]:
    runtime = evidence / "runtime"
    project_root = runtime / "project"
    catalog_root = runtime / "catalog"
    project_root.mkdir(parents=True)
    fixture = ROOT / "tests" / "fixtures" / "official-layout-rich.json"
    (project_root / "project.json").write_bytes(fixture.read_bytes())

    process, ready, output = launch_studio(
        "happy", project_root, catalog_root, evidence, transcript
    )
    cleanup: dict[str, Any]
    try:
        surface = ready.get("surface", {})
        if (
            ready.get("event") != "opened"
            or ready.get("windowTitle") != "문서작성기"
            or ready.get("windowVisible") is not True
            or surface.get("projectTitle") != "공식 조판 프로필 검증"
            or surface.get("editorPresent") is not True
            or surface.get("exportControlPresent") is not True
        ):
            raise RuntimeError(f"Studio did not render the representative project: {ready}")
        screenshot = capture_window(ready, evidence, transcript)
        accessibility = capture_native_accessibility_tree(process, evidence, transcript)
        export_root = evidence / "export"
        export_result = run(
            [
                str(app_binary()),
                "--export-project",
                str(fixture),
                str(export_root),
                "--formats",
                ",".join(FORMATS),
                "--flattening-consent",
            ],
            transcript,
            timeout=180,
        )
        export_receipt = json.loads(export_result.stdout)
        write_json(evidence / "receipt.json", export_receipt)
        package_inspection = inspect_exports(export_root, export_receipt)
        write_json(evidence / "package-inspection.json", package_inspection)
        batch_result = run(
            [
                str(app_binary()),
                "--batch-export-self-test",
                str(evidence / "batch"),
                "partial-failure",
            ],
            transcript,
            timeout=120,
        )
        batch_receipt = json.loads(batch_result.stdout)
        write_json(evidence / "batch-receipt.json", batch_receipt)
        cleanup = terminate_app(process, output)
        return {
            "schemaVersion": 1,
            "scenario": "happy",
            "status": "pass",
            "appPath": str(APP),
            "workspaceContained": True,
            "studioReady": ready,
            "screenshot": {
                "path": screenshot.name,
                "sha256": sha256(screenshot),
                "sizeBytes": screenshot.stat().st_size,
            },
            "nativeAccessibility": accessibility,
            "export": package_inspection,
            "batchState": batch_receipt["state"],
            "processCleanup": cleanup,
            "postLaunchMetadataPolicy": "canonical archive strips xattrs and re-verifies codesign",
        }
    finally:
        terminate_app(process, output)


def invalid_project(evidence: Path, transcript: Transcript) -> dict[str, Any]:
    runtime = evidence / "runtime"
    project_root = runtime / "project"
    catalog_root = runtime / "catalog"
    project_root.mkdir(parents=True)
    malformed = project_root / "project.json"
    malformed.write_text('{"schemaVersion":1,"title":', encoding="utf-8")
    destination = evidence / "destination"
    destination.mkdir()
    sentinel = destination / "existing.docx"
    sentinel.write_bytes(b"user-owned-existing-file")
    before = sha256(sentinel)
    destination_before = tree_snapshot(destination)

    process, ready, output = launch_studio(
        "invalid-project", project_root, catalog_root, evidence, transcript
    )
    cleanup: dict[str, Any]
    try:
        diagnostic = ready.get("diagnostic")
        body_text = ready.get("surface", {}).get("bodyText", "")
        if (
            ready.get("event") != "error"
            or not isinstance(diagnostic, str)
            or not diagnostic
            or diagnostic not in body_text
        ):
            raise RuntimeError(f"GUI did not display the malformed-project diagnostic: {ready}")
        screenshot = capture_window(ready, evidence, transcript)
        export_result = run(
            [
                str(app_binary()),
                "--export-project",
                str(malformed),
                str(destination),
                "--formats",
                ",".join(FORMATS),
                "--flattening-consent",
            ],
            transcript,
            timeout=30,
            check=False,
        )
        if export_result.returncode == 0:
            raise RuntimeError("malformed project unexpectedly exported")
        after = sha256(sentinel)
        destination_after = tree_snapshot(destination)
        packages = [
            path.name
            for path in destination.iterdir()
            if path != sentinel and path.is_file()
        ]
        if before != after or destination_before != destination_after or packages:
            raise RuntimeError("malformed project changed the protected destination")
        write_json(
            evidence / "destination-hash-diff.json",
            {
                "before": before,
                "after": after,
                "unchanged": before == after,
                "publishedFiles": packages,
                "destinationSnapshotBefore": destination_before,
                "destinationSnapshotAfter": destination_after,
            },
        )
        cleanup = terminate_app(process, output)
        return {
            "schemaVersion": 1,
            "scenario": "invalid-project",
            "status": "pass",
            "appPath": str(APP),
            "workspaceContained": True,
            "studioReady": ready,
            "diagnostic": diagnostic,
            "screenshot": {
                "path": screenshot.name,
                "sha256": sha256(screenshot),
                "sizeBytes": screenshot.stat().st_size,
            },
            "destinationUnchanged": before == after,
            "destinationTreeUnchanged": destination_before == destination_after,
            "publishedFiles": packages,
            "processCleanup": cleanup,
            "postLaunchMetadataPolicy": "canonical archive strips xattrs and re-verifies codesign",
        }
    finally:
        terminate_app(process, output)


def main() -> int:
    arguments = parse_args()
    evidence = arguments.evidence_dir
    if not evidence.is_absolute():
        evidence = ROOT / evidence
    try:
        evidence = create_evidence_directory(evidence)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    transcript = Transcript(evidence / "transcript.txt")
    forbidden_app = Path.home() / "Applications" / "PublicDocument.app"
    forbidden_before = tree_snapshot(forbidden_app)
    try:
        if arguments.build:
            build_app(transcript)
        assert_workspace_app()
        result = (
            happy(evidence, transcript)
            if arguments.scenario == "happy"
            else invalid_project(evidence, transcript)
        )
        forbidden_after = tree_snapshot(forbidden_app)
        if forbidden_after != forbidden_before:
            raise RuntimeError("~/Applications/PublicDocument.app changed during QA")
        result["forbiddenApplicationsPath"] = str(forbidden_app)
        result["forbiddenApplicationsSnapshot"] = {
            "before": forbidden_before,
            "after": forbidden_after,
            "unchanged": True,
        }
        write_json(evidence / "action-log.json", result)
        write_json(
            evidence / "summary.json",
            {
                "schemaVersion": 1,
                "status": "pass",
                "scenario": arguments.scenario,
                "workspaceApp": str(APP),
                "cleanup": "Studio process terminated; no QA temporary directory",
            },
        )
        return 0
    except Exception as error:
        transcript.output(f"ERROR: {error}")
        write_json(
            evidence / "summary.json",
            {
                "schemaVersion": 1,
                "status": "fail",
                "scenario": arguments.scenario,
                "error": str(error),
            },
        )
        print(str(error), file=sys.stderr)
        return 1
    finally:
        transcript.close()


if __name__ == "__main__":
    raise SystemExit(main())
