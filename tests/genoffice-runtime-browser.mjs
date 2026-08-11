import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const root = resolve(import.meta.dirname, '..')
const dependencyRoot = process.env['GENOFFICE_DEPENDENCY_ROOT'] ?? '/tmp/public-document-genoffice-build.kPjYnB'
const { chromium, webkit } = await import(pathToFileURL(join(dependencyRoot, 'node_modules/playwright-core/index.mjs')).href)
const evidence = join(root, '.omo/evidence/genoffice-runtime/browser')
mkdirSync(evidence, { recursive: true })

const project = {
  elements: [
    { elementID: 'heading-1', kind: 'heading', text: '공공문서 제목', contentHTML: '<b>공공문서</b> 제목' },
    { elementID: 'body-1', kind: 'paragraph', text: '첫 문장 강조 문장 기울임 문장', contentHTML: '<span data-inline-id="inline-alpha">첫 문장 </span><strong data-inline-id="inline-bravo">강조 문장 </strong><em data-inline-id="inline-charlie">기울임 문장</em>' },
    { elementID: 'approval-1', kind: 'approval-grid', text: '담당 팀장 과장 김○○', contentHTML: '<span>담당</span><span>팀장</span><span>과장</span><b>김○○</b><b></b><b></b>' },
    { elementID: 'table-1', kind: 'table', text: '항목 값 연간 생활안전 시설 점검 예산 100백만원', contentHTML: '<tbody><tr><th>항목</th><th>값</th></tr><tr><td>연간 생활안전 시설 점검 예산</td><td>100백만원</td></tr></tbody>' },
  ],
}

async function verify(browserType, name, launchOptions = {}) {
  const browser = await browserType.launch({ headless: true, ...launchOptions })
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  const errors = []
  const requests = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('request', (request) => { if (!request.url().startsWith('data:') && !request.url().startsWith('file:')) requests.push(request.url()) })
  await page.setContent('<style>:root{--studio-ink:#202726;--studio-panel:#f7f9f8;--studio-border-strong:#b7c1be;--studio-accent-strong:#005361;--studio-accent-soft:#e8f4f5;--studio-accent-border:#afd1d5;--studio-border:#d7dddb;--studio-muted:#66706d;--studio-surface:#fff;--studio-document-fill:#eef4f3;--studio-document-rule:#7f8986}</style><public-document-genoffice-editor></public-document-genoffice-editor>')
  await page.addScriptTag({ path: join(root, 'Resources/GenOffice/public-document-genoffice.js') })
  await page.waitForFunction(() => customElements.get('public-document-genoffice-editor'))
  const initial = await page.locator('public-document-genoffice-editor').evaluate((editor, value) => {
    editor.setProject(value)
    return { elements: editor.getElements(), focused: editor.focusElement('body-1') }
  }, project)
  assert.equal(initial.focused, true)
  assert.deepEqual(initial.elements.map((item) => item.id), project.elements.map((item) => item.elementID))
  assert.deepEqual([...initial.elements[1].contentHTML.matchAll(/data-inline-id="([^"]+)"/g)].map((match) => match[1]), ['inline-alpha', 'inline-bravo', 'inline-charlie'])
  const initialInlineSegments = await page.locator('public-document-genoffice-editor').evaluate((editor) => {
    const body = new DOMParser().parseFromString(editor.getElements()[1].contentHTML, 'text/html').body
    return [...body.querySelectorAll('[data-inline-id]')].map((node) => ({
      id: node.getAttribute('data-inline-id'),
      text: node.textContent,
      bold: node.matches('b,strong') || Boolean(node.querySelector('b,strong')) || Boolean(node.parentElement?.closest('b,strong')),
      italic: node.matches('i,em') || Boolean(node.querySelector('i,em')) || Boolean(node.parentElement?.closest('i,em')),
    }))
  })
  assert.deepEqual(initialInlineSegments, [
    { id: 'inline-alpha', text: '첫 문장 ', bold: false, italic: false },
    { id: 'inline-bravo', text: '강조 문장 ', bold: true, italic: false },
    { id: 'inline-charlie', text: '기울임 문장', bold: false, italic: true },
  ])
  const selectionHost = page.locator('public-document-genoffice-editor')
  await selectionHost.evaluate((editor) => {
    window.__selectionStates = []
    editor.addEventListener('public-document-genoffice-selection-change', (event) => window.__selectionStates.push(event.detail))
    editor.focusElement('body-1')
  })
  assert.deepEqual(await selectionHost.evaluate((editor) => editor.getSelectionState()), { elementID: 'body-1', bold: false, italic: false, underline: false })
  for (let index = 0; index < 7; index += 1) await page.locator('public-document-genoffice-editor .ProseMirror').press('Shift+ArrowRight')
  assert.equal((await selectionHost.evaluate((editor) => editor.getSelectionState())).bold, false)
  assert.equal(await selectionHost.evaluate((editor) => editor.command('bold')), true)
  assert.equal((await selectionHost.evaluate((editor) => editor.getSelectionState())).bold, true)
  const boldSnapshot = await selectionHost.evaluate((editor) => editor.getElements())
  await selectionHost.evaluate((editor, elements) => editor.setProject({ elements: elements.map((item) => ({ elementID: item.id, kind: item.type, text: item.text, contentHTML: item.contentHTML })) }), boldSnapshot)
  await selectionHost.evaluate((editor) => editor.focusElement('body-1'))
  for (let index = 0; index < 7; index += 1) await page.locator('public-document-genoffice-editor .ProseMirror').press('Shift+ArrowRight')
  assert.equal((await selectionHost.evaluate((editor) => editor.getSelectionState())).bold, true)
  assert.equal(await selectionHost.evaluate((editor) => editor.command('bold')), true)
  assert.equal((await selectionHost.evaluate((editor) => editor.getSelectionState())).bold, false)
  assert.ok((await page.evaluate(() => window.__selectionStates)).length > 0)
  await selectionHost.evaluate((editor, value) => editor.setProject(value), project)
  await page.locator('public-document-genoffice-editor .nav-item').first().click()
  assert.equal(await page.locator('public-document-genoffice-editor').evaluate((editor) => editor.command('insertText', '[NAV]')), true)
  assert.match((await page.locator('public-document-genoffice-editor').evaluate((editor) => editor.getElements()))[0].text, /\[NAV\]/)
  assert.equal(await page.locator('public-document-genoffice-editor').evaluate((editor) => editor.focusElement('body-1')), true)
  await page.locator('public-document-genoffice-editor .ProseMirror').press('End')
  await page.keyboard.type(' 편집')
  const commandResults = await page.locator('public-document-genoffice-editor').evaluate((editor) => [
    editor.command('fontName', 'Apple SD Gothic Neo'),
    editor.command('fontSize', 14),
    editor.command('bold'),
    editor.command('italic'),
    editor.command('underline'),
    editor.command('justifyCenter'),
    editor.command('insertText', '[확인 필요]'),
    editor.command('insertUnorderedList'),
  ])
  assert.ok(commandResults.every(Boolean))
  const edited = await page.locator('public-document-genoffice-editor').evaluate((editor) => editor.getElements())
  assert.deepEqual(edited.map((item) => item.id), project.elements.map((item) => item.elementID))
  assert.deepEqual(edited.map((item) => item.type), ['heading', 'list-item', 'approval-grid', 'table'])
  assert.deepEqual(edited[1].inlineIDs, ['inline-alpha', 'inline-bravo', 'inline-charlie'])
  const inlineSegments = await page.locator('public-document-genoffice-editor').evaluate((editor) => {
    const body = new DOMParser().parseFromString(editor.getElements()[1].contentHTML, 'text/html').body
    return [...body.querySelectorAll('[data-inline-id]')].map((node) => ({
      id: node.getAttribute('data-inline-id'),
      text: node.textContent,
      bold: node.matches('b,strong') || Boolean(node.querySelector('b,strong')) || Boolean(node.parentElement?.closest('b,strong')),
      italic: node.matches('i,em') || Boolean(node.querySelector('i,em')) || Boolean(node.parentElement?.closest('i,em')),
    }))
  })
  assert.deepEqual(inlineSegments.map((item) => [item.id, item.text]), [['inline-alpha', '첫 문장 '], ['inline-bravo', '강조 문장 '], ['inline-charlie', '기울임 문장']])
  assert.equal(inlineSegments.find((item) => item.id === 'inline-bravo').bold, true)
  assert.equal(inlineSegments.find((item) => item.id === 'inline-charlie').italic, true)
  assert.match(edited[1].contentHTML, /font-size:\s*14pt/)
  assert.match(edited[1].contentHTML, /data-public-document-align="center"/)
  assert.match(edited[1].text, /\[확인 필요\]/)
  assert.match(edited[2].contentHTML, /담당.*팀장.*과장.*김○○/s)
  assert.match(edited[3].contentHTML, /<th[^>]*>.*항목.*<\/th>/s)
  await page.locator('public-document-genoffice-editor').evaluate((editor, elements) => editor.setProject({ elements: elements.map((item) => ({ elementID: item.id, kind: item.type, text: item.text, contentHTML: item.contentHTML })) }), edited)
  const reopened = await page.locator('public-document-genoffice-editor').evaluate((editor) => editor.getElements())
  assert.deepEqual(reopened.map((item) => item.id), project.elements.map((item) => item.elementID))
  assert.equal(reopened[1].type, 'list-item')
  assert.deepEqual(reopened[1].inlineIDs, ['inline-alpha', 'inline-bravo', 'inline-charlie'])
  assert.equal(edited[1].contentHTML, reopened[1].contentHTML)
  assert.match(reopened[1].contentHTML, /font-size:\s*14pt/)
  assert.equal(errors.length, 0)
  assert.equal(requests.length, 0)
  await page.locator('public-document-genoffice-editor').evaluate((editor, value) => editor.setProject(value), project)
  await page.screenshot({ path: join(evidence, `${name}-editor.png`), fullPage: true })
  await page.setViewportSize({ width: 920, height: 900 })
  await page.screenshot({ path: join(evidence, `${name}-editor-920.png`), fullPage: true })
  await browser.close()
  return { name, ids: reopened.map((item) => item.id), inlineIDs: reopened[1].inlineIDs, inlineSegments, commandResults, errors, externalRequests: requests }
}

const results = [await verify(chromium, 'chrome', { channel: 'chrome' }), await verify(webkit, 'webkit')]
process.stdout.write(`${JSON.stringify({ schemaVersion: 1, results }, null, 2)}\n`)
