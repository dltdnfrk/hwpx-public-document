import assert from 'node:assert/strict'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import test from 'node:test'

const root = resolve(import.meta.dirname, '..')
const dependencyRoot = process.env['GENOFFICE_DEPENDENCY_ROOT'] ?? '/tmp/public-document-genoffice-build.kPjYnB'
const { chromium, webkit } = await import(pathToFileURL(join(dependencyRoot, 'node_modules/playwright-core/index.mjs')).href)
const evidence = resolve(process.env['GENOFFICE_EVIDENCE_DIR'] ?? join(root, '.omo/evidence/genoffice-adapter-regressions'))
mkdirSync(evidence, { recursive: true })
const fixture = { elements: [
  { elementID: 'title', kind: 'title', text: 'Untouched title', contentHTML: 'Untouched title' },
  { elementID: 'body', kind: 'paragraph', text: 'alpha TARGET omega', contentHTML: 'alpha TARGET omega' },
] }

for (const [name, browserType, options] of [['chrome', chromium, { channel: 'chrome' }], ['webkit', webkit, {}]]) {
  await test(`${name}: shipped adapter selection and text preservation`, async (t) => {
    const browser = await browserType.launch({ headless: true, ...options })
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' })
    const page = await context.newPage()
    const actions = []
    const errors = []
    const externalRequests = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => { if (!/^(data|file|about):/.test(request.url())) externalRequests.push(request.url()) })
    const host = page.locator('public-document-genoffice-editor')
    const editable = page.locator('public-document-genoffice-editor .ProseMirror')
    const snapshot = () => host.evaluate((editor) => editor.getElements())
    const reset = (value = fixture) => host.evaluate((editor, project) => editor.setProject(project), value)
    const command = async (commandName, value) => {
      const result = await host.evaluate((editor, args) => editor.command(...args), [commandName, value])
      actions.push({ action: 'command', commandName, value, result, elements: await snapshot() })
      assert.equal(result, true)
    }
    const pressSelection = async (key) => {
      await host.evaluate((editor) => {
        window.keyboardSelection = new Promise((resolve, reject) => {
          const listener = () => { clearTimeout(timeout); resolve() }
          const timeout = setTimeout(() => { editor.removeEventListener('public-document-genoffice-selection-change', listener); reject(new Error('Keyboard selection event timed out')) }, 5000)
          editor.addEventListener('public-document-genoffice-selection-change', listener, { once: true })
        })
      })
      await editable.press(key)
      await page.evaluate(() => window.keyboardSelection)
    }
    const selectTarget = async () => {
      await host.evaluate((editor) => editor.focusElement('body'))
      for (let i = 0; i < 6; i += 1) await pressSelection('ArrowRight')
      for (let i = 0; i < 6; i += 1) await pressSelection('Shift+ArrowRight')
      actions.push({ action: 'keyboard-select', text: await page.evaluate(() => window.getSelection().toString()) })
      assert.equal(await page.evaluate(() => window.getSelection().toString()), 'TARGET')
    }
    const capture = (label) => page.screenshot({ path: join(evidence, `${name}-${label}.png`), fullPage: true })
    const markedText = (selector) => host.evaluate((editor, selector) => {
      const body = new DOMParser().parseFromString(editor.getElements()[1].contentHTML, 'text/html').body
      return [...body.querySelectorAll(selector)].map((node) => node.textContent).join('')
    }, selector)
    try {
      await page.setContent('<style>:root{--studio-ink:#202726;--studio-panel:#f7f9f8;--studio-border-strong:#b7c1be;--studio-accent-strong:#005361;--studio-accent-soft:#e8f4f5;--studio-accent-border:#afd1d5;--studio-border:#d7dddb;--studio-muted:#66706d;--studio-surface:#fff;--studio-document-fill:#eef4f3;--studio-document-rule:#7f8986}button{padding:8px}</style><button id="bold">Bold</button><public-document-genoffice-editor></public-document-genoffice-editor>')
      await page.addScriptTag({ path: process.env['GENOFFICE_BROWSER_BUNDLE'] ?? join(root, 'Resources/GenOffice/public-document-genoffice.js') })
      await page.evaluate(() => {
        document.querySelector('#bold').onclick = () => document.querySelector('public-document-genoffice-editor').command('bold')
      })
      await t.test('Given a pointer-selected body word When the toolbar is clicked Then only that word changes, not the title', async () => {
        await reset()
        const point = await page.locator('public-document-genoffice-editor .ProseMirror > p').evaluate((paragraph) => {
          const range = document.createRange()
          range.setStart(paragraph.firstChild, 6)
          range.setEnd(paragraph.firstChild, 12)
          const rect = range.getBoundingClientRect()
          return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 }
        })
        await host.evaluate((editor) => {
          window.pointerSelection = new Promise((resolve, reject) => {
            const timeout = setTimeout(() => { editor.removeEventListener('public-document-genoffice-selection-change', listener); reject(new Error('Pointer selection event timed out')) }, 5000)
            const listener = (event) => {
              if (event.detail.elementID !== 'body' || window.getSelection().toString() !== 'TARGET') return
              clearTimeout(timeout)
              editor.removeEventListener('public-document-genoffice-selection-change', listener)
              resolve(event.detail)
            }
            editor.addEventListener('public-document-genoffice-selection-change', listener)
          })
        })
        await page.mouse.dblclick(point.x, point.y)
        const selected = await page.evaluate(() => window.pointerSelection)
        actions.push({ action: 'pointer-double-click', point, selected, text: await page.evaluate(() => window.getSelection().toString()) })
        await capture('pointer-selected')
        assert.equal(await page.evaluate(() => window.getSelection().toString()), 'TARGET')
        await page.locator('#bold').click()
        actions.push({ action: 'toolbar-click', elements: await snapshot() })
        await capture('pointer-formatted')
        assert.equal((await snapshot())[0].contentHTML, fixture.elements[0].contentHTML)
        assert.equal(await markedText('strong,b'), 'TARGET')
      })
      for (const [commandName, value, selector] of [['bold', undefined, 'strong,b'], ['italic', undefined, 'em,i'], ['underline', undefined, 'u'], ['fontSize', 18, '[style*="font-size"]'], ['fontName', 'Arial', '[style*="font-family"]']]) {
        await t.test(`Given a substring selection When ${commandName} is applied Then adjacent text is unchanged`, async () => {
          await reset()
          await selectTarget()
          await command(commandName, value)
          assert.equal(await markedText(selector), 'TARGET')
          assert.equal((await snapshot())[1].text, fixture.elements[1].text)
          if (['bold', 'italic', 'underline'].includes(commandName)) {
            await command(commandName)
            assert.equal(await markedText(selector), '')
          }
        })
      }
      await t.test('Given a collapsed selection When a whole-block formatting macro runs Then the full focused block is formatted', async () => {
        await reset()
        await host.evaluate((editor) => editor.focusElement('body'))
        await command('bold')
        assert.equal(await markedText('strong,b'), fixture.elements[1].text)
        assert.equal((await snapshot())[0].contentHTML, fixture.elements[0].contentHTML)
      })
      await t.test('Given a mid-block caret When insertText runs Then it inserts there and advances the caret', async () => {
        await reset()
        await host.evaluate((editor) => editor.focusElement('body'))
        for (let i = 0; i < 6; i += 1) await pressSelection('ArrowRight')
        await command('insertText', '[ONE]')
        await command('insertText', '[TWO]')
        await capture('mid-cursor-insert')
        assert.equal((await snapshot())[1].text, 'alpha [ONE][TWO]TARGET omega')
      })
      await t.test('Given a selected word When insertText runs Then it replaces only that word', async () => {
        await reset()
        await selectTarget()
        await command('insertText', 'replacement')
        assert.equal((await snapshot())[1].text, 'alpha replacement omega')
      })
      for (const [label, contentHTML, expected] of [
        ['consecutive-breaks', 'first<br><br><strong>second</strong><br><br>', 'first\n\nsecond\n\n'],
        ['nested-blocks', '<div>first<div>second</div>third</div><p>fourth</p>', 'first\nsecond\nthird\nfourth'],
        ['empty-blocks', '<p>first</p><p></p><p>third</p>', 'first\n\nthird'],
        ['literal-fallback', '', '<literal> & plain\n\ntext'],
        ['escaped-literal-newlines', '&lt;literal&gt; &amp; plain\n\ntext', '<literal> & plain\n\ntext'],
      ]) {
        await t.test(`Given ${label} When serialized and reopened twice Then authored text and separators survive`, async () => {
          await reset({ elements: [{ elementID: 'body', kind: 'paragraph', text: expected, contentHTML }] })
          const initial = await snapshot()
          actions.push({ action: 'load-roundtrip', label, elements: initial })
          await capture(label)
          assert.equal(initial[0].text, expected)
          assert.equal((initial[0].contentHTML.match(/<br\b/g) ?? []).length, (expected.match(/\n/g) ?? []).length)
          for (let i = 0; i < 2; i += 1) {
            const elements = await snapshot()
            await reset({ elements: elements.map((item) => ({ elementID: item.id, kind: item.type, text: item.text, contentHTML: item.contentHTML })) })
            const reopened = await snapshot()
            actions.push({ action: 'reopen', label, elements: reopened })
            assert.equal(reopened[0].text, expected)
            assert.equal(reopened[0].contentHTML, initial[0].contentHTML)
          }
        })
      }
      assert.deepEqual(errors, [])
      assert.deepEqual(externalRequests, [])
    } finally {
      await context.close()
      await browser.close()
      writeFileSync(join(evidence, `${name}-actions.json`), `${JSON.stringify({ actions, errors, externalRequests, cleanup: { contextClosed: true, browserClosed: !browser.isConnected(), persistentProfileUsed: false } }, null, 2)}\n`)
    }
  })
}
