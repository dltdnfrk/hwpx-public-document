const studioURL = __STUDIO_URL__
const evidence = __EVIDENCE_DIR__
const injected = __INJECTED_ELEMENTS__
const expectedTitle = __EXPECTED_TITLE__
const log = []
const step = (id, status, detail) => {
  const row = { id, status, detail, at: new Date().toISOString() }
  log.push(row)
  console.log(JSON.stringify(row))
  return row
}
const waitFor = async (page, selector, timeout = 15000) => {
  const loc = page.locator(selector)
  if (typeof loc.waitFor !== 'function') throw new Error('locator.waitFor unavailable: ' + selector)
  await loc.waitFor({ state: 'visible', timeout })
  return loc
}
const textOf = async (page, selector) => {
  const loc = page.locator(selector).first()
  if (typeof loc.innerText === 'function') return (await loc.innerText()).trim()
  return String(await loc.textContent() || '').trim()
}
const clickCss = async (page, selector) => {
  await waitFor(page, selector)
  await page.locator(selector).first().click()
}
const armMutationSignal = async (page, key, kind, expected = null, timeout = 15000) => {
  await page.evaluate(({ key, kind, expected, timeout }) => {
    const ready = () => {
      if (kind === 'draft') {
        return /기안문/.test(document.querySelector('.panel-heading h2')?.textContent || '')
      }
      if (kind === 'content') {
        const studio = window.PublicDocumentStudio
        const project = studio && studio.state && studio.state.currentProject
        const host = document.querySelector('public-document-genoffice-editor')
        const editorText = host && host.shadowRoot ? String(host.shadowRoot.textContent || '') : ''
        const engine = window.PublicDocumentPageEngine
        const layout = engine && project ? engine.paginateProject(project) : null
        return project && project.title === expected && editorText.includes('제언 요지') && layout && layout.pageCount >= 3
      }
      if (kind === 'preview-on') {
        const preview = document.querySelector('[data-page-preview]')
        return preview && !preview.hidden && preview.querySelectorAll('.page-preview-sheet').length >= 3
      }
      if (kind === 'preview-off') {
        const preview = document.querySelector('[data-page-preview]')
        const canvas = document.querySelector('.canvas')
        return preview && preview.hidden && canvas && !canvas.classList.contains('page-preview-open')
      }
      if (kind === 'export') {
        const dialog = document.querySelector('dialog.export-result')
        const summary = document.querySelector('#export-summary')
        return dialog && dialog.open && String(summary?.textContent || '').trim().length > 0
      }
      return false
    }
    window.__publicDocumentQASignals ||= {}
    window.__publicDocumentQASignals[key] = new Promise((resolve, reject) => {
      if (ready()) {
        resolve(true)
        return
      }
      const observer = new MutationObserver(() => {
        if (!ready()) return
        observer.disconnect()
        clearTimeout(timer)
        resolve(true)
      })
      const timer = setTimeout(() => {
        observer.disconnect()
        reject(new Error(`QA mutation signal timed out: ${key}`))
      }, timeout)
      observer.observe(document.documentElement, {
        attributes: true,
        characterData: true,
        childList: true,
        subtree: true,
      })
    })
  }, { key, kind, expected, timeout })
}
const armIntersectionSignal = async (page, key, selector, timeout = 5000) => {
  await page.evaluate(({ key, selector, timeout }) => {
    const target = document.querySelector(selector)
    if (!target) throw new Error(`QA intersection target missing: ${selector}`)
    window.__publicDocumentQASignals ||= {}
    window.__publicDocumentQASignals[key] = new Promise((resolve, reject) => {
      const observer = new IntersectionObserver((entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return
        observer.disconnect()
        clearTimeout(timer)
        resolve(true)
      })
      const timer = setTimeout(() => {
        observer.disconnect()
        reject(new Error(`QA intersection signal timed out: ${key}`))
      }, timeout)
      observer.observe(target)
    })
  }, { key, selector, timeout })
}
const awaitSignal = async (page, key) => page.evaluate(
  async (signalKey) => window.__publicDocumentQASignals[signalKey],
  key,
)
const closeOpenDialogs = async (page) => {
  for (const sel of [
    '[data-action="close-draft-wizard"]',
    '[data-action="close-export-result"]',
    '[data-action="close-export-setup"]',
    '[data-action="close-easy-tool"]',
  ]) {
    const loc = page.locator(sel)
    if (await loc.count()) {
      const visible = await loc.first().isVisible().catch(() => false)
      if (visible) {
        await loc.first().click()
        await loc.first().waitFor({ state: 'hidden', timeout: 5000 })
      }
    }
  }
}
const previewState = async (page) => page.evaluate(() => {
  const preview = document.querySelector('[data-page-preview]')
  const canvas = document.querySelector('.canvas')
  const toggle = document.querySelector('[data-view-action="toggle-page-preview"]')
  const sheets = preview ? preview.querySelectorAll('.page-preview-sheet').length : 0
  const first = preview && preview.querySelector('[data-preview-page="1"]')
  const last = preview && preview.querySelector('.page-preview-sheet:last-child')
  const body = document.querySelector('public-document-genoffice-editor')
  const root = body && body.shadowRoot
  const pageBreaks = root ? root.querySelectorAll('.page-engine-break, [data-page-break]').length : 0
  const editorText = root ? String(root.textContent || '') : ''
  return {
    hidden: preview ? preview.hidden : null,
    ariaHidden: preview ? preview.getAttribute('aria-hidden') : null,
    canvasOpen: canvas ? canvas.classList.contains('page-preview-open') : false,
    pressed: toggle ? toggle.getAttribute('aria-pressed') : null,
    sheets,
    pageBreaks,
    firstText: first ? String(first.textContent || '').slice(0, 180) : '',
    lastPage: last ? last.getAttribute('data-preview-page') : '',
    lastText: last ? String(last.textContent || '').slice(0, 180) : '',
    editorHasTitle: editorText.indexOf('과수화상병') >= 0,
    editorHasEnd: editorText.indexOf('끝') >= 0,
    previewHTML: preview ? preview.innerHTML.slice(0, 500) : '',
  }
})

const tabs = await listBrowserTabs()
const studioTabs = tabs.filter((tab) => String(tab.url || '').includes('127.0.0.1:8766/Studio'))
step('C1-tabs', 'PASS', { total: tabs.length, studio8766: studioTabs.length, leftoverIgnored: studioTabs.length })

const pageS = await openTab(studioURL)
step('C2-open', 'PASS', studioURL.split('#')[0])
await waitFor(pageS, '[data-action="open-export"]', 25000)
await waitFor(pageS, '.catalog-entries button[data-template-id="public-draft"]', 25000)
const titleC2 = await textOf(pageS, '.brand-lockup')
const statusC2 = await textOf(pageS, '.status-message')
if (!/문서작성기|공공문서 작성기|Public Document Studio/.test(titleC2)) {
  throw new Error('C2 title missing: ' + titleC2)
}
if (/불러오지 못해/.test(statusC2)) throw new Error('C2 genoffice failed: ' + statusC2)
await pageS.screenshot({ path: evidence + '/c2-studio.png' })
step('C2-snapshot', 'PASS', { titleC2, statusC2 })

await armMutationSignal(pageS, 'draft-applied', 'draft')
await clickCss(pageS, '.catalog-entries button[data-template-id="public-draft"]')
await awaitSignal(pageS, 'draft-applied')
await closeOpenDialogs(pageS)
const headingC3 = await textOf(pageS, '.panel-heading h2')
if (!/기안문/.test(headingC3)) throw new Error('C3 draft not applied heading=' + headingC3)
step('C3-draft', 'PASS', { headingC3 })

await armMutationSignal(pageS, 'content-rendered', 'content', expectedTitle)
const injectedState = await pageS.evaluate(({ elements, title }) => {
  const studio = window.PublicDocumentStudio
  if (!studio || typeof studio.commitProjectElements !== 'function') {
    return { ok: false, reason: 'commitProjectElements missing' }
  }
  if (studio.dom && studio.dom.titleInput) studio.dom.titleInput.value = title
  studio.commitProjectElements(elements, 'content-trial', '정책 제언문을 넣었습니다.', { title })
  const project = studio.state && studio.state.currentProject
  const engine = window.PublicDocumentPageEngine
  const layout = engine && project ? engine.paginateProject(project) : null
  return {
    ok: true,
    title: project && project.title,
    elementCount: project && project.elements ? project.elements.length : 0,
    sample: (project && project.elements || []).slice(0, 4).map((item) => item.text),
    pageCount: layout && layout.pageCount,
    tokenID: layout && layout.tokenID,
    firstPageBlocks: layout && layout.pages && layout.pages[0] ? layout.pages[0].blocks.map((block) => block.id) : [],
    lastPageBlocks: layout && layout.pages && layout.pages.length
      ? layout.pages[layout.pages.length - 1].blocks.map((block) => block.id)
      : [],
  }
}, { elements: injected, title: expectedTitle })
if (!injectedState.ok) throw new Error('C4 inject failed: ' + JSON.stringify(injectedState))
await awaitSignal(pageS, 'content-rendered')
const headingC4 = await textOf(pageS, '.panel-heading h2')
const statusC4 = await textOf(pageS, '.status-message')
const outlineC4 = String(await pageS.locator('.outline-list').innerText())
const pageStatusC4 = await textOf(pageS, '[data-page-status]').catch(() => '')
const editorC4 = await pageS.evaluate(() => {
  const host = document.querySelector('public-document-genoffice-editor')
  const root = host && host.shadowRoot
  const title = document.querySelector('#document-title, [data-title-input], .title-input, input[name="title"]')
  return {
    editorText: root ? String(root.textContent || '') : '',
    titleValue: title ? String(title.value || title.textContent || '') : '',
  }
})
if (String(injectedState.title || '').indexOf('과수화상병') < 0 && editorC4.titleValue.indexOf('과수화상병') < 0 && editorC4.editorText.indexOf('과수화상병') < 0) {
  throw new Error('C4 title missing heading=' + headingC4 + ' title=' + injectedState.title + ' editor=' + editorC4.editorText.slice(0, 200))
}
if (editorC4.editorText.indexOf('제언 요지') < 0 || editorC4.editorText.indexOf('결론') < 0) {
  throw new Error('C4 editor missing policy text: ' + editorC4.editorText.slice(0, 400))
}
if (!injectedState.pageCount || injectedState.pageCount < 3) {
  throw new Error('C4 expected multi-page layout, got ' + injectedState.pageCount)
}
await pageS.screenshot({ path: evidence + '/c4-content.png' })
step('C4-inject', 'PASS', {
  headingC4,
  statusC4,
  pageStatusC4,
  outline: outlineC4.slice(0, 400),
  editorSample: editorC4.editorText.slice(0, 240),
  titleValue: editorC4.titleValue,
  injectedState,
})

await clickCss(pageS, '.ribbon-tab[data-tab="view"]')
await waitFor(pageS, '[data-view-action="toggle-page-preview"]')
const noteBefore = await textOf(pageS, '[data-view-page-note]')
const statusBefore = await textOf(pageS, '[data-page-status]')
await armMutationSignal(pageS, 'preview-opened', 'preview-on')
await clickCss(pageS, '[data-view-action="toggle-page-preview"]')
await awaitSignal(pageS, 'preview-opened')
const previewOn = await previewState(pageS)
const liveCount = await pageS.evaluate(() => {
  const studio = window.PublicDocumentStudio
  const engine = window.PublicDocumentPageEngine
  const project = studio && studio.state && studio.state.currentProject
  return engine && project ? engine.pageCountForProject(project) : 0
})
if (previewOn.hidden || !previewOn.canvasOpen || previewOn.pressed !== 'true' || previewOn.sheets < 3 || previewOn.sheets !== liveCount) {
  throw new Error('C5 preview on unexpected ' + JSON.stringify(previewOn) + ' liveCount=' + liveCount)
}
if (previewOn.firstText.indexOf('과수화상병') < 0) {
  throw new Error('C5 first preview sheet missing title: ' + previewOn.firstText)
}
if (noteBefore.indexOf('한컴 쪽 나누기를 대체하지 않습니다') < 0) {
  throw new Error('C5 dishonest page copy note=' + noteBefore)
}
await pageS.screenshot({ path: evidence + '/c5-preview.png' })
await armIntersectionSignal(pageS, 'last-preview-visible', '.page-preview-sheet:last-child')
await pageS.evaluate(() => {
  const last = document.querySelector('.page-preview-sheet:last-child')
  if (last) last.scrollIntoView({ block: 'start' })
})
await awaitSignal(pageS, 'last-preview-visible')
await pageS.screenshot({ path: evidence + '/c5-preview-last.png' })
await armMutationSignal(pageS, 'preview-closed', 'preview-off')
await clickCss(pageS, '[data-view-action="toggle-page-preview"]')
await awaitSignal(pageS, 'preview-closed')
const previewOff = await previewState(pageS)
if (!previewOff.hidden || previewOff.canvasOpen || previewOff.pageBreaks > 0) {
  throw new Error('C5 preview off mutated body ' + JSON.stringify(previewOff))
}
step('C5-preview', 'PASS', { noteBefore, statusBefore, previewOn, previewOff })

await clickCss(pageS, '[data-action="open-export"]')
await waitFor(pageS, 'dialog.export-setup')
if (!(await pageS.locator('input[name="export-format"][value="hwpx"]').isChecked())) {
  await pageS.locator('input[name="export-format"][value="hwpx"]').check()
}
if (!(await pageS.locator('input[name="export-format"][value="docx"]').isChecked())) {
  await pageS.locator('input[name="export-format"][value="docx"]').check()
}
const consent = pageS.locator('[data-export-consent]')
if (!(await consent.isChecked())) await consent.check()
const batch = pageS.locator('[data-batch-export]')
if (await batch.count() && await batch.isChecked()) await batch.uncheck()
await armMutationSignal(pageS, 'export-finished', 'export', null, 90000)
await clickCss(pageS, '[data-action="export"]')
await awaitSignal(pageS, 'export-finished')
const summary = await textOf(pageS, '#export-summary')
const resultsText = await textOf(pageS, '.export-results').catch(() => '')
const lossText = await textOf(pageS, '.loss-report').catch(() => '')
await pageS.screenshot({ path: evidence + '/c6-export.png' })
const publishedDocx = /docx/i.test(summary + resultsText)
const blockedHwpx = /hwpx/i.test(summary + lossText + resultsText) && /차단|blocked|의미 손실|semantic/i.test(summary + lossText)
if (!summary) throw new Error('C6 no export summary')
if (!publishedDocx || !blockedHwpx) {
  step('C6-export', 'FAIL', { summary, resultsText, lossText, publishedDocx, blockedHwpx })
  throw new Error('C6 export gate unexpected: ' + summary)
}
step('C6-export', 'PASS', {
  summary,
  resultsText: resultsText.slice(0, 800),
  lossText: lossText.slice(0, 800),
})

console.log('TRIAL_LOG ' + JSON.stringify(log, null, 2))
console.log('TRIAL_OK')
