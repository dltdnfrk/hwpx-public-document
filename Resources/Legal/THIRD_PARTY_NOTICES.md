# Third-party notices

This unsigned local build is derived from the exact source revisions recorded below. The matching complete license texts are shipped beside this notice and the machine-readable package relationships are in `provenance/sbom.spdx.json`.

## GenOffice Docs

- Source: `https://github.com/genspark-ai/genoffice.git`
- Commit: `d8305ff2dc152593a1ec5639d77e6860c6a512bd`
- License: Apache License 2.0, in `GenOffice-LICENSE.txt`
- Upstream notice: GenOffice, Copyright 2026 Mainfunc, Inc. This product includes software developed at Mainfunc, Inc.

Only the Docs interface grammar and required UI/DOCX boundaries are approved. Enterprise code and non-document products are not shipped.

## rhwp

- Source: `https://github.com/edwardkim/rhwp.git`
- Commit: `2dced7bfe10c6597cead634264c7c1781c01f1e7`
- License: MIT, in `rhwp-LICENSE.txt`
- Copyright: Copyright (c) 2025-2026 Edward Kim

rhwp is the approved HWP-family engine boundary. This AC foundation records the pin and license; later format work must remain inside that owned boundary.
The shipped arm64 engine applies local HWP interoperability fixes reproducibly to that exact commit. The patch inputs, source hashes, build script, and bundled binary hash are recorded in `provenance/upstream-lock.json`; no alternative converter is used.

The exact 204-package Cargo.lock dependency inventory is shipped as
`rhwp-RUST-DEPENDENCIES.md` and as SPDX package records. Package-manifest
license declarations are recorded separately from `licenseConcluded`, which
remains `NOASSERTION` unless a license conclusion has been made.

## GenOffice runtime packages

- Node.js 22.17.1 arm64: full license in `Node-LICENSE.txt`; SPDX inventory in `../GenOffice/node.spdx.json`.
- 42 bundled JavaScript packages: exact versions, declared licenses, and complete available license texts in `GenOffice-JS-DEPENDENCIES.md` and `GenOffice-JS-THIRD-PARTY-LICENSES.txt`; SPDX inventory and dependency relationships in `../GenOffice/javascript-runtime.spdx.json` and the root SBOM.
