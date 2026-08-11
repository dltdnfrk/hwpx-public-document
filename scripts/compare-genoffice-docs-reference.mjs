import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(import.meta.dirname, '..')
const rounded = (number) => Math.round(number * 10_000) / 10_000
const delta = (left, right, scale) => rounded(Math.abs(left - right) / scale)

function orderAgreement(reference, current) {
  const order = ['commandChrome', 'workspace', 'status']
  const pairs = []
  for (let left = 0; left < order.length; left += 1) for (let right = left + 1; right < order.length; right += 1) pairs.push([order[left], order[right]])
  const comparable = pairs.filter(([a, b]) => reference[a] && reference[b] && current[a] && current[b])
  const passing = comparable.filter(([a, b]) => Math.sign(reference[a].y - reference[b].y) === Math.sign(current[a].y - current[b].y))
  return comparable.length ? rounded(passing.length / comparable.length) : 0
}

function overlap(left, right) {
  return left.x < right.x + right.width && left.x + left.width > right.x && left.y < right.y + right.height && left.y + left.height > right.y
}

export function compareDesktopGeometry(reference, current) {
  const required = ['commandTabs', 'commandChrome', 'workspace', 'navigation', 'canvas', 'document', 'status']
  const shared = required.filter((name) => reference.regions[name] && current.regions[name])
  const viewport = reference.viewport
  const illegal = [
    ['navigation', 'document'], ['commandChrome', 'status'],
  ].filter(([left, right]) => reference.regions[left] && reference.regions[right] && current.regions[left] && current.regions[right])
    .filter(([left, right]) => overlap(current.regions[left], current.regions[right])).length
  const metrics = {
    chromeBottomDelta: delta(reference.regions.commandChrome.height, current.regions.commandChrome.height, viewport.height),
    navigationWidthDelta: delta(reference.regions.navigation.width, current.regions.navigation.width, viewport.width),
    documentCenterDelta: delta(reference.regions.document.x + reference.regions.document.width / 2, current.regions.document.x + current.regions.document.width / 2, viewport.width),
    statusHeightDelta: delta(reference.regions.status.height, current.regions.status.height, viewport.height),
  }
  const thresholds = { chromeBottomDelta: 0.03, navigationWidthDelta: 0.08, documentCenterDelta: 0.08, statusHeightDelta: 0.02, rawPixelEquivalence: false }
  const coverage = rounded(shared.length / required.length)
  const verticalOrderAgreement = orderAgreement(reference.regions, current.regions)
  const passed = coverage === 1 && verticalOrderAgreement === 1 && illegal === 0
    && Object.entries(metrics).every(([name, value]) => value <= thresholds[name])
  return { coverage, verticalOrderAgreement, illegalOverlapCount: illegal, metrics, thresholds, passed }
}

function options(arguments_) {
  const parsed = new Map()
  for (let index = 0; index < arguments_.length; index += 2) parsed.set(arguments_[index], arguments_[index + 1])
  for (const name of ['--reference-receipt', '--studio-url', '--output-root']) if (!parsed.get(name)) throw new Error(`missing required option: ${name}`)
  return parsed
}

function confinedOutput(path) {
  const target = resolve(root, path)
  const lexical = relative(root, target)
  if ((isAbsolute(path) && !target.startsWith(`${root}/`)) || lexical.startsWith('..') || isAbsolute(lexical)) throw new Error('output root must stay within the project')
  if (existsSync(target)) throw new Error('output root already exists')
  return target
}

async function regions(page, width, height) {
  await page.setViewportSize({ width, height })
  await page.goto(page.__studioURL)
  await page.waitForSelector('public-document-genoffice-editor[data-runtime="ready"]')
  const selectors = { commandTabs: '.ribbon-tabs', workspace: '.workspace', navigation: '.outline-panel', canvas: '.canvas', document: 'public-document-genoffice-editor', status: '.statusbar' }
  const result = {}
  for (const [name, selector] of Object.entries(selectors)) {
    const locator = page.locator(selector).first()
    if (await locator.isVisible()) result[name] = await locator.boundingBox()
  }
  const tools = await page.locator('.ribbon').first().boundingBox()
  const tabs = result.commandTabs
  if (tools && tabs) {
    const bottom = Math.max(tabs.y + tabs.height, tools.y + tools.height)
    result.commandChrome = { x: Math.min(tabs.x, tools.x), y: Math.min(tabs.y, tools.y), width: Math.max(tabs.width, tools.width), height: bottom - Math.min(tabs.y, tools.y) }
  }
  return { viewport: { width, height }, regions: result }
}

export async function main(arguments_ = process.argv.slice(2)) {
  const parsed = options(arguments_)
  const output = confinedOutput(parsed.get('--output-root'))
  const reference = JSON.parse(readFileSync(resolve(root, parsed.get('--reference-receipt')), 'utf8'))
  mkdirSync(output)
  const require = createRequire(resolve(root, '.omo/ac08-browser/package.json'))
  const { chromium } = require('playwright')
  const browser = await chromium.launch({ channel: 'chrome' })
  try {
    const page = await browser.newPage()
    page.__studioURL = parsed.get('--studio-url')
    const current1280 = await regions(page, 1280, 820)
    await page.screenshot({ path: resolve(output, 'studio-1280.png') })
    const current920 = await regions(page, 920, 640)
    await page.screenshot({ path: resolve(output, 'studio-920.png') })
    const reference1280 = reference.captures.find((entry) => entry.viewport.width === 1280)
    const reference920 = reference.captures.find((entry) => entry.viewport.width === 920)
    const desktop = compareDesktopGeometry(reference1280, current1280)
    const common = ['commandTabs', 'commandChrome', 'workspace', 'canvas', 'document', 'status']
    const responsive = {
      coverage: common.filter((name) => reference920.regions[name] && current920.regions[name]).length / common.length,
      outlineHidden: !current920.regions.navigation,
      paperWidth: current920.regions.document?.width,
      noOverlayObstruction: current920.regions.document && current920.regions.commandChrome ? !overlap(current920.regions.document, current920.regions.commandChrome) : false,
    }
    responsive.passed = responsive.coverage === 1 && responsive.outlineHidden && Math.abs(responsive.paperWidth - 794) <= 1 && responsive.noOverlayObstruction
    const result = { schemaVersion: 1, lineage: reference.lineage, referenceSetHash: reference.referenceSetHash, comparisons: { desktop, responsive }, passed: desktop.passed && responsive.passed }
    result.sha256 = createHash('sha256').update(JSON.stringify(result)).digest('hex')
    writeFileSync(resolve(output, 'reference-comparison.json'), `${JSON.stringify(result, null, 2)}\n`)
    if (!result.passed) throw new Error('GenOffice Docs semantic geometry comparison failed')
  } finally {
    await browser.close()
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main().catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1 })
