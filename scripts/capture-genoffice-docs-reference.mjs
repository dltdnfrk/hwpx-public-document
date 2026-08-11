import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = realpathSync(resolve(import.meta.dirname, '..'))
const approvedCommit = 'd8305ff2dc152593a1ec5639d77e6860c6a512bd'
const approvedTree = '41cccf8c72120f971fca4f37fe257ffc4b1d8b99'

const stable = (value) => Array.isArray(value)
  ? value.map(stable)
  : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]))
    : value

export const hashCanonical = (value) => `sha256:${createHash('sha256').update(JSON.stringify(stable(value))).digest('hex')}`
const sha256 = (path) => `sha256:${createHash('sha256').update(readFileSync(path)).digest('hex')}`

function options(arguments_) {
  const parsed = new Map()
  for (let index = 0; index < arguments_.length; index += 2) parsed.set(arguments_[index], arguments_[index + 1])
  for (const name of ['--genoffice-source', '--docx', '--output-root']) {
    if (!parsed.get(name)) throw new Error(`missing required option: ${name}`)
  }
  return parsed
}

function confinedOutput(path) {
  if (isAbsolute(path)) {
    const lexical = relative(root, resolve(path))
    if (lexical.startsWith('..') || isAbsolute(lexical)) throw new Error('output root must stay within the project')
  }
  const target = resolve(root, path)
  const lexical = relative(root, target)
  if (lexical.startsWith('..') || isAbsolute(lexical)) throw new Error('output root must stay within the project')
  if (existsSync(target)) throw new Error('output root already exists')
  return target
}

function git(source, ...arguments_) {
  const result = spawnSync('git', ['-C', source, ...arguments_], { encoding: 'utf8' })
  if (result.status !== 0) throw new Error(result.stderr.trim() || `git ${arguments_.join(' ')} failed`)
  return result.stdout.trim()
}

async function box(page, selector, required = true) {
  const locator = page.locator(selector).first()
  if (await locator.count() === 0 || !await locator.isVisible()) {
    if (required) throw new Error(`required GenOffice region is not visible: ${selector}`)
    return null
  }
  const value = await locator.boundingBox()
  if (!value && required) throw new Error(`required GenOffice region has no geometry: ${selector}`)
  return value && Object.fromEntries(Object.entries(value).map(([key, number]) => [key, Math.round(number * 100) / 100]))
}

async function capture(page, output, width, height) {
  await page.setViewportSize({ width, height })
  await page.waitForSelector('.doc-page.ProseMirror', { state: 'visible', timeout: 30_000 })
  const collapseAI = page.locator('.ai-header-btn').first()
  if (await collapseAI.isVisible()) await collapseAI.click()
  if (width === 1280) {
    await page.getByRole('button', { name: /^View$/u }).click()
    await page.getByRole('button', { name: /Navigation Pane/u }).click()
    await page.waitForSelector('.nav-pane', { state: 'visible' })
  }
  await page.screenshot({ path: resolve(output, `genoffice-docs-${width}.png`) })
  const selectors = {
    commandTabs: '.ribbon-tabs', commandChrome: '.ribbon', workspace: '.app-main',
    navigation: '.nav-pane', canvas: '.workspace', document: '.doc-page.ProseMirror', status: '.status-bar',
  }
  const regions = {}
  for (const [name, selector] of Object.entries(selectors)) {
    const value = await box(page, selector, name !== 'navigation' || width === 1280)
    if (value) regions[name] = value
  }
  return { viewport: { width, height }, regions, screenshot: `genoffice-docs-${width}.png` }
}

async function captureApplication(electron, launchOptions, output, width, height, externalRequests) {
  const application = await electron.launch(launchOptions)
  const child = application.process()
  try {
    const page = await application.firstWindow({ timeout: 30_000 })
    await page.route('**/*', async (route) => {
      const protocol = new URL(route.request().url()).protocol
      if (['file:', 'data:', 'blob:'].includes(protocol)) await route.continue()
      else { externalRequests.push(route.request().url()); await route.abort() }
    })
    return await capture(page, output, width, height)
  } finally {
    const exited = new Promise((resolveExit) => child.once('exit', resolveExit))
    await application.evaluate(({ app }) => app.exit(0)).catch(() => {})
    const stopped = await Promise.race([exited.then(() => true), new Promise((resolveWait) => setTimeout(() => resolveWait(false), 5_000))])
    if (!stopped) child.kill('SIGTERM')
  }
}

export async function main(arguments_ = process.argv.slice(2)) {
  const parsed = options(arguments_)
  const output = confinedOutput(parsed.get('--output-root'))
  const source = realpathSync(resolve(parsed.get('--genoffice-source')))
  const docx = realpathSync(resolve(parsed.get('--docx')))
  if (git(source, 'rev-parse', 'HEAD') !== approvedCommit) throw new Error('GenOffice checkout commit is not approved')
  if (git(source, 'rev-parse', 'HEAD^{tree}') !== approvedTree) throw new Error('GenOffice checkout tree is not approved')
  if (git(source, 'status', '--porcelain', '--untracked-files=all')) throw new Error('GenOffice checkout must be clean')
  const mainEntry = resolve(source, 'apps/docs/out/main/index.js')
  if (!existsSync(mainEntry)) {
    const build = spawnSync('npm', ['run', 'build', '-w', '@genoffice/docs'], { cwd: source, encoding: 'utf8' })
    if (build.status !== 0) throw new Error(build.stderr.trim() || 'GenOffice Docs build failed')
  }
  mkdirSync(output, { recursive: false })
  const require = createRequire(resolve(source, 'package.json'))
  const { _electron: electron } = require('playwright-core')
  const electronExecutable = resolve(source, 'node_modules/electron/dist/Electron.app/Contents/MacOS/Electron')
  const externalRequests = []
  const launchOptions = {
    executablePath: electronExecutable,
    args: [mainEntry, docx],
    cwd: source,
    env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: process.env.HOME ?? '', LANG: 'ko_KR.UTF-8', ELECTRON_DISABLE_SECURITY_WARNINGS: 'true' },
  }
  const captures = [
    await captureApplication(electron, launchOptions, output, 1280, 820, externalRequests),
    await captureApplication(electron, launchOptions, output, 920, 640, externalRequests),
  ]
  const receipt = {
    schemaVersion: 1,
    lineage: 'pinned-genoffice-docs-fidelity-v1',
    upstream: { repository: 'https://github.com/genspark-ai/genoffice.git', commit: approvedCommit, tree: approvedTree },
    immutableInput: { clean: true, docx: { path: relative(root, docx), sha256: sha256(docx) } },
    runtime: { surface: 'Electron Docs', offline: externalRequests.length === 0, externalRequests, accountRequiredForCapture: false, gensparkProviderEnabledInUpstream: true, referenceProviderSurfaceExcluded: true },
    captures,
  }
  receipt.referenceSetHash = hashCanonical(receipt)
  writeFileSync(resolve(output, 'reference-receipt.json'), `${JSON.stringify(receipt, null, 2)}\n`)
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main().catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1 })
