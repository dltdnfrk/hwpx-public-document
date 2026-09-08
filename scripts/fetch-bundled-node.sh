#!/bin/sh
# Restore the pinned GenOffice Node runtime to Resources/Engines/node.
# GitHub rejects the 105MB arm64 binary, so clones fetch the official
# Node.js v22.17.1 macOS pkg and keep only the arm64 slice.
#
# Pins (GenOfficeFork/node-runtime-lock.json, Resources/GenOffice/node.spdx.json):
#   version:        22.17.1
#   arch:           arm64
#   pkg SHA-256:    31f30608a6c9961ef3d19002a578899d40cdaa6583d0d46744ae2be9aa137b0d
#   universal SHA-256 (sourceSha256):
#                   7ede1e8c98a2b2bb5965aff3c070ede061fc9e2a6a0b16774646487f94fe4541
#   arm64 SHA-256:  5c8cd3ab2559b530fceca01776064c56687619475a7ffc339178524af6cdaa25
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination=${1:-"$root/Resources/Engines/node"}
version=22.17.1
pkg_name="node-v${version}.pkg"
pkg_url="https://nodejs.org/download/release/v${version}/${pkg_name}"
pkg_sha256=31f30608a6c9961ef3d19002a578899d40cdaa6583d0d46744ae2be9aa137b0d
universal_sha256=7ede1e8c98a2b2bb5965aff3c070ede061fc9e2a6a0b16774646487f94fe4541
arm64_sha256=5c8cd3ab2559b530fceca01776064c56687619475a7ffc339178524af6cdaa25
work=$(mktemp -d "${TMPDIR:-/tmp}/public-document-node.XXXXXX")

cleanup() {
    case "$work" in
        "${TMPDIR:-/tmp}"/public-document-node.*) rm -rf -- "$work" ;;
        *) printf '%s\n' "refusing to clean unexpected path: $work" >&2 ;;
    esac
}
trap cleanup EXIT INT TERM

sha256_of() {
    /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'
}

test "$(/usr/sbin/sysctl -n hw.optional.arm64 2>/dev/null)" = "1" || {
    printf '%s\n' "bundled Node is pinned to Apple Silicon arm64" >&2
    exit 2
}

if [ -f "$destination" ]; then
    if [ "$(sha256_of "$destination")" = "$arm64_sha256" ] && \
       [ "$(/usr/bin/lipo -archs "$destination")" = "arm64" ]; then
        printf '%s\n' "$destination"
        exit 0
    fi
fi

curl -fsSL --retry 3 --retry-delay 2 -o "$work/$pkg_name" "$pkg_url"
test "$(sha256_of "$work/$pkg_name")" = "$pkg_sha256" || {
    printf '%s\n' "Node pkg SHA-256 mismatch" >&2
    exit 1
}

/usr/sbin/pkgutil --expand-full "$work/$pkg_name" "$work/expanded"
universal="$work/expanded/${pkg_name}/Payload/usr/local/bin/node"
if [ ! -f "$universal" ]; then
    universal=$(/usr/bin/find "$work/expanded" -path '*/usr/local/bin/node' -type f | /usr/bin/head -n 1)
fi
test -n "$universal" && test -f "$universal" || {
    printf '%s\n' "official Node payload is missing usr/local/bin/node" >&2
    exit 1
}
test "$(sha256_of "$universal")" = "$universal_sha256" || {
    printf '%s\n' "Node universal binary SHA-256 mismatch" >&2
    exit 1
}

thinned="$work/node-arm64"
/usr/bin/lipo "$universal" -thin arm64 -output "$thinned"
chmod 755 "$thinned"
test "$(sha256_of "$thinned")" = "$arm64_sha256" || {
    printf '%s\n' "Node arm64 SHA-256 mismatch" >&2
    exit 1
}
test "$(/usr/bin/lipo -archs "$thinned")" = "arm64" || {
    printf '%s\n' "Node architecture is not arm64" >&2
    exit 1
}
test "$("$thinned" --version)" = "v${version}" || {
    printf '%s\n' "Node version mismatch" >&2
    exit 1
}

mkdir -p "$(dirname -- "$destination")"
tmp_destination="$destination.tmp.$$"
cp "$thinned" "$tmp_destination"
chmod 755 "$tmp_destination"
mv "$tmp_destination" "$destination"
printf '%s\n' "$destination"
