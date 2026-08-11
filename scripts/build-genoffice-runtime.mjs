import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, isAbsolute, join, relative, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const projectRoot = resolve(import.meta.dirname, '..')
const expectedCommit = 'd8305ff2dc152593a1ec5639d77e6860c6a512bd'
const args = new Map()
for (let index = 2; index < process.argv.length; index += 2) args.set(process.argv[index], process.argv[index + 1])
const upstream = realpathSync(resolve(args.get('--upstream') ?? ''))
const dependencies = realpathSync(resolve(args.get('--dependencies') ?? upstream))
const finalOutput = resolve(args.get('--output') ?? join(projectRoot, 'Resources'))
const output = mkdtempSync(join(dirname(finalOutput), '.genoffice-runtime-stage.'))
process.on('exit', () => { if (existsSync(output)) rmSync(output, { recursive: true, force: true }) })
if (!isAbsolute(upstream) || !isAbsolute(dependencies)) throw new Error('absolute --upstream and --dependencies paths are required')

const sha256Bytes = (bytes) => createHash('sha256').update(bytes).digest('hex')
const sha256 = (path) => sha256Bytes(readFileSync(path))
const readJSON = (path) => JSON.parse(readFileSync(path, 'utf8'))
const commit = execFileSync('git', ['-C', upstream, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
if (commit !== expectedCommit) throw new Error(`GenOffice commit mismatch: ${commit}`)

const checkedLock = readJSON(join(projectRoot, 'GenOfficeFork/upstream-lock.json'))
if (checkedLock.commit !== expectedCommit) throw new Error('checked upstream lock commit mismatch')
for (const file of checkedLock.files) {
  if (sha256(join(upstream, file.path)) !== file.sha256) throw new Error(`upstream input hash mismatch: ${file.path}`)
}

const esbuild = await import(pathToFileURL(join(dependencies, 'node_modules/esbuild/lib/main.js')).href)
const safeLocale = join(projectRoot, 'GenOfficeFork/safe-locale.tsx')
const safeProtected = join(projectRoot, 'GenOfficeFork/safe-protected-render.ts')
const safeShapeSvg = join(projectRoot, 'GenOfficeFork/safe-shape-svg.ts')
const safeSetImmediate = join(projectRoot, 'GenOfficeFork/safe-set-immediate.ts')
const safeStream = join(projectRoot, 'GenOfficeFork/safe-stream.ts')
const upstreamPrefix = '@genoffice-upstream/'
const adapterPlugin = {
  name: 'public-document-genoffice-boundary',
  setup(build) {
    build.onResolve({ filter: /^@genoffice-upstream\// }, ({ path }) => {
      const base = join(upstream, path.slice(upstreamPrefix.length))
      return { path: existsSync(base) ? base : existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts` }
    })
    build.onResolve({ filter: /(?:^|\/)i18n\/locale$/ }, ({ path, resolveDir }) => {
      const candidate = resolve(resolveDir, path)
      return candidate.startsWith(join(upstream, 'apps/docs/')) ? { path: safeLocale } : undefined
    })
    build.onResolve({ filter: /(?:^|\/)protected-render$/ }, ({ path, resolveDir }) => {
      const candidate = resolve(resolveDir, path)
      return candidate.startsWith(join(upstream, 'apps/docs/')) ? { path: safeProtected } : undefined
    })
    build.onResolve({ filter: /(?:^|\/)shape-svg$/ }, ({ path, resolveDir }) => {
      const candidate = resolve(resolveDir, path)
      return candidate.startsWith(join(upstream, 'apps/docs/')) ? { path: safeShapeSvg } : undefined
    })
    build.onResolve({ filter: /^@genoffice\/ui$/ }, ({ importer }) => importer === join(projectRoot, 'GenOfficeFork/browser.tsx') ? { path: join(upstream, 'packages/ui/src/icons.tsx') } : undefined)
    build.onResolve({ filter: /^@genoffice\/docx-engine$/ }, () => ({ path: join(upstream, 'packages/docx-engine/src/index.ts') }))
    build.onResolve({ filter: /^setimmediate$/ }, () => ({ path: safeSetImmediate }))
    build.onResolve({ filter: /^jszip$/ }, () => ({ path: join(dependencies, 'node_modules/jszip/lib/index.js') }))
    build.onResolve({ filter: /^stream$/ }, () => ({ path: safeStream }))
  },
}

mkdirSync(join(output, 'GenOffice'), { recursive: true })
mkdirSync(join(output, 'Engines'), { recursive: true })
mkdirSync(join(output, 'Legal'), { recursive: true })
const shared = { bundle: true, metafile: true, plugins: [adapterPlugin], nodePaths: [join(dependencies, 'node_modules')], logLevel: 'silent', charset: 'utf8', legalComments: 'none', minify: true, sourcemap: false, jsx: 'automatic', jsxImportSource: 'react', define: { 'process.env.NODE_ENV': '"production"' } }
const browserPath = join(output, 'GenOffice/public-document-genoffice.js')
const cliPath = join(output, 'GenOffice/genoffice-docx-normalize.cjs')
const browser = await esbuild.build({ ...shared, entryPoints: [join(projectRoot, 'GenOfficeFork/browser.tsx')], outfile: browserPath, platform: 'browser', format: 'iife', target: ['safari17'] })
const cli = await esbuild.build({ ...shared, entryPoints: [join(projectRoot, 'GenOfficeFork/docx-normalize.mjs')], outfile: cliPath, platform: 'node', format: 'cjs', target: ['node22'] })

const nodeSource = '/usr/local/bin/node'
const nodeLock = readJSON(join(projectRoot, 'GenOfficeFork/node-runtime-lock.json'))
const nodeVersion = execFileSync(nodeSource, ['--version'], { encoding: 'utf8' }).trim()
if (nodeVersion !== 'v22.17.1') throw new Error(`Node version mismatch: ${nodeVersion}`)
if (sha256(nodeSource) !== nodeLock.sourceSha256) throw new Error('Node source hash mismatch')
const nodePath = join(output, 'Engines/node')
execFileSync('lipo', [nodeSource, '-thin', 'arm64', '-output', nodePath])
execFileSync('chmod', ['755', nodePath])
if (sha256(nodePath) !== nodeLock.arm64Sha256) throw new Error('Node arm64 hash mismatch')
const linkedLibraries = execFileSync('otool', ['-L', '-arch', 'arm64', nodePath], { encoding: 'utf8' }).split('\n').slice(1).map((line) => line.trim().split(' ')[0]).filter(Boolean)
if (!linkedLibraries.every((path) => path.startsWith('/System/Library/') || path.startsWith('/usr/lib/'))) throw new Error('Node links a non-system library')

const genofficeLicense = join(output, 'Legal/GenOffice-LICENSE.txt')
copyFileSync(join(upstream, 'LICENSE'), genofficeLicense)
const nodeNotice = join(output, 'Legal/Node-v22.17.1-NOTICE.txt')
writeFileSync(nodeNotice, 'Node.js v22.17.1\nSPDX-License-Identifier: MIT\nSource: https://github.com/nodejs/node/tree/v22.17.1\nLicense: https://github.com/nodejs/node/blob/v22.17.1/LICENSE\nBundled binary source: /usr/local/bin/node (arm64 slice only)\n')
const nodeLicense = join(output, 'Legal/Node-LICENSE.txt')
const checkedNodeLicense = join(projectRoot, 'Resources/Legal/Node-LICENSE.txt')
if (sha256(checkedNodeLicense) !== nodeLock.licenseSha256) throw new Error('Node license hash mismatch')
copyFileSync(checkedNodeLicense, nodeLicense)
const nodeSbom = join(output, 'GenOffice/node.spdx.json')
writeFileSync(nodeSbom, `${JSON.stringify({ spdxVersion: 'SPDX-2.3', dataLicense: 'CC0-1.0', SPDXID: 'SPDXRef-DOCUMENT', name: 'node-v22.17.1-arm64', documentNamespace: `https://public-document-studio.local/spdx/node/${sha256(nodePath)}`, creationInfo: { created: '1980-01-01T00:00:00Z', creators: ['Tool: build-genoffice-runtime.mjs'] }, packages: [{ name: 'Node.js', SPDXID: 'SPDXRef-Package-Node', versionInfo: '22.17.1', downloadLocation: 'https://nodejs.org/download/release/v22.17.1/', filesAnalyzed: false, licenseDeclared: 'MIT', licenseConcluded: 'MIT', copyrightText: 'Copyright Node.js contributors' }] }, null, 2)}\n`)

const logicalInput = (path) => path.startsWith(upstream) ? `upstream/${relative(upstream, path)}` : path.startsWith(projectRoot) ? `adapter/${relative(projectRoot, path)}` : path.startsWith(dependencies) ? `dependencies/${relative(dependencies, path)}` : (() => { throw new Error(`build input escaped approved roots: ${path}`) })()
const resolveInput = (path) => {
  if (isAbsolute(path)) return path
  for (const root of [projectRoot, dependencies, upstream]) {
    const candidate = resolve(root, path)
    if (existsSync(candidate)) return candidate
  }
  throw new Error(`cannot resolve build input: ${path}`)
}
const inputPaths = [
  ...[...Object.keys(browser.metafile.inputs), ...Object.keys(cli.metafile.inputs)].map(resolveInput),
  join(projectRoot, 'scripts/build-genoffice-runtime.mjs'),
  join(projectRoot, 'GenOfficeFork/upstream-lock.json'),
  join(projectRoot, 'GenOfficeFork/node-runtime-lock.json'),
  join(upstream, 'package-lock.json'),
  join(upstream, 'LICENSE'),
]
const codepointCompare = (a, b) => a < b ? -1 : a > b ? 1 : 0
const uniqueInputs = [...new Set(inputPaths)].sort((a, b) => codepointCompare(logicalInput(a), logicalInput(b)))
const inputs = uniqueInputs.map((path) => ({ path: logicalInput(path), sha256: sha256(path) }))
const inputLockPath = join(projectRoot, 'GenOfficeFork/runtime-input-lock.json')
const packageAt = (name, path) => {
  const value = readJSON(path)
  return { name, version: value.version, license: value.license ?? 'NOASSERTION', author: typeof value.author === 'string' ? value.author : 'NOASSERTION', packageJsonSha256: sha256(path) }
}
const nodeModules = join(dependencies, 'node_modules')
const dependencyPackageNames = new Set()
for (const path of uniqueInputs) {
  if (!path.startsWith(`${nodeModules}/`)) continue
  const parts = relative(nodeModules, path).split('/')
  dependencyPackageNames.add(parts[0].startsWith('@') ? `${parts[0]}/${parts[1]}` : parts[0])
}
const packages = [
  packageAt('@genoffice/docx-engine', join(upstream, 'packages/docx-engine/package.json')),
  packageAt('@genoffice/ui', join(upstream, 'packages/ui/package.json')),
  ...[...dependencyPackageNames].sort(codepointCompare).map((name) => packageAt(name, join(nodeModules, name, 'package.json'))),
]
const buildTool = packageAt('esbuild', join(nodeModules, 'esbuild/package.json'))
const inputLock = { schemaVersion: 1, upstreamCommit: expectedCommit, inputs, packages, buildTool }
if (args.has('--update-input-lock')) writeFileSync(inputLockPath, `${JSON.stringify(inputLock, null, 2)}\n`)
else if (JSON.stringify(readJSON(inputLockPath)) !== JSON.stringify(inputLock)) throw new Error('runtime input lock mismatch; inspect inputs and use --update-input-lock intentionally')
const jsNotices = join(output, 'Legal/GenOffice-JS-DEPENDENCIES.md')
writeFileSync(jsNotices, `# GenOffice runtime JavaScript dependencies\n\n${packages.map((item) => `- ${item.name} ${item.version} — ${item.license}`).join('\n')}\n`)
const jsLicenses = join(output, 'Legal/GenOffice-JS-THIRD-PARTY-LICENSES.txt')
const packageDirectory = (name) => name.startsWith('@genoffice/') ? upstream : join(nodeModules, name)
const licenseSections = packages.map((item) => {
  const directory = packageDirectory(item.name)
  const candidate = readdirSync(directory).find((name) => /^(license|copying|notice)(\.|$)/i.test(name))
  const readmePath = join(directory, 'README.md')
  const readmeLicense = existsSync(readmePath) ? readFileSync(readmePath, 'utf8').split(/^## License\s*$/m)[1]?.trim() : undefined
  const mit = `Copyright (c) ${item.author}\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.`
  const body = candidate ? readFileSync(join(directory, candidate), 'utf8') : readmeLicense?.includes('Permission is hereby granted') ? readmeLicense : item.license === 'MIT' ? mit : `License expression: ${item.license}\nNo standalone license text was present in the installed package.`
  return `===== ${item.name} ${item.version} (${item.license}) =====\n${body.trim()}\n`
})
writeFileSync(jsLicenses, `${licenseSections.join('\n')}\n`)
const jsSbom = join(output, 'GenOffice/javascript-runtime.spdx.json')
const spdxPackages = packages.map((item, index) => ({ name: item.name, SPDXID: `SPDXRef-JS-${index + 1}`, versionInfo: item.version, downloadLocation: 'NOASSERTION', filesAnalyzed: false, licenseDeclared: item.license, licenseConcluded: item.license, copyrightText: 'NOASSERTION' }))
writeFileSync(jsSbom, `${JSON.stringify({ spdxVersion: 'SPDX-2.3', dataLicense: 'CC0-1.0', SPDXID: 'SPDXRef-DOCUMENT', name: 'public-document-genoffice-javascript-runtime', documentNamespace: `https://public-document-studio.local/spdx/genoffice-js/${expectedCommit}`, creationInfo: { created: '1980-01-01T00:00:00Z', creators: ['Tool: build-genoffice-runtime.mjs'] }, packages: spdxPackages, relationships: spdxPackages.map((item) => ({ spdxElementId: 'SPDXRef-DOCUMENT', relationshipType: 'DESCRIBES', relatedSpdxElement: item.SPDXID })) }, null, 2)}\n`)
const outputPaths = [browserPath, cliPath, nodeSbom, jsSbom, genofficeLicense, jsNotices, jsLicenses, nodeNotice, nodeLicense]
const outputs = outputPaths.map((path) => ({ path: relative(output, path), sha256: sha256(path), sizeBytes: statSync(path).size }))
const forbiddenPattern = /genspark|AiPanel|electron-updater|apps\/(?:sheets|slides|pdf|shell|markdown)|packages\/(?:ai-provider|ai-search|agent-core|pptx-engine|pptx-render|electron-utils)|fetch\s*\(|WebSocket|XMLHttpRequest|sendBeacon|new\s+Function|eval\s*\(/i
const scannedOutputs = [browserPath, cliPath].map((path) => relative(output, path))
for (const path of [browserPath, cliPath]) {
  const text = readFileSync(path, 'utf8')
  if (forbiddenPattern.test(text)) throw new Error(`forbidden runtime token: ${path}`)
  for (const leakedRoot of [upstream, dependencies, projectRoot]) if (text.includes(leakedRoot)) throw new Error(`absolute build path leaked into runtime: ${leakedRoot}`)
}
const manifest = {
  schemaVersion: 1,
  upstream: { repository: checkedLock.repository, commit: expectedCommit, license: 'Apache-2.0' },
  inputs,
  inputLock: { sourcePath: 'GenOfficeFork/runtime-input-lock.json', packagedPath: 'Provenance/genoffice-runtime-input-lock.json', sha256: sha256(inputLockPath) },
  outputs,
  packages,
  buildTool,
  forbiddenScan: { status: 'pass', caseInsensitive: true, patterns: ['genspark', 'AiPanel', 'electron-updater', 'non-Docs app/package paths', 'fetch(', 'WebSocket', 'XMLHttpRequest', 'sendBeacon', 'new Function', 'eval('], scannedOutputs },
  node: { version: '22.17.1', sourcePath: 'Engines/node', sourceSha256: nodeLock.sourceSha256, sha256: sha256(nodePath), sizeBytes: statSync(nodePath).size, architecture: 'arm64', linkedLibraries, lock: { sourcePath: 'GenOfficeFork/node-runtime-lock.json', packagedPath: 'Provenance/genoffice-node-runtime-lock.json', sha256: sha256(join(projectRoot, 'GenOfficeFork/node-runtime-lock.json')) } },
  runtime: { browserBundlePath: 'GenOffice/public-document-genoffice.js', docxCliPath: 'GenOffice/genoffice-docx-normalize.cjs', customElementTag: 'public-document-genoffice-editor', readyEvent: 'public-document-genoffice-ready', changeEvent: 'public-document-genoffice-change', offline: true },
}
writeFileSync(join(output, 'GenOffice/runtime-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`)
for (const directory of ['GenOffice', 'Engines', 'Legal']) mkdirSync(join(finalOutput, directory), { recursive: true })
for (const path of [...outputPaths, nodePath]) renameSync(path, join(finalOutput, relative(output, path)))
renameSync(join(output, 'GenOffice/runtime-manifest.json'), join(finalOutput, 'GenOffice/runtime-manifest.json'))
process.stdout.write(`${join(finalOutput, 'GenOffice/runtime-manifest.json')}\n`)
