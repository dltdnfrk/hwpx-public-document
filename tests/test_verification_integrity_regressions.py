from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

import pytest

from tests.external_stage2.loader import load

ROOT = Path(__file__).resolve().parents[1]


def module_at(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def audit_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    auditor = module_at("integrity_auditor", "scripts/qa/audit-ulw-evidence.py")
    repository = tmp_path / "repository"
    subprocess.run(["git", "clone", "--shared", "--no-checkout", "--single-branch", str(ROOT), str(repository)],
                   check=True, capture_output=True, timeout=30)
    for relative in (
        "scripts/worktree-fingerprint.py", "Resources/Studio/official-layout-profile.js",
        "Resources/Capabilities/format-capabilities-1.0.0.json",
        "provenance/genoffice-docs-port.json", "provenance/upstream-lock.json",
        "docs/maintenance-and-recovery.md", "docs/release-and-recovery.md",
    ):
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    brief = repository / "brief.txt"
    brief.write_text("fixture brief", encoding="utf-8")
    monkeypatch.setattr(auditor, "ROOT", repository)
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repository, text=True).strip()
    worktree = subprocess.check_output(
        [sys.executable, str(repository / "scripts/worktree-fingerprint.py"), str(repository)], text=True
    ).strip()
    identity = {"headTree": tree, "worktreeSHA256": worktree, "worktreeDirty": True}
    evidence = tmp_path / "evidence"
    inventory = "G002/a1/malformed/empty-output-inventory.json"
    transcript = "G002/a1/malformed/transcript.txt"
    refresh = "G007/a1/certified/final-verify/summary.json"
    write_json(evidence / inventory, {"packages": []})
    (evidence / transcript).write_text("$ fixture\nexit=2\n", encoding="utf-8")
    write_json(evidence / refresh, {
        "schemaVersion": 1, "status": "pass", "cleanup": "none", "gates": ["fixture"],
        "normalizedManifestHashes": {relative: auditor.sha256(repository / relative) for relative in (
            "Resources/Studio/official-layout-profile.js",
            "Resources/Capabilities/format-capabilities-1.0.0.json",
            "provenance/genoffice-docs-port.json", "provenance/upstream-lock.json",
        )},
        "normalizedArtifactHashes": {"fixture": "0" * 64}, "sourceIdentity": identity,
    })
    for scenario in ("app-happy", "app-invalid"):
        write_json(evidence / f"G007/a1/certified/{scenario}/action-log.json", {
            "forbiddenApplicationsSnapshot": {"unchanged": True},
            "export": {"publishedFormats": ["hwpx", "hwp", "docx", "markdown"]},
        })
    stamp = f"@tree:{tree[:7]} @worktree:{worktree}"
    goals = {"briefPath": str(brief), "goals": [{
        "id": "G002", "attempt": 1, "status": "complete", "successCriteria": [
            {"id": "C002", "status": "pass", "capturedEvidence": stamp},
        ],
    }]}
    events = [
        {"kind": "evidence_captured", "goalId": "G002", "criterionId": "C002",
         "capturedEvidence": stamp, "artifactHashes": {
             relative: auditor.sha256(evidence / relative) for relative in (inventory, transcript)
         }},
        {"kind": "evidence_captured", "goalId": "G007", "criterionId": "C001",
         "capturedEvidence": stamp, "artifactHashes": {refresh: auditor.sha256(evidence / refresh)}},
    ]
    args = argparse.Namespace(session="fixture", tree=tree[:7], out=tmp_path / "audit.json",
                              goals=tmp_path / "goals.json", ledger=tmp_path / "ledger.jsonl",
                              evidence_root=evidence, adversarial_ledger_copy=None)
    monkeypatch.setattr(auditor, "GOAL_IDS", ("G002",))
    monkeypatch.setattr(auditor, "REFRESH_ARTIFACTS", (refresh,))
    monkeypatch.setattr(auditor, "CLAUSE_MAPPINGS", ())
    monkeypatch.setattr(auditor, "parse_args", lambda: args)
    return auditor, args, goals, events, inventory, refresh


@pytest.mark.parametrize("mutation", ["none", "tree", "worktree", "missing-hash", "artifact", "refresh", "summary-tree"])
def test_auditor_requires_actual_source_and_previously_captured_bytes(audit_case, mutation: str) -> None:
    # Given: valid evidence with independently captured input identities.
    auditor, args, goals, events, inventory, refresh = audit_case
    if mutation == "tree":
        old = args.tree
        args.tree = "deadbeef"
        for event in events:
            event["capturedEvidence"] = event["capturedEvidence"].replace(old, args.tree)
        goals["goals"][0]["successCriteria"][0]["capturedEvidence"] = events[0]["capturedEvidence"]
    elif mutation == "worktree":
        for event in events:
            event["capturedEvidence"] = event["capturedEvidence"].split(" @worktree:")[0] + " @worktree:" + "0" * 64
        goals["goals"][0]["successCriteria"][0]["capturedEvidence"] = events[0]["capturedEvidence"]
    elif mutation == "missing-hash":
        events[0].pop("artifactHashes")
    elif mutation == "artifact":
        write_json(args.evidence_root / inventory, {"packages": ["injected.hwpx"]})
    elif mutation in ("refresh", "summary-tree"):
        path = args.evidence_root / refresh
        summary = auditor.load_json(path)
        if mutation == "refresh":
            summary["gates"] = ["changed-after-capture"]
        else:
            summary["sourceIdentity"]["headTree"] = "0" * 40
            # Isolate the source binding, rather than merely the artifact digest.
        write_json(path, summary)
        if mutation == "summary-tree":
            events[1]["artifactHashes"][refresh] = auditor.sha256(path)
    write_json(args.goals, goals)
    args.ledger.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    # When: the real auditor entrypoint reads the supplied files.
    code = auditor.main()
    # Then: only unchanged, explicitly captured evidence passes.
    report = auditor.load_json(args.out)
    assert code == (0 if mutation == "none" else 1), report
    assert report["status"] == ("pass" if mutation == "none" else "fail")


@pytest.fixture
def retained_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Worker runs retain scratch files; production TemporaryDirectory policy is unchanged.
    @contextmanager
    def retained_directory(*, prefix: str, dir=None):
        yield tempfile.mkdtemp(prefix=prefix, dir=dir or tmp_path)
    monkeypatch.setattr(tempfile, "TemporaryDirectory", retained_directory)


def test_failed_final_manifest_copy_cannot_look_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, retained_staging) -> None:
    # Given: the real ditto command succeeds in copying bytes, then reports an I/O failure.
    assembly = load("external_stage2.package_assembly")
    integrity = load("external_stage2.copy_integrity")
    source = tmp_path / "source"
    source.mkdir()
    (source / "document.hwpx").write_bytes(b"candidate")
    destination = tmp_path / "assembled"
    real_run = subprocess.run
    calls = 0

    def fail_final_copy(arguments, **kwargs):
        nonlocal calls
        result = real_run(arguments, **kwargs)
        calls += 1
        if calls == 4:
            return subprocess.CompletedProcess(arguments, 1, result.stdout, "injected I/O failure")
        return result

    monkeypatch.setattr(assembly.subprocess, "run", fail_final_copy)
    # When: assembly fails at the final manifest copy.
    with pytest.raises((OSError, assembly.DuplicatePackageWriteError)) as failure:
        assembly.assemble_package_copies(source, b'{"fixture":true}', destination)
    # Then: the public copy gate cannot accept the leftover pair, and retry cannot overwrite it.
    decision = integrity.verify_copy_integrity(integrity.CopyIntegrityInputs(
        destination / "package-copy", destination / "package-copy-secondary",
        destination / "manifest.json", destination / "manifest-secondary.json",
    ))
    assert decision.integrity_pass is False
    assert decision.reason_codes == ("INTEGRITY_COPY_MISSING",)
    assert isinstance(failure.value, OSError)
    before = {p.relative_to(destination): p.read_bytes() for p in destination.rglob("*") if p.is_file()}
    with pytest.raises(assembly.DuplicatePackageWriteError):
        assembly.assemble_package_copies(source, b"replacement", destination)
    assert before == {p.relative_to(destination): p.read_bytes() for p in destination.rglob("*") if p.is_file()}


def test_secondary_collision_is_detected_before_primary_publication(tmp_path: Path, retained_staging) -> None:
    # Given: a protected secondary destination but no primary output.
    assembly = load("external_stage2.package_assembly")
    source = tmp_path / "source"
    source.mkdir()
    (source / "document.hwpx").write_bytes(b"candidate")
    destination = tmp_path / "assembled"
    destination.mkdir()
    sentinel = destination / "manifest-secondary.json"
    sentinel.write_bytes(b"protected")
    # When: duplicate publication is attempted.
    with pytest.raises(assembly.DuplicatePackageWriteError):
        assembly.assemble_package_copies(source, b"replacement", destination)
    # Then: refusal is non-mutating, including the primary paths.
    assert list(destination.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"protected"


def test_studio_stdout_keeps_draining_after_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a real child that writes more than a pipe can hold only after launch returns.
    qa = module_at("integrity_macos_qa", "scripts/qa/macos-app-qa.py")
    child = tmp_path / "studio-fixture"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(10)
        child.write_text(f'''#!{sys.executable}
import os, selectors, socket, sys
with socket.create_connection({listener.getsockname()!r}, timeout=10) as control:
    os.write(1, b'PUBLIC_DOCUMENT_STUDIO_QA_READY {{"event":"opened"}}\\n')
    assert control.recv(1) == b'G'
    os.set_blocking(1, False)
    payload = memoryview(b'x' * (2 * 1024 * 1024) + b'\\nDRAINED\\n')
    with selectors.DefaultSelector() as selector:
        selector.register(1, selectors.EVENT_WRITE)
        while payload:
            if not selector.select(5):
                sys.exit(23)
            try:
                payload = payload[os.write(1, payload):]
            except BlockingIOError:
                continue
    control.sendall(b'D')
''', encoding="utf-8")
        child.chmod(0o755)
        monkeypatch.setattr(qa, "app_binary", lambda: child)
        transcript = qa.Transcript(tmp_path / "transcript.txt")
        try:
            launched = qa.launch_studio("happy", tmp_path, tmp_path, tmp_path, transcript)
            process, ready = launched[:2]
            with listener.accept()[0] as control:
                control.settimeout(10)
                # When: the post-readiness writer is released through an exact event.
                control.sendall(b"G")
                completed = control.recv(1)
            code = process.wait(timeout=10)
            if len(launched) == 3:
                launched[2].finish()
            elif process.stdout is not None:
                process.stdout.close()
            # Then: no backpressure deadlock and all output reaches the transcript.
            assert completed == b"D" and code == 0
            assert ready == {"event": "opened"}
            assert (tmp_path / "app-stdout.txt").read_bytes().endswith(b"\nDRAINED\n")
        finally:
            transcript.close()


def test_declared_environment_runs_receipt_cli_without_import_failure(tmp_path: Path) -> None:
    # Given: the project interpreter and an explicitly missing receipt.
    missing = str(tmp_path / "missing")
    # When: the public verifier CLI processes it (not merely --help).
    result = subprocess.run([
        sys.executable, str(ROOT / "scripts/external-stage2/verify_receipt.py"),
        "--receipt", missing, "--trust-policy", missing, "--trust-policy-sha256", "0" * 64,
        "--request", missing, "--result", missing, "--manifest", missing,
        "--artifact-root", missing, "--execution-id", "regression",
    ], capture_output=True, text=True, timeout=30)
    # Then: the declared dependency environment produces a structured rejection.
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)["semantic_pass"] is False
    assert result.stderr == ""
