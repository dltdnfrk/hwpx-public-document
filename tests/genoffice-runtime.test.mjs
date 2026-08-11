import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdirSync, mkdtempSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import test from 'node:test'

const root = resolve(import.meta.dirname, '..')
const upstream = process.env['GENOFFICE_UPSTREAM'] ?? '/private/tmp/public-document-upstream-audit.YfDSXU/genoffice'
const dependencyRoot = process.env['GENOFFICE_DEPENDENCY_ROOT'] ?? '/tmp/public-document-genoffice-build.kPjYnB'
const sha256 = (path) => createHash('sha256').update(readFileSync(path)).digest('hex')
const forbidden = /genspark|AiPanel|electron-updater|apps\/(?:sheets|slides|pdf|shell|markdown)|packages\/(?:ai-provider|ai-search|agent-core|pptx-engine|pptx-render|electron-utils)|fetch\s*\(|WebSocket|XMLHttpRequest|sendBeacon/i

function build(destination) {
  execFileSync(process.execPath, [join(root, 'scripts/build-genoffice-runtime.mjs'), '--upstream', upstream, '--dependencies', dependencyRoot, '--output', destination], {
    cwd: root,
    env: { ...process.env, SOURCE_DATE_EPOCH: '315532800' },
    stdio: 'pipe',
  })
}

function createPreservationFixture(path) {
  const work = mkdtempSync(join(tmpdir(), 'genoffice-docx-fixture.'))
  for (const directory of ['_rels', 'word', 'word/_rels', 'customXml']) mkdirSync(join(work, directory), { recursive: true })
  writeFileSync(join(work, '[Content_Types].xml'), '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
  writeFileSync(join(work, '_rels/.rels'), '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
  writeFileSync(join(work, 'word/_rels/document.xml.rels'), '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
  writeFileSync(join(work, 'word/document.xml'), '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:sdt><w:sdtPr><w:alias w:val="보존"/></w:sdtPr><w:sdtContent><w:p><w:r><w:t>첫째 문단</w:t></w:r></w:p></w:sdtContent></w:sdt><w:p><w:r><w:t>둘째 문단</w:t></w:r></w:p><w:sectPr/></w:body></w:document>')
  writeFileSync(join(work, 'customXml/item1.xml'), '<?xml version="1.0"?><record>공공문서-보존</record>')
  execFileSync('zip', ['-X', '-q', '-r', path, '.'], { cwd: work })
}

test('Given the owned adapter When sources are inspected Then only pinned Docs package modules are imported', () => {
  const browser = readFileSync(join(root, 'GenOfficeFork/browser.tsx'), 'utf8')
  const cli = readFileSync(join(root, 'GenOfficeFork/docx-normalize.mjs'), 'utf8')
  assert.match(browser, /apps\/docs\/src\/renderer\/editor\/extensions/)
  assert.match(browser, /apps\/docs\/src\/renderer\/components\/NavPane/)
  assert.match(browser, /@genoffice\/ui/)
  assert.match(cli, /@genoffice\/docx-engine/)
  assert.doesNotMatch(`${browser}\n${cli}`, forbidden)
})

test('Given the pinned source When built twice Then runtime outputs and checked hashes are deterministic', () => {
  const first = mkdtempSync(join(tmpdir(), 'genoffice-runtime-first.'))
  const second = mkdtempSync(join(tmpdir(), 'genoffice-runtime-second.'))
  build(first)
  build(second)
  const manifest = JSON.parse(readFileSync(join(first, 'GenOffice/runtime-manifest.json'), 'utf8'))
  assert.equal(manifest.upstream.commit, 'd8305ff2dc152593a1ec5639d77e6860c6a512bd')
  assert.ok(manifest.inputs.length >= 6)
  for (const output of manifest.outputs) {
    const firstPath = join(first, output.path)
    const secondPath = join(second, output.path)
    assert.equal(sha256(firstPath), output.sha256)
    assert.equal(sha256(secondPath), output.sha256)
    assert.equal(statSync(firstPath).size, output.sizeBytes)
  }
  for (const file of ['public-document-genoffice.js', 'genoffice-docx-normalize.cjs']) {
    assert.doesNotMatch(readFileSync(join(first, 'GenOffice', file), 'utf8'), forbidden)
  }
  assert.equal(sha256(join(first, 'Engines/node')), manifest.node.sha256)
  assert.equal(execFileSync('lipo', ['-archs', join(first, 'Engines/node')], { encoding: 'utf8' }).trim(), 'arm64')
  assert.ok(manifest.node.linkedLibraries.every((path) => path.startsWith('/System/Library/') || path.startsWith('/usr/lib/')))
})

test('Given a DOCX containing Korean text and preserved parts When normalized Then order, customXml, and SDTs survive', () => {
  const destination = mkdtempSync(join(tmpdir(), 'genoffice-runtime-docx.'))
  build(destination)
  const fixture = join(destination, 'genoffice-preservation.docx')
  createPreservationFixture(fixture)
  const output = join(destination, 'normalized.docx')
  const savedAt = '2026-08-10T00:00:00.000Z'
  const stdout = execFileSync(join(destination, 'Engines/node'), [join(destination, 'GenOffice/genoffice-docx-normalize.cjs'), fixture, output, savedAt], { encoding: 'utf8' })
  const receipt = JSON.parse(stdout)
  assert.equal(receipt.schemaVersion, 1)
  assert.equal(receipt.savedAt, savedAt)
  assert.ok(receipt.blockCount >= 2)
  assert.ok(receipt.preservedPartNames.some((path) => path.startsWith('customXml/')))
  const listing = execFileSync('unzip', ['-p', output, 'word/document.xml'], { encoding: 'utf8' })
  assert.ok(listing.indexOf('첫째 문단') < listing.indexOf('둘째 문단'))
  assert.match(listing, /<w:sdt[ >]/)
  assert.match(execFileSync('unzip', ['-p', output, 'customXml/item1.xml'], { encoding: 'utf8' }), /공공문서-보존/)
})

test('Given packaging scripts When inspected Then the manifest-authoritative runtime tree and Node engine are required', () => {
  const packageScript = readFileSync(join(root, 'scripts/package-macos-app.sh'), 'utf8')
  const archiveScript = readFileSync(join(root, 'scripts/package-release-archive.sh'), 'utf8')
  assert.match(packageScript, /Resources\/GenOffice/)
  assert.match(packageScript, /Resources\/Engines\/node/)
  assert.match(archiveScript, /runtime-manifest\.json/)
  assert.match(archiveScript, /expected_genoffice/)
})
