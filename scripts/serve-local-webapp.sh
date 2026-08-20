#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec /usr/bin/python3 "$root/public_document_web.py" "$@"
