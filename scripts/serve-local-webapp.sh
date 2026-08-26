#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}" exec /usr/bin/python3 -m public_document_web "$@"
