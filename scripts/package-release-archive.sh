#!/bin/sh
set -eu

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

sha256() {
    /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'
}

write_inventory() {
    inventory_root=$1
    inventory_destination=$2
    (
        cd "$inventory_root"
        /usr/bin/find PublicDocument.app Evidence -type f -print | LC_ALL=C /usr/bin/sort | while IFS= read -r artifact; do
            digest=$(sha256 "$artifact")
            printf '%s  %s\n' "$digest" "$artifact"
        done
    ) > "$inventory_destination"
}

write_artifact_rows() {
    artifact_root=$1
    rows_destination=$2
    /usr/bin/find "$artifact_root" -type f -print | LC_ALL=C /usr/bin/sort | while IFS= read -r artifact; do
        relative_path=${artifact#"$extracted_app/"}
        digest=$(sha256 "$artifact")
        /usr/bin/jq -nc --arg path "$relative_path" --arg sha256 "$digest" \
            '{path:$path,sha256:$sha256}'
    done | /usr/bin/jq -s '.' > "$rows_destination"
}

test "$#" -eq 2 || fail "usage: package-release-archive.sh <input-app> <output-zip>"

input_app=$1
requested_archive=$2
test -d "$input_app" || fail "input app does not exist: $input_app"
test ! -L "$input_app" || fail "input app must not be a symbolic link"
case "$(basename -- "$input_app")" in
    *.app) ;;
    *) fail "input must be a macOS .app bundle" ;;
esac

input_parent=$(CDPATH= cd -- "$(dirname -- "$input_app")" && pwd -P)
input_app="$input_parent/$(basename -- "$input_app")"
input_evidence="$input_parent/Evidence"
test -d "$input_evidence" || fail "release Evidence directory is missing next to the input app"
test ! -L "$input_evidence" || fail "release Evidence directory must not be a symbolic link"
archive_name=$(basename -- "$requested_archive")
case "$archive_name" in
    *.zip) archive_stem=${archive_name%.zip} ;;
    *) fail "output archive must use the .zip extension" ;;
esac

archive_parent=$(dirname -- "$requested_archive")
/bin/mkdir -p "$archive_parent"
archive_parent=$(CDPATH= cd -- "$archive_parent" && pwd -P)
archive="$archive_parent/$archive_name"
inventory="$archive_parent/$archive_stem.SHA256SUMS"
receipt="$archive_parent/$archive_stem.verification.json"
for output in "$archive" "$inventory" "$receipt"; do
    test ! -e "$output" && test ! -L "$output" || fail "release output already exists: $output"
done

staging_root=$(/usr/bin/mktemp -d /tmp/public-document-release-archive.XXXXXX)
verification_root=$(/usr/bin/mktemp -d /tmp/public-document-release-verify.XXXXXX)

cleanup() {
    for temporary_root in "$staging_root" "$verification_root"; do
        case "$temporary_root" in
            /tmp/public-document-release-archive.*|/tmp/public-document-release-verify.*)
                /bin/rm -rf -- "$temporary_root"
                ;;
            *)
                printf '%s\n' "refusing to clean unexpected path: $temporary_root" >&2
                ;;
        esac
    done
}
trap cleanup EXIT INT TERM

staged_app="$staging_root/PublicDocument.app"
staged_evidence="$staging_root/Evidence"
COPYFILE_DISABLE=1 /usr/bin/ditto --norsrc --noextattr --noqtn --noacl \
    "$input_app" "$staged_app"
COPYFILE_DISABLE=1 /usr/bin/ditto --norsrc --noextattr --noqtn --noacl \
    "$input_evidence" "$staged_evidence"
test -z "$(/usr/bin/find "$staged_evidence" -type l -print -quit)" || \
    fail "symbolic links are not permitted in the release Evidence tree"
test -f "$staged_evidence/release-manifest.json" || fail "release evidence manifest is missing"
test -f "$staged_evidence/SHA256SUMS" || fail "release evidence inventory is missing"
(
    cd "$staging_root"
    /usr/bin/shasum -a 256 -c Evidence/SHA256SUMS >/dev/null
) || fail "release evidence inventory does not match the input bundle"
/usr/bin/jq -e '
    (.criteria | length == 10)
    and ([.criteria[] | select(.criterion == "AC-07" or .criterion == "AC-10") | .verdict] | all(. == "blocked"))
    and ([.criteria[] | select(.criterion != "AC-07" and .criterion != "AC-10") | .verdict] | all(. == "pass"))
    and ([.criteria[].evidence] | all(startswith("Evidence/") and (contains("../") | not)))
' "$staged_evidence/release-manifest.json" >/dev/null || fail "release evidence manifest verdicts or paths are invalid"
/usr/bin/jq -r '.criteria[].evidence' "$staged_evidence/release-manifest.json" | while IFS= read -r evidence_path; do
    test -f "$staging_root/$evidence_path" || fail "release evidence manifest target is missing: $evidence_path"
done

required_directories='Capabilities Compatibility Engines GenOffice Legal Performance Provenance Studio Templates'
for resource in $required_directories; do
    test -d "$staged_app/Contents/Resources/$resource" || \
        fail "required packaged resource is missing: Contents/Resources/$resource"
done
for resource in \
    Contents/Info.plist \
    Contents/Resources/Engines/rhwp \
    Contents/Resources/Engines/node \
    Contents/Resources/GenOffice/runtime-manifest.json \
    Contents/Resources/GenOffice/public-document-genoffice.js \
    Contents/Resources/GenOffice/genoffice-docx-normalize.cjs \
    Contents/Resources/Legal/THIRD_PARTY_NOTICES.md \
    Contents/Resources/Provenance/genoffice-runtime-input-lock.json \
    Contents/Resources/Provenance/genoffice-node-runtime-lock.json \
    Contents/Resources/Provenance/upstream-lock.json \
    Contents/Resources/Provenance/sbom.spdx.json \
    Contents/Resources/Provenance/rhwp-dependency-lock.json; do
    test -f "$staged_app/$resource" || fail "required packaged file is missing: $resource"
done
test -z "$(/usr/bin/find "$staged_app" -type l -print -quit)" || \
    fail "symbolic links are not permitted in the canonical release app"

/usr/bin/plutil -lint "$staged_app/Contents/Info.plist" >/dev/null
executable_name=$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$staged_app/Contents/Info.plist")
case "$executable_name" in
    ''|*/*|.|..) fail "CFBundleExecutable must name one bundle-local executable" ;;
esac
staged_binary="$staged_app/Contents/MacOS/$executable_name"
test -x "$staged_binary" || fail "packaged executable is missing or not executable"
test "$(/usr/bin/lipo -archs "$staged_binary")" = "arm64" || \
    fail "packaged executable must contain only arm64"
/usr/bin/codesign --verify --deep --strict "$staged_app"

upstream_lock="$staged_app/Contents/Resources/Provenance/upstream-lock.json"
expected_rhwp_hash=$(/usr/bin/jq -er \
    '[.upstreams[] | select(.name == "rhwp")][0].local_patchset.bundled_arm64_binary_sha256' \
    "$upstream_lock")
actual_rhwp_hash=$(sha256 "$staged_app/Contents/Resources/Engines/rhwp")
test "$expected_rhwp_hash" = "sha256:$actual_rhwp_hash" || \
    fail "packaged rhwp does not match the approved upstream lock"
expected_dependency_hash=$(/usr/bin/jq -er \
    '[.upstreams[] | select(.name == "rhwp")][0].local_patchset.cargo_lock.dependency_inventory_sha256' \
    "$upstream_lock")
actual_dependency_hash=$(sha256 "$staged_app/Contents/Resources/Provenance/rhwp-dependency-lock.json")
test "$expected_dependency_hash" = "sha256:$actual_dependency_hash" || \
    fail "packaged rhwp dependency inventory does not match the approved upstream lock"

genoffice_manifest="$staged_app/Contents/Resources/GenOffice/runtime-manifest.json"
expected_runtime_manifest_hash=$(/usr/bin/jq -er '[.upstreams[] | select(.name == "genoffice")][0].local_patchset.runtime_manifest_sha256' "$upstream_lock")
test "$expected_runtime_manifest_hash" = "sha256:$(sha256 "$genoffice_manifest")" || \
    fail "GenOffice runtime manifest does not match the approved upstream lock"
port_manifest="$staged_app/Contents/Resources/Provenance/genoffice-docs-port.json"
expected_port_manifest_hash=$(/usr/bin/jq -er '[.upstreams[] | select(.name == "genoffice")][0].port_manifest_sha256' "$upstream_lock")
test "$expected_port_manifest_hash" = "sha256:$(sha256 "$port_manifest")" || \
    fail "GenOffice port manifest does not match the approved upstream lock"
test "$(/usr/bin/jq -er '.upstream.commit' "$genoffice_manifest")" = \
    "$(/usr/bin/jq -er '[.upstreams[] | select(.name == "genoffice")][0].commit' "$upstream_lock")" || \
    fail "GenOffice manifest commit does not match the approved upstream lock"
test "$(/usr/bin/jq -er '.upstream.license' "$genoffice_manifest")" = "Apache-2.0" || \
    fail "GenOffice manifest license is not approved"
input_lock_path="$staged_app/Contents/Resources/Provenance/genoffice-runtime-input-lock.json"
expected_input_lock_hash=$(/usr/bin/jq -er '.inputLock.sha256' "$genoffice_manifest")
test "$(sha256 "$input_lock_path")" = "$expected_input_lock_hash" || \
    fail "packaged GenOffice input lock does not match the runtime manifest"
node_lock_path="$staged_app/Contents/Resources/Provenance/genoffice-node-runtime-lock.json"
test "$(sha256 "$node_lock_path")" = "$(/usr/bin/jq -er '.node.lock.sha256' "$genoffice_manifest")" || \
    fail "packaged Node runtime lock does not match the runtime manifest"
expected_genoffice_node_hash=$(/usr/bin/jq -er '.node.sha256' "$genoffice_manifest")
actual_genoffice_node_hash=$(sha256 "$staged_app/Contents/Resources/Engines/node")
test "$expected_genoffice_node_hash" = "$actual_genoffice_node_hash" || \
    fail "packaged Node engine does not match the GenOffice runtime manifest"
test "$(/usr/bin/lipo -archs "$staged_app/Contents/Resources/Engines/node")" = "arm64" || \
    fail "packaged Node engine must contain only arm64"
/usr/bin/jq -cer '.outputs[]' "$genoffice_manifest" | while IFS= read -r expected_genoffice; do
    genoffice_path=$(/usr/bin/jq -r '.path' <<EOF
$expected_genoffice
EOF
)
    genoffice_hash=$(/usr/bin/jq -r '.sha256' <<EOF
$expected_genoffice
EOF
)
    case "$genoffice_path" in
        GenOffice/*|Legal/*) ;;
        *) fail "GenOffice manifest output escaped approved resource trees: $genoffice_path" ;;
    esac
    case "/$genoffice_path/" in *'/../'*|*'/./'*) fail "GenOffice manifest output is not normalized: $genoffice_path" ;; esac
    test -f "$staged_app/Contents/Resources/$genoffice_path" || \
        fail "GenOffice manifest output is missing: $genoffice_path"
    test "$(sha256 "$staged_app/Contents/Resources/$genoffice_path")" = "$genoffice_hash" || \
        fail "GenOffice manifest output hash mismatch: $genoffice_path"
    genoffice_size=$(/usr/bin/jq -r '.sizeBytes' <<EOF
$expected_genoffice
EOF
)
    test "$(/usr/bin/stat -f '%z' "$staged_app/Contents/Resources/$genoffice_path")" = "$genoffice_size" || \
        fail "GenOffice manifest output size mismatch: $genoffice_path"
done
for genoffice_runtime in public-document-genoffice.js genoffice-docx-normalize.cjs; do
    /usr/bin/grep -Eiq 'genspark|AiPanel|electron-updater|apps/(sheets|slides|pdf|shell|markdown)|packages/(ai-provider|ai-search|agent-core|pptx-engine|pptx-render|electron-utils)|fetch[[:space:]]*\(|WebSocket|XMLHttpRequest|sendBeacon|new[[:space:]]+Function|eval[[:space:]]*\(' \
        "$staged_app/Contents/Resources/GenOffice/$genoffice_runtime" && \
        fail "forbidden runtime surface found in GenOffice/$genoffice_runtime"
done
test -z "$(/usr/bin/otool -L -arch arm64 "$staged_app/Contents/Resources/Engines/node" | /usr/bin/awk 'NR>1 {print $1}' | /usr/bin/grep -Ev '^(/System/Library/|/usr/lib/)' || true)" || \
    fail "packaged Node engine links a non-system library"

TZ=UTC
export TZ
/usr/bin/find "$staged_app" "$staged_evidence" -type f -exec /usr/bin/touch -t 198001010000 {} +
/usr/bin/find -d "$staged_app" "$staged_evidence" -type d -exec /usr/bin/touch -t 198001010000 {} +
/usr/bin/touch -t 198001010000 "$staging_root"
/usr/bin/codesign --verify --deep --strict "$staged_app"

expected_inventory="$verification_root/expected.SHA256SUMS"
write_inventory "$staging_root" "$expected_inventory"
temporary_archive="$verification_root/$archive_name"
COPYFILE_DISABLE=1 /usr/bin/ditto -c -k --norsrc --noextattr --noqtn --noacl \
    "$staging_root" "$temporary_archive"

extracted_root="$verification_root/extracted"
/bin/mkdir "$extracted_root"
/usr/bin/ditto -x -k "$temporary_archive" "$extracted_root"
extracted_app="$extracted_root/PublicDocument.app"
extracted_evidence="$extracted_root/Evidence"
test -d "$extracted_app" || fail "archive did not reopen with PublicDocument.app at its root"
test -d "$extracted_evidence" || fail "archive did not reopen with Evidence at its root"
test -z "$(/usr/bin/find "$extracted_root" -path '*/__MACOSX' -print -quit)" || \
    fail "archive contains a resource-fork metadata directory"
for prohibited_attribute in com.apple.FinderInfo com.apple.ResourceFork; do
    if /usr/bin/xattr -p "$prohibited_attribute" "$extracted_app" >/dev/null 2>&1; then
        fail "archive restored prohibited metadata: $prohibited_attribute"
    fi
done
/usr/bin/codesign --verify --deep --strict "$extracted_app"
extracted_binary="$extracted_app/Contents/MacOS/$executable_name"
test "$(/usr/bin/lipo -archs "$extracted_binary")" = "arm64" || \
    fail "extracted executable must contain only arm64"
/usr/bin/plutil -lint "$extracted_app/Contents/Info.plist" >/dev/null

actual_inventory="$verification_root/SHA256SUMS"
write_inventory "$extracted_root" "$actual_inventory"
/usr/bin/cmp -s "$expected_inventory" "$actual_inventory" || \
    fail "archive extraction changed packaged file content"
(
    cd "$extracted_root"
    /usr/bin/shasum -a 256 -c "$actual_inventory" >/dev/null
)
(
    cd "$extracted_root"
    /usr/bin/shasum -a 256 -c Evidence/SHA256SUMS >/dev/null
) || fail "extracted internal Evidence inventory failed verification"

resource_rows="$verification_root/resource-trees.jsonl"
: > "$resource_rows"
for resource in $required_directories; do
    resource_inventory="$verification_root/resource-tree.inventory"
    /usr/bin/awk -v prefix="  PublicDocument.app/Contents/Resources/$resource/" \
        'index($0, prefix) > 0' "$actual_inventory" > "$resource_inventory"
    file_count=$(/usr/bin/wc -l < "$resource_inventory" | /usr/bin/tr -d ' ')
    test "$file_count" -gt 0 || fail "packaged resource tree is empty: $resource"
    tree_hash=$(sha256 "$resource_inventory")
    /usr/bin/jq -nc \
        --arg path "Contents/Resources/$resource" \
        --argjson fileCount "$file_count" \
        --arg sha256 "$tree_hash" \
        '{path:$path,fileCount:$fileCount,treeSha256:$sha256}' >> "$resource_rows"
done
/usr/bin/jq -s '.' "$resource_rows" > "$verification_root/resource-trees.json"
write_artifact_rows "$extracted_app/Contents/Resources/Provenance" \
    "$verification_root/provenance-artifacts.json"
write_artifact_rows "$extracted_app/Contents/Resources/Engines" \
    "$verification_root/engine-artifacts.json"

bundle_identifier=$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$extracted_app/Contents/Info.plist")
bundle_name=$(/usr/bin/plutil -extract CFBundleName raw -o - "$extracted_app/Contents/Info.plist")
short_version=$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$extracted_app/Contents/Info.plist")
bundle_version=$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$extracted_app/Contents/Info.plist")
archive_hash=$(sha256 "$temporary_archive")
archive_size=$(/usr/bin/stat -f '%z' "$temporary_archive")
inventory_hash=$(sha256 "$actual_inventory")
inventory_count=$(/usr/bin/wc -l < "$actual_inventory" | /usr/bin/tr -d ' ')
info_plist_hash=$(sha256 "$extracted_app/Contents/Info.plist")
executable_hash=$(sha256 "$extracted_binary")
temporary_receipt="$verification_root/verification.json"
/usr/bin/jq -n \
    --arg archiveFile "$archive_name" \
    --arg archiveSha256 "$archive_hash" \
    --argjson archiveSizeBytes "$archive_size" \
    --arg bundleIdentifier "$bundle_identifier" \
    --arg bundleName "$bundle_name" \
    --arg shortVersion "$short_version" \
    --arg bundleVersion "$bundle_version" \
    --arg executableName "$executable_name" \
    --arg executableSha256 "$executable_hash" \
    --arg infoPlistSha256 "$info_plist_hash" \
    --arg inventoryFile "$archive_stem.SHA256SUMS" \
    --arg inventorySha256 "$inventory_hash" \
    --argjson inventoryFileCount "$inventory_count" \
    --slurpfile resourceTrees "$verification_root/resource-trees.json" \
    --slurpfile provenanceArtifacts "$verification_root/provenance-artifacts.json" \
    --slurpfile engineArtifacts "$verification_root/engine-artifacts.json" \
    '{
        schemaVersion:2,
        archive:{file:$archiveFile,format:"zip",sha256:$archiveSha256,sizeBytes:$archiveSizeBytes},
        bundle:{sha256Inventory:{file:$inventoryFile,sha256:$inventorySha256,fileCount:$inventoryFileCount}},
        evidence:{root:"Evidence",manifestResolution:"pass",internalInventoryRecheck:"pass"},
        app:{
            bundleIdentifier:$bundleIdentifier,
            bundleName:$bundleName,
            shortVersion:$shortVersion,
            bundleVersion:$bundleVersion,
            architecture:"arm64",
            codesignVerification:"pass",
            infoPlist:{path:"Contents/Info.plist",sha256:$infoPlistSha256},
            executable:{path:("Contents/MacOS/" + $executableName),sha256:$executableSha256},
            sha256Inventory:{file:$inventoryFile,sha256:$inventorySha256,fileCount:$inventoryFileCount},
            resourceTrees:$resourceTrees[0],
            provenanceArtifacts:$provenanceArtifacts[0],
            engineArtifacts:$engineArtifacts[0]
        },
        verification:{
            freshTemporaryExtraction:true,
            archiveExtendedAttributes:"excluded",
            extractedInventoryComparison:"pass",
            sha256InventoryRecheck:"pass"
        }
    }' > "$temporary_receipt"

for output in "$archive" "$inventory" "$receipt"; do
    test ! -e "$output" && test ! -L "$output" || fail "release output appeared during verification: $output"
done
/bin/cp "$actual_inventory" "$inventory"
/bin/cp "$temporary_receipt" "$receipt"
/bin/mv "$temporary_archive" "$archive"
printf '%s\n%s\n%s\n' "$archive" "$inventory" "$receipt"
