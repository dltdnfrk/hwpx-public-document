import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const readJSON = (path) => JSON.parse(readFileSync(resolve(root, path), 'utf8'))
const writeJSON = (path, value) => writeFileSync(resolve(root, path), `${JSON.stringify(value, null, 2)}\n`)
const sha256 = (path) => createHash('sha256').update(readFileSync(resolve(root, path))).digest('hex')

const runtimeManifest = readJSON('Resources/GenOffice/runtime-manifest.json')
const jsSbom = readJSON('Resources/GenOffice/javascript-runtime.spdx.json')
const nodeSbom = readJSON('Resources/GenOffice/node.spdx.json')
const rootSbom = readJSON('provenance/sbom.spdx.json')
const removedIDs = new Set(rootSbom.packages.filter((item) => item.SPDXID?.startsWith('SPDXRef-JS-') || item.SPDXID === 'SPDXRef-Package-NodeRuntime').map((item) => item.SPDXID))
const nodePackage = { ...nodeSbom.packages[0], SPDXID: 'SPDXRef-Package-NodeRuntime', checksums: [{ algorithm: 'SHA256', checksumValue: runtimeManifest.node.sha256 }] }
rootSbom.packages = [...rootSbom.packages.filter((item) => !removedIDs.has(item.SPDXID)), nodePackage, ...jsSbom.packages]
rootSbom.relationships = [
  ...rootSbom.relationships.filter((item) => !removedIDs.has(item.relatedSpdxElement) && item.relatedSpdxElement !== 'SPDXRef-Package-NodeRuntime'),
  { spdxElementId: 'SPDXRef-Package-GenOfficeDocs', relationshipType: 'DEPENDS_ON', relatedSpdxElement: 'SPDXRef-Package-NodeRuntime' },
  ...jsSbom.packages.map((item) => ({ spdxElementId: 'SPDXRef-Package-GenOfficeDocs', relationshipType: 'DEPENDS_ON', relatedSpdxElement: item.SPDXID })),
]
writeJSON('provenance/sbom.spdx.json', rootSbom)

const upstreamLock = readJSON('provenance/upstream-lock.json')
const genoffice = upstreamLock.upstreams.find((item) => item.name === 'genoffice')
genoffice.port_manifest_sha256 = `sha256:${sha256('provenance/genoffice-docs-port.json')}`
genoffice.local_patchset = {
  build_script_sha256: `sha256:${sha256('scripts/build-genoffice-runtime.mjs')}`,
  runtime_manifest_sha256: `sha256:${sha256('Resources/GenOffice/runtime-manifest.json')}`,
  runtime_input_lock_sha256: `sha256:${sha256('GenOfficeFork/runtime-input-lock.json')}`,
  browser_bundle_sha256: `sha256:${sha256('Resources/GenOffice/public-document-genoffice.js')}`,
  docx_cli_sha256: `sha256:${sha256('Resources/GenOffice/genoffice-docx-normalize.cjs')}`,
  node_arm64_sha256: `sha256:${sha256('Resources/Engines/node')}`,
  javascript_package_count: runtimeManifest.packages.length,
}
writeJSON('provenance/upstream-lock.json', upstreamLock)

const noticePath = resolve(root, 'Resources/Legal/THIRD_PARTY_NOTICES.md')
const notice = readFileSync(noticePath, 'utf8').split('\n## GenOffice runtime packages\n')[0].trimEnd()
writeFileSync(noticePath, `${notice}\n\n## GenOffice runtime packages\n\n- Node.js 22.17.1 arm64: full license in \`Node-LICENSE.txt\`; SPDX inventory in \`../GenOffice/node.spdx.json\`.\n- ${runtimeManifest.packages.length} bundled JavaScript packages: exact versions, declared licenses, and complete available license texts in \`GenOffice-JS-DEPENDENCIES.md\` and \`GenOffice-JS-THIRD-PARTY-LICENSES.txt\`; SPDX inventory and dependency relationships in \`../GenOffice/javascript-runtime.spdx.json\` and the root SBOM.\n`)
