#!/bin/sh
set -eu

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

sha256() {
    /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'
}

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
requested_destination=${1:-"$root/dist/PublicDocumentStudio-Functional-0.1.0"}
requested_source_map=${2:-"$root/provenance/seed-evidence-sources.json"}
test "$#" -le 2 || fail "usage: build-ac10-functional-release.sh [destination] [source-map]"

case "$requested_destination" in
    /*) destination=$requested_destination ;;
    *) destination="$root/$requested_destination" ;;
esac
case "$requested_source_map" in
    /*) source_map=$requested_source_map ;;
    *) source_map="$root/$requested_source_map" ;;
esac

test ! -e "$destination" && test ! -L "$destination" || \
    fail "release destination already exists: $destination"
test -f "$source_map" || fail "evidence source map does not exist: $source_map"
test ! -L "$source_map" || fail "evidence source map must not be a symbolic link"

destination_parent=$(dirname -- "$destination")
mkdir -p "$destination_parent"
destination_parent=$(CDPATH= cd -- "$destination_parent" && pwd -P)
destination="$destination_parent/$(basename -- "$destination")"
staging_root=$(mktemp -d /tmp/public-document-ac10-functional.XXXXXX)
bundle="$staging_root/bundle"

cleanup() {
    case "$staging_root" in
        /tmp/public-document-ac10-functional.*) rm -rf -- "$staging_root" ;;
        *) printf '%s\n' "refusing to clean unexpected path: $staging_root" >&2 ;;
    esac
}
trap cleanup EXIT INT TERM

source_paths="$staging_root/evidence-source-paths.txt"
/usr/bin/jq -e '
    . as $root
    | .schemaVersion == 1
      and (.criteria | type == "object")
      and (["AC-01","AC-02","AC-03","AC-04","AC-05","AC-06","AC-07","AC-08","AC-09"]
        | all(. as $criterion | ($root.criteria[$criterion] | type == "object")))
      and (["AC-01","AC-02","AC-03","AC-04","AC-05","AC-06","AC-07","AC-08","AC-09"]
        | all(. as $criterion | ([$root.criteria[$criterion] | .. | scalars]
          | all(type == "string"))))
      and (["AC-01","AC-02","AC-03","AC-04","AC-05","AC-06","AC-07","AC-08","AC-09"]
        | all(. as $criterion | ([$root.criteria[$criterion] | .. | strings
          | select(test("[\\r\\n]"))] | length == 0)))
' "$source_map" >/dev/null || fail "evidence source map does not match schema version 1"
/usr/bin/jq -r '
    .criteria as $criteria
    | ["AC-01","AC-02","AC-03","AC-04","AC-05","AC-06","AC-07","AC-08","AC-09"][] as $criterion
    | $criteria[$criterion]
    | ..
    | strings
' "$source_map" | LC_ALL=C /usr/bin/sort -u > "$source_paths"
test -s "$source_paths" || fail "evidence source map declares no source paths"

while IFS= read -r evidence_path; do
    case "$evidence_path" in
        ''|/*) fail "evidence source paths must be non-empty and project-relative: $evidence_path" ;;
    esac
    case "/$evidence_path/" in
        *'/../'*|*'/./'*|*'//') fail "evidence source path contains an unsafe segment: $evidence_path" ;;
    esac
    candidate="$root/$evidence_path"
    test -e "$candidate" || fail "declared evidence source does not exist: $evidence_path"
    test ! -L "$candidate" || fail "declared evidence source must not be a symbolic link: $evidence_path"
    resolved_path=$(/bin/realpath "$candidate")
    case "$resolved_path" in
        "$root"/*) ;;
        *) fail "declared evidence source escapes the project root: $evidence_path" ;;
    esac
    if test -d "$candidate"; then
        test -z "$(/usr/bin/find "$candidate" -type l -print -quit)" || \
            fail "declared evidence directory contains a symbolic link: $evidence_path"
    elif test ! -f "$candidate"; then
        fail "declared evidence source must be a regular file or directory: $evidence_path"
    fi
done < "$source_paths"

mkdir -p "$bundle/Evidence/CanonicalSources" \
    "$bundle/Evidence/AcceptanceCriteria" \
    "$bundle/Evidence/Provenance" \
    "$bundle/Evidence/Runtime/ac-10-packaged-app"

PUBLIC_DOCUMENT_PACKAGE_PARENT="$bundle" \
    "$root/scripts/package-macos-app.sh" "$bundle/PublicDocument.app" >/dev/null

cp "$root/provenance/upstream-lock.json" "$bundle/Evidence/Provenance/"
cp "$root/provenance/sbom.spdx.json" "$bundle/Evidence/Provenance/"
cp "$root/provenance/genoffice-docs-port.json" "$bundle/Evidence/Provenance/"
cp "$root/provenance/rhwp-dependency-lock.json" "$bundle/Evidence/Provenance/"
cp "$root/Resources/Release/release-manifest-1.0.0.json" "$bundle/Evidence/release-manifest.json"

for evidence_document in \
    ac-01-foundation-evidence.md \
    ac-02-project-lifecycle-evidence.md \
    ac-03-guided-template-evidence.md \
    ac-04-ai-governance-evidence.md \
    ac-05-format-export-evidence.md \
    ac-06-batch-export-evidence.md \
    ac-07-compatibility-evidence.md \
    ac-08-accessibility-evidence.md \
    ac-09-performance-evidence.md \
    ac-10-functional-release-evidence.md
do
    cp "$root/docs/$evidence_document" "$bundle/Evidence/AcceptanceCriteria/$evidence_document"
done

while IFS= read -r evidence_path; do
    source="$root/$evidence_path"
    target="$bundle/Evidence/CanonicalSources/$evidence_path"
    mkdir -p "$(dirname -- "$target")"
    if test -d "$source"; then
        COPYFILE_DISABLE=1 /usr/bin/ditto --norsrc --noextattr --noqtn --noacl "$source" "$target"
    else
        cp "$source" "$target"
    fi
done < "$source_paths"

runtime="$bundle/Evidence/Runtime/ac-10-packaged-app"
binary="$bundle/PublicDocument.app/Contents/MacOS/PublicDocumentApp"
mkdir -p "$runtime/ac-01" "$runtime/ac-02" "$runtime/ac-03" "$runtime/ac-04" \
    "$runtime/ac-05" "$runtime/ac-06" "$runtime/ac-09"
codesign --verify --deep --strict "$bundle/PublicDocument.app"
architecture=$(lipo -archs "$binary")
test "$architecture" = "arm64" || fail "packaged executable must contain only arm64"
printf '%s\n' "$architecture" > "$runtime/ac-01/architecture.txt"
codesign -dv --verbose=2 "$bundle/PublicDocument.app" 2> "$runtime/ac-01/code-signature.txt"
jq -n \
    --arg architecture "$architecture" \
    --arg appBinarySHA256 "sha256:$(sha256 "$binary")" \
    --arg rhwpBinarySHA256 "sha256:$(sha256 "$bundle/PublicDocument.app/Contents/Resources/Engines/rhwp")" \
    --arg infoPlistSHA256 "sha256:$(sha256 "$bundle/PublicDocument.app/Contents/Info.plist")" \
    '{schemaVersion:1,architecture:$architecture,codesignVerification:"pass",appBinarySHA256:$appBinarySHA256,rhwpBinarySHA256:$rhwpBinarySHA256,infoPlistSHA256:$infoPlistSHA256}' \
    > "$runtime/ac-01/foundation-runtime.json"

PUBLIC_DOCUMENT_STUDIO_PROJECT_ROOT="$runtime/ac-02/window.project" \
    PUBLIC_DOCUMENT_STUDIO_CATALOG_ROOT="$runtime/ac-02/window.catalog" \
    "$binary" --window-lifecycle-self-test > "$runtime/ac-02/window-lifecycle.json"
"$binary" --project-store-self-test "$runtime/ac-02/project-store" > "$runtime/ac-02/project-store.json"
"$binary" --project-migration-self-test "$runtime/ac-02/project-migration" > "$runtime/ac-02/project-migration.json"
"$binary" --template-catalog-self-test "$runtime/ac-03/template-catalog" > "$runtime/ac-03/template-catalog.json"
"$binary" --ai-governance-self-test "$runtime/ac-04/ai-governance" > "$runtime/ac-04/ai-governance.json"

"$binary" --export-self-test "$runtime/ac-05/export-hwp-family" basic-hwp-family > "$runtime/ac-05/export-hwp-family.json"
"$binary" --export-self-test "$runtime/ac-05/export-loss-aware" all-consented > "$runtime/ac-05/export-loss-aware.json"
"$binary" --export-self-test "$runtime/ac-05/export-adversarial-markdown" adversarial-markdown > "$runtime/ac-05/export-adversarial-markdown.json"
"$binary" --export-self-test "$runtime/ac-05/export-markdown-unconsented" markdown-unconsented > "$runtime/ac-05/export-markdown-unconsented.json"
"$binary" --export-self-test "$runtime/ac-05/export-mixed-semantic-block" mixed-semantic-block > "$runtime/ac-05/export-mixed-semantic-block.json"

for scenario in partial-failure cancel-after-first cancel-before-publication crash-and-retry disk-full-and-retry; do
    "$binary" --batch-export-self-test "$runtime/ac-06/$scenario" "$scenario" > "$runtime/ac-06/batch-$scenario.json"
done
existing_root="$runtime/ac-06/existing-destination"
mkdir -p "$existing_root"
printf '%s' 'user-owned-existing-file' > "$existing_root/생활안전-계획.docx"
"$binary" --batch-export-self-test "$existing_root" existing-destination > "$runtime/ac-06/batch-existing-destination.json"
find "$runtime/ac-06" -type l -exec rm -- {} +
"$binary" --performance-self-test "$runtime/ac-09/performance" > "$runtime/ac-09/performance.json"
jq -e '
    .overallVerdict == "pass"
    and (.exportObservations | length == 8)
    and (.exportObservations | all(.passed == true))
' "$runtime/ac-09/performance.json" >/dev/null || fail "packaged AC-09 performance gate failed"

codesign --verify --deep --strict "$bundle/PublicDocument.app"
app_binary_hash=$(sha256 "$bundle/PublicDocument.app/Contents/MacOS/PublicDocumentApp")
rhwp_binary_hash=$(sha256 "$bundle/PublicDocument.app/Contents/Resources/Engines/rhwp")
source_count=$(wc -l < "$source_paths" | tr -d ' ')
jq -n \
    --arg appBinaryHash "sha256:$app_binary_hash" \
    --arg rhwpBinaryHash "sha256:$rhwp_binary_hash" \
    --argjson sourceCount "$source_count" \
    '{schemaVersion:2,codesignVerification:"pass",architecture:"arm64",appBinaryHash:$appBinaryHash,rhwpBinaryHash:$rhwpBinaryHash,declaredPrecedingSourceCount:$sourceCount,canonicalSourcesRoot:"Evidence/CanonicalSources",runtimeEvidenceRoot:"Evidence/Runtime/ac-10-packaged-app",sourceMapBoundary:"AC-10 source-map leaves are recorded outside the archive after publication.",fileProviderBoundary:"The canonical handoff is produced by package-release-archive.sh from this verified app."}' \
    > "$bundle/Evidence/Runtime/ac-10-packaged-app/final-publication-verification.json"
(
    cd "$bundle"
    find PublicDocument.app Evidence -type f ! -name SHA256SUMS | LC_ALL=C sort | while IFS= read -r artifact; do
        digest=$(shasum -a 256 "$artifact" | awk '{print $1}')
        printf '%s  %s\n' "$digest" "$artifact"
    done
) > "$bundle/Evidence/SHA256SUMS"
mv "$bundle" "$destination"
printf '%s\n' "$destination"
