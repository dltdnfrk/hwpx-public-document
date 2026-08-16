#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
requested_destination=${1:-"$root/dist/PublicDocument.app"}
package_scratch=${PUBLIC_DOCUMENT_PACKAGE_SCRATCH_PATH:-"$root/.build/package-release"}
binary="$package_scratch/arm64-apple-macosx/release/PublicDocumentApp"
staging_root=$(mktemp -d "${TMPDIR:-/tmp}/public-document-package.XXXXXX")
destination="$staging_root/PublicDocument.app"

cleanup() {
    case "$staging_root" in
        "${TMPDIR:-/tmp}"/public-document-package.*) rm -rf -- "$staging_root" ;;
        *) printf '%s\n' "refusing to clean unexpected path: $staging_root" >&2 ;;
    esac
}
trap cleanup EXIT INT TERM

destination_name=$(basename -- "$requested_destination")
destination_parent=$(dirname -- "$requested_destination")
allowed_parent=${PUBLIC_DOCUMENT_PACKAGE_PARENT:-"$root/dist"}
case "$destination_name" in
    *.app) ;;
    *) printf '%s\n' "destination must be a direct .app child of $root/dist" >&2; exit 2 ;;
esac
mkdir -p "$destination_parent" "$allowed_parent"
destination_parent=$(CDPATH= cd -- "$destination_parent" && pwd -P)
allowed_parent=$(CDPATH= cd -- "$allowed_parent" && pwd -P)
test "$destination_parent" = "$allowed_parent" || {
    printf '%s\n' "destination must be a direct .app child of $allowed_parent" >&2
    exit 2
}
requested_destination="$destination_parent/$destination_name"
test ! -L "$requested_destination" || {
    printf '%s\n' "refusing to replace a symbolic-link destination" >&2
    exit 2
}

input_stamp="$package_scratch/PublicDocumentApp.inputs.sha256"
current_input_hash=$(
    {
        printf '%s\n' "$root/Package.swift"
        find "$root/Sources" -type f -print
    } | LC_ALL=C sort | while IFS= read -r source; do
        digest=$(/usr/bin/shasum -a 256 "$source" | /usr/bin/awk '{print $1}')
        printf '%s  %s\n' "$digest" "${source#"$root/"}"
    done | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}'
)
cached_input_hash=''
if test -f "$input_stamp"; then
    IFS= read -r cached_input_hash < "$input_stamp"
fi
if test ! -x "$binary" || test "$cached_input_hash" != "$current_input_hash"; then
    swift build --configuration release --product PublicDocumentApp \
        --package-path "$root" \
        --scratch-path "$package_scratch" \
        --triple arm64-apple-macosx \
        -j 4
    mkdir -p "$package_scratch"
    printf '%s\n' "$current_input_hash" > "$input_stamp.tmp"
    mv "$input_stamp.tmp" "$input_stamp"
fi
test -x "$binary"
mkdir -p "$destination/Contents/MacOS" "$destination/Contents/Resources/Provenance" "$destination/Contents/Resources/Engines"
cp "$binary" "$destination/Contents/MacOS/PublicDocumentApp"
cp "$root/Resources/Info.plist" "$destination/Contents/Info.plist"
cp -R "$root/Resources/Studio" "$destination/Contents/Resources/Studio"
cp -R "$root/Resources/Legal" "$destination/Contents/Resources/Legal"
cp -R "$root/Resources/Templates" "$destination/Contents/Resources/Templates"
cp -R "$root/Resources/Capabilities" "$destination/Contents/Resources/Capabilities"
cp -R "$root/Resources/Compatibility" "$destination/Contents/Resources/Compatibility"
cp -R "$root/Resources/Performance" "$destination/Contents/Resources/Performance"
cp -R "$root/Resources/GenOffice" "$destination/Contents/Resources/GenOffice"
"$root/scripts/fetch-bundled-node.sh"
cp "$root/Resources/Engines/rhwp" "$destination/Contents/Resources/Engines/rhwp"
cp "$root/Resources/Engines/node" "$destination/Contents/Resources/Engines/node"
chmod 755 "$destination/Contents/Resources/Engines/node"
cp "$root/provenance/upstream-lock.json" "$destination/Contents/Resources/Provenance/upstream-lock.json"
cp "$root/provenance/genoffice-docs-port.json" "$destination/Contents/Resources/Provenance/genoffice-docs-port.json"
cp "$root/provenance/sbom.spdx.json" "$destination/Contents/Resources/Provenance/sbom.spdx.json"
cp "$root/provenance/rhwp-dependency-lock.json" "$destination/Contents/Resources/Provenance/rhwp-dependency-lock.json"
cp "$root/GenOfficeFork/runtime-input-lock.json" "$destination/Contents/Resources/Provenance/genoffice-runtime-input-lock.json"
cp "$root/GenOfficeFork/node-runtime-lock.json" "$destination/Contents/Resources/Provenance/genoffice-node-runtime-lock.json"
find "$destination/Contents/Resources" -name '* 2.*' -delete
xattr -cr "$destination"
chflags -R nohidden,nouchg "$destination"
codesign --force --options runtime --sign - "$destination"
codesign --verify --deep --strict "$destination"
expected_node_hash=$(/usr/bin/jq -er '.node.sha256' "$destination/Contents/Resources/GenOffice/runtime-manifest.json")
actual_node_hash=$(/usr/bin/shasum -a 256 "$destination/Contents/Resources/Engines/node" | /usr/bin/awk '{print $1}')
test "$expected_node_hash" = "$actual_node_hash"
rm -rf -- "$requested_destination"
COPYFILE_DISABLE=1 /usr/bin/ditto --norsrc --noextattr --noqtn --noacl "$destination" "$requested_destination"
chflags -R nohidden,nouchg "$requested_destination"
xattr -cr "$requested_destination" || true
test "$(lipo -archs "$requested_destination/Contents/MacOS/PublicDocumentApp")" = "arm64"
toolkit_sha256=$(/usr/bin/shasum -a 256 "$root/Resources/Templates/official-style-toolkit-1.0.0.json" | /usr/bin/awk '{print $1}')
envelope_sha256=$(/usr/bin/shasum -a 256 "$root/Resources/Templates/catalog-envelope.json" | /usr/bin/awk '{print $1}')
source_revision=$(git -C "$root" rev-parse HEAD)
PUBLIC_DOCUMENT_ROOT="$root" \
PUBLIC_DOCUMENT_APP="$requested_destination" \
PUBLIC_DOCUMENT_SOURCE_REVISION="$source_revision" \
PUBLIC_DOCUMENT_TOOLKIT_SHA256="$toolkit_sha256" \
PUBLIC_DOCUMENT_ENVELOPE_SHA256="$envelope_sha256" \
/usr/bin/python3 - <<'PY'
from pathlib import Path
import os
import sys

root = Path(os.environ["PUBLIC_DOCUMENT_ROOT"])
sys.path.insert(0, str(root))
from public_document_install import write_bundle_manifest

app = Path(os.environ["PUBLIC_DOCUMENT_APP"])
write_bundle_manifest(
    app,
    Path(str(app) + ".manifest"),
    source_revision=os.environ["PUBLIC_DOCUMENT_SOURCE_REVISION"],
    toolkit_sha256=os.environ["PUBLIC_DOCUMENT_TOOLKIT_SHA256"],
    envelope_sha256=os.environ["PUBLIC_DOCUMENT_ENVELOPE_SHA256"],
)
PY
printf '%s\n' "$requested_destination"
