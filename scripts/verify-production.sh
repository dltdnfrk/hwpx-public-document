#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mode=full
repeat_count=1

case "${1:-}" in
    --tamper-provenance-copy)
        mode=tamper
        evidence=${2:-}
        test "$#" -eq 2 || {
            printf '%s\n' "usage: verify-production.sh --tamper-provenance-copy <evidence-dir>" >&2
            exit 2
        }
        ;;
    --repeat)
        mode=repeat
        repeat_count=${2:-}
        evidence=${3:-}
        test "$#" -eq 3 || {
            printf '%s\n' "usage: verify-production.sh --repeat <count> <evidence-dir>" >&2
            exit 2
        }
        case "$repeat_count" in
            ''|*[!0-9]*|0|1) printf '%s\n' "repeat count must be at least 2" >&2; exit 2 ;;
        esac
        ;;
    *)
        evidence=${1:-}
        test "$#" -eq 1 || {
            printf '%s\n' "usage: verify-production.sh <evidence-dir>" >&2
            exit 2
        }
        ;;
esac

test -n "$evidence" || {
    printf '%s\n' "evidence directory is required" >&2
    exit 2
}
case "$evidence" in
    /*) ;;
    *) evidence="$root/$evidence" ;;
esac
PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m public_document_web.evidence_path "$evidence" >/dev/null
transcript="$evidence/transcript.txt"
exec >"$transcript" 2>&1

run() {
    printf '\n$'
    printf ' %s' "$@"
    printf '\n'
    "$@"
}

write_summary() {
    gate_kind=$1
    /usr/bin/python3 - "$evidence" "$gate_kind" <<'PY'
from pathlib import Path
import hashlib
import json
import sys
import zipfile

root = Path(sys.argv[1])
gate_kind = sys.argv[2]
packages = sorted(
    path for path in (root / "golden").rglob("*")
    if path.is_file() and path.suffix.lower() in {".docx", ".hwpx", ".hwp", ".md"}
)

def normalized_hash(path):
    if path.suffix.lower() in {".docx", ".hwpx"}:
        digest = hashlib.sha256()
        with zipfile.ZipFile(path) as package:
            for name in sorted(package.namelist()):
                digest.update(name.encode())
                digest.update(b"\0")
                digest.update(hashlib.sha256(package.read(name)).digest())
        return digest.hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()

repository = Path.cwd()
manifest_paths = [
    repository / "Resources/Studio/official-layout-profile.js",
    repository / "Resources/Capabilities/format-capabilities-1.0.0.json",
    repository / "provenance/genoffice-docs-port.json",
    repository / "provenance/upstream-lock.json",
]
summary = {
    "schemaVersion": 1,
    "status": "pass",
    "gates": ([
        "generated-provenance",
        "javascript-syntax",
        "genoffice-port",
        "swift-build",
        "full-pytest",
    ] if gate_kind == "full" else [
        "generated-provenance",
        "genoffice-port",
        "swift-build",
    ]) + [
        "layout-profile-parity",
        "roundtrip-matrix",
        "fireblight-docx",
    ],
    "normalizedManifestHashes": {
        str(path.relative_to(repository)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in manifest_paths
    },
    "normalizedArtifactHashes": {
        str(path.relative_to(root)): normalized_hash(path) for path in packages
    },
    "artifactCount": len(packages),
    "sourceIdentity": {
        "revision": __import__("subprocess").check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "headTree": __import__("subprocess").check_output(
            ["git", "rev-parse", "HEAD^{tree}"], text=True
        ).strip(),
        "worktreeSHA256": (
            (root / "before-worktree.sha256").read_text().strip()
            if (root / "before-worktree.sha256").is_file() else None
        ),
        "worktreeDirty": bool(
            (root / "before-status.txt").read_text()
            if (root / "before-status.txt").is_file() else ""
        ),
        "beforeStatusSHA256": hashlib.sha256(
            (root / "before-status.txt").read_bytes()
        ).hexdigest() if (root / "before-status.txt").is_file() else None,
        "afterStatusSHA256": hashlib.sha256(
            (root / "after-status.txt").read_bytes()
        ).hexdigest() if (root / "after-status.txt").is_file() else None,
        "beforeWorktreeSHA256": (
            (root / "before-worktree.sha256").read_text().strip()
            if (root / "before-worktree.sha256").is_file() else None
        ),
        "afterWorktreeSHA256": (
            (root / "after-worktree.sha256").read_text().strip()
            if (root / "after-worktree.sha256").is_file() else None
        ),
        "transcriptSHA256": hashlib.sha256(
            (root / "transcript.txt").read_bytes()
        ).hexdigest() if (root / "transcript.txt").is_file() else None,
    },
    "cleanup": "all invoked commands exited; no verifier temporary directory",
}
(root / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

golden_outputs() {
    mkdir -p "$evidence/golden"
    run python3 scripts/qa/layout-profile-parity.py \
        --project tests/fixtures/official-layout-rich.json \
        --outdir "$evidence/golden/layout-profile"
    run python3 scripts/qa/export-roundtrip-matrix.py \
        --fixture tests/fixtures/official-rich-project.json \
        --outdir "$evidence/golden/roundtrip"
    run python3 scripts/qa/fireblight-export-smoke.py \
        --format docx \
        --outdir "$evidence/golden/fireblight"
}

assert_repository_unchanged() {
    git status --porcelain=v1 --untracked-files=all >"$evidence/after-status.txt"
    python3 scripts/worktree-fingerprint.py "$root" >"$evidence/after-worktree.sha256"
    cmp -s "$evidence/before-status.txt" "$evidence/after-status.txt"
    cmp -s "$evidence/before-worktree.sha256" "$evidence/after-worktree.sha256"
}

full_gate() {
    git status --porcelain=v1 --untracked-files=all >"$evidence/before-status.txt"
    python3 scripts/worktree-fingerprint.py "$root" >"$evidence/before-worktree.sha256"
    run node scripts/update-local-provenance.mjs --check
    find Resources/Studio scripts -type f \( -name '*.js' -o -name '*.mjs' \) -print \
        | LC_ALL=C sort | while IFS= read -r file; do
            run node --check "$file"
        done
    run node scripts/verify-genoffice-port.mjs --manifest provenance/genoffice-docs-port.json
    run swift build --product PublicDocumentApp
    run python3 -m pytest -q --tb=short
    golden_outputs
    assert_repository_unchanged
    printf '%s\n' "cleanup: all invoked commands exited; no verifier temporary directory"
    write_summary full
}

golden_gate() {
    git status --porcelain=v1 --untracked-files=all >"$evidence/before-status.txt"
    python3 scripts/worktree-fingerprint.py "$root" >"$evidence/before-worktree.sha256"
    run node scripts/update-local-provenance.mjs --check
    run node scripts/verify-genoffice-port.mjs --manifest provenance/genoffice-docs-port.json
    run swift build --product PublicDocumentApp
    golden_outputs
    assert_repository_unchanged
    printf '%s\n' "cleanup: all invoked commands exited; no verifier temporary directory"
    write_summary golden
}

tamper_gate() {
    before="$evidence/before-status.txt"
    after="$evidence/after-status.txt"
    before_worktree="$evidence/before-worktree.sha256"
    after_worktree="$evidence/after-worktree.sha256"
    git status --porcelain=v1 --untracked-files=all >"$before"
    python3 scripts/worktree-fingerprint.py "$root" >"$before_worktree"
    temporary=$(mktemp -d "${TMPDIR:-/tmp}/public-document-provenance-copy.XXXXXX")
    cleanup_tamper() {
        if test -n "${temporary:-}" && test -d "$temporary"; then
            rm -rf "$temporary"
        fi
    }
    trap cleanup_tamper EXIT INT TERM
    /usr/bin/python3 - "$temporary" <<'PY'
from pathlib import Path
import json
import shutil
import sys

destination = Path(sys.argv[1])
manifest = json.loads(Path("provenance/genoffice-docs-port.json").read_text())
(destination / "provenance").mkdir(parents=True)
shutil.copy2(
    "provenance/genoffice-docs-port.json",
    destination / "provenance/genoffice-docs-port.json",
)
for artifact in manifest["localArtifacts"]:
    source = Path(artifact["path"])
    target = destination / source
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
PY
    run node scripts/verify-genoffice-port.mjs \
        --manifest "$temporary/provenance/genoffice-docs-port.json" \
        --local-root "$temporary"
    printf '\n// deliberate tamper\n' >>"$temporary/Resources/Studio/easy-tools.js"
    set +e
    node scripts/verify-genoffice-port.mjs \
        --manifest "$temporary/provenance/genoffice-docs-port.json" \
        --local-root "$temporary" >"$evidence/tamper-verifier.json" 2>&1
    tamper_status=$?
    set -e
    test "$tamper_status" -ne 0
    /usr/bin/python3 - "$evidence/tamper-verifier.json" <<'PY'
import json
import sys

receipt = json.load(open(sys.argv[1]))
assert "local port hash drift: Resources/Studio/easy-tools.js" in receipt["failures"]
PY
    rm -rf "$temporary"
    temporary=''
    git status --porcelain=v1 --untracked-files=all >"$after"
    python3 scripts/worktree-fingerprint.py "$root" >"$after_worktree"
    cmp -s "$before" "$after"
    cmp -s "$before_worktree" "$after_worktree"
    printf '%s\n' "cleanup: isolated provenance copy removed; verifier commands exited"
    /usr/bin/python3 - "$evidence" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1])
summary = {
    "schemaVersion": 1,
    "status": "pass",
    "tamperRejected": True,
    "repositoryUnchanged": (root / "before-status.txt").read_bytes()
        == (root / "after-status.txt").read_bytes()
        and (root / "before-worktree.sha256").read_bytes()
        == (root / "after-worktree.sha256").read_bytes(),
    "beforeWorktreeSHA256": (root / "before-worktree.sha256").read_text().strip(),
    "afterWorktreeSHA256": (root / "after-worktree.sha256").read_text().strip(),
    "transcriptSHA256": hashlib.sha256(
        (root / "transcript.txt").read_bytes()
    ).hexdigest(),
    "cleanup": "isolated provenance copy removed; verifier commands exited",
}
(root / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

repeat_gate() {
    index=1
    while test "$index" -le "$repeat_count"; do
        child="$evidence/run-$index"
        mkdir -p "$child"
        run "$root/scripts/verify-production.sh" "$child"
        index=$((index + 1))
    done
    printf '%s\n' "cleanup: all child gates exited; no verifier temporary directories"
    /usr/bin/python3 - "$evidence" "$repeat_count" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1])
count = int(sys.argv[2])
runs = [
    json.loads((root / f"run-{index}" / "summary.json").read_text())
    for index in range(1, count + 1)
]
manifest_equal = all(
    run["normalizedManifestHashes"] == runs[0]["normalizedManifestHashes"]
    for run in runs[1:]
)
artifact_equal = all(
    run["normalizedArtifactHashes"] == runs[0]["normalizedArtifactHashes"]
    for run in runs[1:]
)
assert all(run["status"] == "pass" for run in runs)
assert manifest_equal and artifact_equal
summary = {
    "schemaVersion": 1,
    "status": "pass",
    "repeatCount": count,
    "normalizedManifestsIdentical": manifest_equal,
    "normalizedArtifactHashesIdentical": artifact_equal,
    "normalizedManifestHashes": runs[0]["normalizedManifestHashes"],
    "normalizedArtifactHashes": runs[0]["normalizedArtifactHashes"],
    "transcriptSHA256": hashlib.sha256(
        (root / "transcript.txt").read_bytes()
    ).hexdigest(),
    "cleanup": "all child gates exited; no verifier temporary directories",
}
(root / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

cd "$root"
case "$mode" in
    full) full_gate ;;
    tamper) tamper_gate ;;
    repeat) repeat_gate ;;
esac
