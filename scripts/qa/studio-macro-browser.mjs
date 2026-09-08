#!/usr/bin/env node
import { spawnSync } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import http from 'node:http'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const resources = path.join(root, 'Resources')
const requireFromHarness = createRequire(path.join(root, '.omo', 'ac08-browser', 'package.json'))
const { chromium } = requireFromHarness('@playwright/test')
const binary = path.join(root, '.build', 'debug', 'PublicDocumentApp')
const mime = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
}

const arguments_ = process.argv.slice(2)
const value = (flag) => {
  const index = arguments_.indexOf(flag)
  return index >= 0 ? arguments_[index + 1] : undefined
}
const scenario = value('--scenario')
const evidenceDir = value('--evidence-dir')
if (!['happy', 'invalid', 'export'].includes(scenario) || !evidenceDir) {
  console.error('usage: studio-macro-browser.mjs --scenario happy|invalid|export --evidence-dir <path>')
  process.exit(2)
}
const evidence = path.resolve(root, evidenceDir)
const evidenceParent = path.dirname(evidence)
const physicalParent = fs.realpathSync(evidenceParent)
if (
  evidence !== root
  && !evidence.startsWith(`${root}${path.sep}`)
  || physicalParent !== root
    && !physicalParent.startsWith(`${root}${path.sep}`)
  || fs.existsSync(evidence)
) {
  console.error('evidence directory must be a new workspace-contained direct child')
  process.exit(2)
}
fs.mkdirSync(evidence)

const projectFixture = () => {
  const createdAt = '2026-08-28T15:00:00Z'
  const elements = [
    ['element-title', 'heading', '범피스 매크로 검증', 'style-title'],
    ['element-body', 'paragraph', '네모 개요\n원 대상\n바 세부\n당구 참고', 'style-body'],
    ['element-law', 'paragraph', '식물방역법', 'style-body'],
    ['element-amount', 'paragraph', '예산 12500000원 2026년', 'style-body'],
    ['element-insert', 'paragraph', '기본 ', 'style-body'],
    ['element-untouched', 'paragraph', '변경 금지 문장', 'style-body'],
  ].map(([elementID, kind, text, styleID], order) => ({
    elementID, kind, order, text, contentHTML: text, inlineIDs: [], styleID, evidenceIDs: [],
  }))
  elements.push({
    elementID: 'element-table',
    kind: 'table',
    order: elements.length,
    text: '구분 값 교육 95',
    contentHTML: '<table data-easy-table="true"><tbody><tr><th>구분</th><th>값</th></tr><tr><td>교육</td><td>95</td></tr></tbody></table>',
    inlineIDs: [],
    styleID: 'style-table',
    evidenceIDs: [],
  })
  return {
    schemaVersion: 1,
    documentID: 'document-macro-browser',
    locale: 'ko-KR',
    title: '범피스 매크로 검증',
    currentRevisionID: 'revision-macro-browser-1',
    elements,
    assets: [],
    styles: [],
    templateBinding: {
      templateID: 'public-draft',
      version: '1.0',
      publishingAuthority: '기관 표준',
      requiredSections: ['본문'],
      checklistResults: {},
    },
    evidenceLinks: [],
    revisions: [{
      revisionID: 'revision-macro-browser-1',
      createdAt,
      summary: 'macro-browser-fixture',
      elementIDs: elements.map((element) => element.elementID),
      snapshotElements: elements,
    }],
    history: [],
    aiProposalHistory: [],
    providerConfigurations: [],
    consentGrants: [],
    redoRevisionIDs: [],
  }
}

const startServer = async () => {
  const server = http.createServer((request, response) => {
    const requestURL = new URL(request.url || '/', 'http://127.0.0.1')
    const relative = decodeURIComponent(requestURL.pathname).replace(/^\/+/, '') || 'Studio/index.html'
    const file = path.resolve(resources, relative)
    if (file !== resources && !file.startsWith(`${resources}${path.sep}`)) {
      response.writeHead(403).end()
      return
    }
    try {
      const data = fs.readFileSync(file)
      response.writeHead(200, {
        'Content-Type': mime[path.extname(file)] || 'application/octet-stream',
        'Cache-Control': 'no-store',
      })
      response.end(data)
    } catch {
      response.writeHead(404).end()
    }
  })
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const address = server.address()
  return { server, url: `http://127.0.0.1:${address.port}/Studio/index.html` }
}

const closeServer = (server) => new Promise((resolve, reject) => {
  server.close((error) => error ? reject(error) : resolve())
})

const snapshot = (page) => page.evaluate(() => structuredClone(window.PublicDocumentStudio.state.currentProject))
const element = (project, id) => project.elements.find((item) => item.elementID === id)
const focus = (page, id) => page.evaluate((elementID) => {
  const editor = document.querySelector('public-document-genoffice-editor')
  return editor.focusElement(elementID)
}, id)
const tab = (page, name) => page.locator(`[data-tab="${name}"]`).click()
const click = (page, selector) => page.locator(selector).click()
const seed = async (page, project = projectFixture()) => {
  await page.evaluate((value_) => {
    window.__bridgeMessages = []
    window.projectStoreReceive({ event: 'opened', payload: { project: value_ } })
  }, project)
  await page.locator('public-document-genoffice-editor').waitFor({ state: 'visible' })
  return snapshot(page)
}
const bridgeAction = async (page, expectedAction, trigger, timeout = 10000) => {
  await page.evaluate(({ action, timeout }) => {
    window.__publicDocumentBridgeSignal = new Promise((resolve, reject) => {
      const listener = (event) => {
        if (event.detail?.action !== action) return
        window.removeEventListener('public-document-bridge-message', listener)
        clearTimeout(timer)
        resolve(event.detail)
      }
      const timer = setTimeout(() => {
        window.removeEventListener('public-document-bridge-message', listener)
        reject(new Error(`bridge action timed out: ${action}`))
      }, timeout)
      window.addEventListener('public-document-bridge-message', listener)
    })
  }, { action: expectedAction, timeout })
  await trigger()
  return page.evaluate(async () => window.__publicDocumentBridgeSignal)
}

const assert = (condition, message) => {
  if (!condition) throw new Error(message)
}

const runHappy = async (page, actions) => {
  const before = await seed(page)
  await tab(page, 'insert')
  assert(await focus(page, 'element-body'), 'body focus failed')
  await click(page, '[data-easy-action="apply-official-block"]')
  let current = await snapshot(page)
  assert(element(current, 'element-body').text === '□ 개요\n○ 대상\n- 세부\n※ 참고', 'block conversion failed')
  assert(element(current, 'element-body').contentHTML === element(current, 'element-body').text, 'block contentHTML is stale')
  assert(element(current, 'element-untouched').text === '변경 금지 문장', 'block conversion escaped focused selection')
  actions.push('focused block conversion')

  assert(await focus(page, 'element-law'), 'law focus failed')
  await click(page, '[data-easy-action="wrap-bracket"][data-easy-bracket="corner"]')
  assert(element(await snapshot(page), 'element-law').text === '「식물방역법」', 'corner bracket failed')
  actions.push('corner bracket')

  assert(await focus(page, 'element-amount'), 'amount focus failed')
  await click(page, '[data-easy-action="format-thousands"]')
  assert(element(await snapshot(page), 'element-amount').text === '예산 12,500,000원 2026년', 'thousands formatting failed')
  actions.push('thousands formatting')

  assert(await focus(page, 'element-insert'), 'insert focus failed')
  await click(page, '[data-easy-action="insert-date"]')
  await click(page, '[data-easy-action="insert-currency"]')
  await page.locator('[data-easy-fields] input[name="amount"]').fill('12500000')
  await click(page, '[data-easy-action="confirm-easy-tool"]')
  await click(page, '[data-easy-action="insert-attachment"]')
  await page.locator('[data-easy-fields] input[name="title"]').fill('성과지표')
  await page.locator('[data-easy-fields] input[name="copies"]').fill('1')
  await click(page, '[data-easy-action="confirm-easy-tool"]')
  await click(page, '[data-easy-action="insert-end-mark"]')
  actions.push('date currency attachment end')

  await tab(page, 'layout')
  await click(page, '[data-easy-action="page-margins"][data-easy-margin="official"]')
  current = await snapshot(page)
  assert(JSON.stringify(current.pageMargins) === JSON.stringify({ top: 20, right: 20, bottom: 10, left: 20 }), 'official margins failed')
  assert(element(current, 'element-insert').text.includes('12,500,000원(금일천이백오십만원정)'), 'currency insertion did not persist')
  assert(element(current, 'element-insert').text.includes('붙임 1. 성과지표 1부.'), 'attachment insertion did not persist')
  assert(element(current, 'element-insert').text.endsWith('끝.'), 'end mark did not persist')
  actions.push('official margins and persisted insertions')

  await tab(page, 'table')
  assert(await focus(page, 'element-table'), 'table focus failed')
  await click(page, '[data-easy-action="add-table-row"]')
  await click(page, '[data-easy-action="set-table-borders"]')
  current = await snapshot(page)
  assert((element(current, 'element-table').contentHTML.match(/<tr/g) || []).length === 3, 'table row macro failed')
  actions.push('table row and borders')

  await tab(page, 'insert')
  await click(page, '[data-easy-action="insert-report-structure"][data-easy-report="one-page"]')
  const withReport = await snapshot(page)
  const inserted = withReport.elements.filter((item) => item.elementID.startsWith('element-report-'))
  assert(inserted.length >= 5, 'one-page report structure was not inserted')
  actions.push('one-page report structure')

  await tab(page, 'home')
  await click(page, '[data-command="undo"]')
  const undone = await snapshot(page)
  assert(!undone.elements.some((item) => item.elementID.startsWith('element-report-')), 'project-level undo did not restore pre-macro state')
  actions.push('project-level undo')

  fs.writeFileSync(path.join(evidence, 'before-project.json'), `${JSON.stringify(before, null, 2)}\n`)
  fs.writeFileSync(path.join(evidence, 'after-project.json'), `${JSON.stringify(undone, null, 2)}\n`)
}

const runInvalid = async (page, actions) => {
  const before = await seed(page)
  await tab(page, 'insert')
  await page.evaluate(() => {
    window.PublicDocumentStudio.state.focusedEditorElementID = null
  })
  await click(page, '[data-easy-action="apply-marker"][data-easy-marker="circle"]')
  let current = await snapshot(page)
  assert(JSON.stringify(current.elements) === JSON.stringify(before.elements), 'empty focus changed the project')
  assert((await page.locator('.status-message').textContent()).includes('선택'), 'empty focus diagnostic missing')
  actions.push('empty focus rejected')

  assert(await focus(page, 'element-insert'), 'insert focus failed')
  await click(page, '[data-easy-action="insert-currency"]')
  await page.locator('[data-easy-fields] input[name="amount"]').fill('abc')
  await click(page, '[data-easy-action="confirm-easy-tool"]')
  assert((await page.locator('.status-message').textContent()).includes('숫자 금액'), 'invalid amount diagnostic missing')
  actions.push('invalid amount rejected')

  const noOpBefore = await snapshot(page)
  assert(await focus(page, 'element-untouched'), 'unsupported focus failed')
  await click(page, '[data-easy-action="apply-official-block"]')
  current = await snapshot(page)
  assert(JSON.stringify(current) === JSON.stringify(noOpBefore), 'unsupported block command created a revision')
  assert((await page.locator('.status-message').textContent()).includes('변경'), 'unsupported block diagnostic missing')
  actions.push('unsupported block rejected')
  fs.writeFileSync(path.join(evidence, 'unchanged-state.json'), `${JSON.stringify(current, null, 2)}\n`)
}

const runExport = async (page, actions) => {
  await seed(page)
  await tab(page, 'insert')
  assert(await focus(page, 'element-body'), 'body focus failed')
  await click(page, '[data-easy-action="apply-official-block"]')
  await tab(page, 'table')
  assert(await focus(page, 'element-table'), 'table focus failed')
  await click(page, '[data-easy-action="add-table-row"]')
  const savedMessage = await bridgeAction(
    page,
    'save',
    () => page.locator('[data-project-action="save"]').click(),
  )
  const saved = structuredClone(savedMessage.project)
  fs.writeFileSync(path.join(evidence, 'project.json'), `${JSON.stringify(saved, null, 2)}\n`)
  actions.push('browser macros saved')

  const exportRoot = path.join(evidence, 'export')
  fs.mkdirSync(exportRoot)
  const result = spawnSync(binary, [
    '--export-project',
    path.join(evidence, 'project.json'),
    exportRoot,
    '--formats',
    'docx',
    '--flattening-consent',
  ], { cwd: root, encoding: 'utf8' })
  assert(result.status === 0, `native export failed: ${result.stderr}`)
  const receipt = JSON.parse(result.stdout)
  fs.writeFileSync(path.join(evidence, 'receipt.json'), `${JSON.stringify(receipt, null, 2)}\n`)
  const docxResult = receipt.results.find((item) => item.format === 'docx')
  assert(docxResult && receipt.publishedFormats.includes('docx'), 'DOCX receipt is missing')
  const docx = path.join(exportRoot, docxResult.fileName)
  const document = spawnSync('/usr/bin/unzip', ['-p', docx, 'word/document.xml'], { encoding: 'utf8' })
  assert(document.status === 0, 'DOCX document.xml extraction failed')
  const xml = document.stdout
  const inspection = {
    status: ['□ 개요', '○ 대상', '- 세부', '※ 참고'].every((text) => xml.includes(text))
      && !xml.includes('네모 개요')
      && (xml.match(/<w:tr>/g) || []).length === 3
      ? 'pass'
      : 'fail',
    staleContentHTMLAbsent: !xml.includes('네모 개요'),
    officialMarkersPresent: ['□ 개요', '○ 대상', '- 세부', '※ 참고'].filter((text) => xml.includes(text)),
    tableRowCount: (xml.match(/<w:tr>/g) || []).length,
    docxSHA256: crypto.createHash('sha256').update(fs.readFileSync(docx)).digest('hex'),
    cleanup: 'browser closed; HTTP server closed; no temporary directories',
  }
  fs.writeFileSync(path.join(evidence, 'package-inspection.json'), `${JSON.stringify(inspection, null, 2)}\n`)
  assert(inspection.status === 'pass', 'browser-applied macro output did not persist to DOCX')
  actions.push('saved project exported and inspected')
}

let browser
let server
let page
const actions = []
const log = {
  schemaVersion: 1,
  scenario,
  status: 'fail',
  actions,
  cleanup: {},
}
try {
  const build = spawnSync('swift', ['build', '--product', 'PublicDocumentApp'], {
    cwd: root,
    encoding: 'utf8',
  })
  assert(build.status === 0, `Swift build failed: ${build.stderr}`)
  log.runtime = {
    swiftBuild: 'pass',
    binarySHA256: crypto.createHash('sha256').update(fs.readFileSync(binary)).digest('hex'),
  }
  actions.push('current Swift product built')
  const running = await startServer()
  server = running.server
  browser = await chromium.launch({ channel: 'chrome', headless: true })
  const context = await browser.newContext({ viewport: { width: 1280, height: 820 } })
  page = await context.newPage()
  await page.addInitScript(() => {
    window.__bridgeMessages = []
    window.webkit = {
      messageHandlers: {
        projectStore: {
          postMessage(message) {
            const cloned = structuredClone(message)
            window.__bridgeMessages.push(cloned)
            window.dispatchEvent(new CustomEvent('public-document-bridge-message', {
              detail: cloned,
            }))
          },
        },
      },
    }
  })
  await page.goto(running.url, { waitUntil: 'networkidle' })
  await page.locator('public-document-genoffice-editor[data-runtime="ready"]').waitFor({ state: 'visible' })
  if (scenario === 'happy') await runHappy(page, actions)
  if (scenario === 'invalid') await runInvalid(page, actions)
  if (scenario === 'export') await runExport(page, actions)
  await page.screenshot({ path: path.join(evidence, 'screenshot.png'), fullPage: false })
  log.status = 'pass'
} catch (error) {
  log.error = error instanceof Error ? error.message : String(error)
  if (page) {
    try {
      await page.screenshot({ path: path.join(evidence, 'screenshot.png'), fullPage: false })
    } catch {}
  }
  process.exitCode = 1
} finally {
  const cleanupErrors = []
  if (browser) {
    try {
      await browser.close()
      log.cleanup.browser = 'closed'
    } catch (error) {
      cleanupErrors.push(`browser: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
  if (server) {
    try {
      await closeServer(server)
      log.cleanup.httpServer = 'closed'
    } catch (error) {
      cleanupErrors.push(`httpServer: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
  log.cleanup.temporaryDirectories = 'none'
  if (cleanupErrors.length) {
    log.cleanup.errors = cleanupErrors
    log.status = 'fail'
    process.exitCode = 1
  }
  fs.writeFileSync(path.join(evidence, 'action-log.json'), `${JSON.stringify(log, null, 2)}\n`)
}
