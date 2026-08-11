import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const run = (script, arguments_) => spawnSync(
  process.execPath,
  [path.join(root, 'scripts', script), ...arguments_],
  { cwd: root, encoding: 'utf8' },
)

test('capture CLI reports a bounded argument error when required options are absent', () => {
  // Given: the capture command has no inputs.
  // When: the CLI parses its boundary.
  const result = run('capture-genoffice-docs-reference.mjs', [])

  // Then: it fails with the missing machine option, not an implementation stack.
  assert.equal(result.status, 1)
  assert.match(result.stderr, /missing required option: --genoffice-source/u)
  assert.doesNotMatch(result.stderr, /\n\s+at /u)
})

test('capture CLI rejects evidence output outside the canonical project', () => {
  // Given: every required input is present syntactically but output escapes the project.
  // When: the CLI validates path confinement before external I/O.
  const result = run('capture-genoffice-docs-reference.mjs', [
    '--genoffice-source', '/private/tmp/genoffice-input',
    '--docx', path.join(root, 'fixture.docx'),
    '--output-root', '/tmp/ac08-reference-evidence',
  ])

  // Then: the escaped evidence path is rejected.
  assert.equal(result.status, 1)
  assert.match(result.stderr, /output root must stay within the project/u)
})

test('reference-set hashing is canonical and mutation-sensitive', async () => {
  // Given: equivalent projections with different key insertion order.
  const module_ = await import(pathToFileURL(path.join(root, 'scripts', 'capture-genoffice-docs-reference.mjs')).href)
  const first = { lineage: 'pinned-genoffice-docs-fidelity-v1', captures: [{ width: 1280, height: 820 }] }
  const reordered = { captures: [{ height: 820, width: 1280 }], lineage: 'pinned-genoffice-docs-fidelity-v1' }

  // When: both projections and a mutated projection are hashed.
  const firstHash = module_.hashCanonical(first)
  const reorderedHash = module_.hashCanonical(reordered)
  const changedHash = module_.hashCanonical({ ...first, captures: [{ width: 920, height: 640 }] })

  // Then: ordering is irrelevant while semantic mutation changes identity.
  assert.equal(firstHash, reorderedHash)
  assert.notEqual(firstHash, changedHash)
  assert.match(firstHash, /^sha256:[0-9a-f]{64}$/u)
})

test('comparison metrics apply the approved normalized geometry thresholds', async () => {
  // Given: seven shared semantic regions inside the approved deltas.
  const module_ = await import(pathToFileURL(path.join(root, 'scripts', 'compare-genoffice-docs-reference.mjs')).href)
  const reference = {
    viewport: { width: 1280, height: 820 },
    regions: {
      commandTabs: { x: 0, y: 0, width: 1280, height: 40 },
      commandChrome: { x: 0, y: 40, width: 1280, height: 90 },
      workspace: { x: 0, y: 130, width: 1280, height: 660 },
      navigation: { x: 0, y: 130, width: 230, height: 660 },
      canvas: { x: 230, y: 130, width: 1050, height: 660 },
      document: { x: 340, y: 160, width: 794, height: 1123 },
      status: { x: 0, y: 790, width: 1280, height: 30 },
    },
  }
  const current = structuredClone(reference)
  current.regions.commandChrome.height = 100
  current.regions.navigation.width = 260
  current.regions.document.x = 350
  current.regions.status.height = 28

  // When: the semantic geometry is compared.
  const comparison = module_.compareDesktopGeometry(reference, current)

  // Then: all approved normalized assertions pass without a pixel claim.
  assert.equal(comparison.coverage, 1)
  assert.equal(comparison.verticalOrderAgreement, 1)
  assert.equal(comparison.illegalOverlapCount, 0)
  assert.equal(comparison.passed, true)
  assert.equal(comparison.thresholds.rawPixelEquivalence, false)
})

test('comparison CLI rejects evidence output outside the canonical project', () => {
  // Given: a comparison command whose evidence path escapes the project.
  // When: the CLI validates its boundary.
  const result = run('compare-genoffice-docs-reference.mjs', [
    '--reference-receipt', path.join(root, 'reference-receipt.json'),
    '--studio-url', 'http://127.0.0.1:4173/Resources/Studio/',
    '--output-root', '/tmp/ac08-reference-comparison',
  ])

  // Then: the escaped evidence path is rejected before browser work.
  assert.equal(result.status, 1)
  assert.match(result.stderr, /output root must stay within the project/u)
})
