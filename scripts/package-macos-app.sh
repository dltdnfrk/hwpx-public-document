#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination=${1:-"$root/dist/PublicDocument.app"}
binary="$root/.build/arm64-apple-macosx/release/PublicDocumentApp"

swift build --configuration release --product PublicDocumentApp --package-path "$root"
test -x "$binary"
rm -rf "$destination"
mkdir -p "$destination/Contents/MacOS" "$destination/Contents/Resources"
cp "$binary" "$destination/Contents/MacOS/PublicDocumentApp"
cp "$root/Resources/Info.plist" "$destination/Contents/Info.plist"
codesign --force --options runtime --sign - "$destination"
printf '%s\n' "$destination"
