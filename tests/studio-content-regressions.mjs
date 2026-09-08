import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const studioSource = (name) => readFileSync(new URL(`../Resources/Studio/${name}`, import.meta.url), 'utf8')

function pageEngine() {
  const context = vm.createContext({ console })
  context.globalThis = context
  vm.runInContext(studioSource('official-layout-profile.js'), context)
  vm.runInContext(studioSource('page-engine.js'), context)
  return context.PublicDocumentPageEngine
}

test('empty bootstrap renders the canonical project before saving it', () => {
  const state = {
    currentProject: { documentID: 'fallback', elements: Array.from({ length: 15 }, (_, index) => ({ elementID: `fallback-${index}` })) },
    easyUndoStack: ['undo'],
    easyRedoStack: ['redo'],
  }
  const canonical = {
    documentID: 'canonical',
    currentRevisionID: 'revision-canonical',
    elements: Array.from({ length: 11 }, (_, index) => ({ elementID: `canonical-${index}` })),
  }
  let rendered = null
  let editorElements = state.currentProject.elements
  const saved = []
  const inert = { hidden: false, open: false, querySelector: () => ({ textContent: '', disabled: false, hidden: false }) }
  const studio = {
    state,
    dom: { aiProposalReview: inert, batchExportProgress: inert, byokSettings: inert, aiWorkspace: inert },
    initialProject: () => canonical,
    renderProject: (project) => {
      rendered = project
      editorElements = project.elements
    },
    projectBridge: (action, project) => saved.push({ action, project }),
    announce: () => {},
    officialRuleWarning: () => '',
  }
  const context = vm.createContext({
    console,
    document: { querySelector: () => ({ value: '', checked: false }) },
    window: { PublicDocumentStudio: studio },
  })
  vm.runInContext(studioSource('studio-events.js'), context)

  context.window.projectStoreReceive({ event: 'empty', payload: {} })

  assert.equal(state.currentProject, canonical)
  assert.equal(rendered, canonical)
  assert.deepEqual(saved, [{ action: 'save', project: canonical }])
  const canSnapshotForSaveOrExport = editorElements.length === state.currentProject.elements.length
    && editorElements.every((element, index) => element.elementID === state.currentProject.elements[index].elementID)
  assert.equal(canSnapshotForSaveOrExport, true)
})

test('oversized paragraph preview partitions source text exactly once', () => {
  const engine = pageEngine()
  const source = `시작${'가'.repeat(5000)}끝`
  const layout = engine.paginateBlocks([{ id: 'long', kind: 'paragraph', styleID: 'style-body', text: source }])
  const fragments = layout.pages.flatMap((page) => page.blocks).filter((block) => block.sourceID === 'long' || block.id === 'long')
  const markup = engine.previewMarkup(layout)

  assert.ok(layout.pageCount > 1)
  assert.ok(fragments.length > 1)
  assert.equal(fragments.map((block) => block.text).join(''), source)
  assert.equal(fragments.reduce((total, block) => total + Array.from(block.text).length, 0), Array.from(source).length)
  assert.equal(new Set(fragments.map((block) => block.id)).size, fragments.length)
  assert.equal(markup.split('시작').length - 1, 1)
  assert.equal(markup.split('끝').length - 1, 1)
})

test('newRevision preserves unchanged rich titles and clears identity after plain title edits', () => {
  const titleInput = { value: '서식 제목' }
  const title = {
    elementID: 'element-title',
    kind: 'heading',
    order: 0,
    text: '서식 제목',
    contentHTML: '<strong data-inline-id="inline-title">서식 제목</strong>',
    inlineIDs: ['inline-title'],
    styleID: 'style-title',
  }
  const project = {
    documentID: 'document-rich-title',
    title: title.text,
    currentRevisionID: 'revision-1',
    elements: [title],
    revisions: [],
    history: [],
  }
  const studio = {
    state: { currentProject: project },
    dom: { titleInput, editor: {}, page: {} },
    revisionTimestamp: () => '2026-09-05T00:00:00Z',
    officialTitleFor: () => '제목',
    fallbackProjectElements: () => project.elements,
    projectElements: () => project.elements,
    isTitleElement: (element) => element?.elementID === 'element-title',
  }
  const context = vm.createContext({
    console,
    crypto: { randomUUID: () => 'fixed-id' },
    document: {},
    window: { PublicDocumentStudio: studio },
  })
  vm.runInContext(studioSource('project-model.js'), context)

  const unchanged = studio.newRevision(project, 'autosaved')
  assert.equal(unchanged.elements[0].contentHTML, title.contentHTML)
  assert.deepEqual(Array.from(unchanged.elements[0].inlineIDs), ['inline-title'])

  titleInput.value = '<b>새 제목</b>\n둘째 줄'
  const changed = studio.newRevision(project, 'saved')
  assert.equal(changed.elements[0].text, titleInput.value)
  assert.equal(changed.elements[0].contentHTML, '&lt;b&gt;새 제목&lt;/b&gt;\n둘째 줄')
  assert.deepEqual(Array.from(changed.elements[0].inlineIDs), [])
})

test('plain-text project paths escape markup and retain authored line breaks', () => {
  const titleInput = { value: '<strong>제목</strong>\n둘째 줄' }
  const fields = [{ dataset: { wizardField: '본문' }, value: '<em>내용</em>\n다음 줄' }]
  const fieldsRoot = { querySelectorAll: () => fields, replaceChildren: () => {} }
  const project = {
    documentID: 'document-content',
    title: '이전 제목',
    currentRevisionID: 'revision-1',
    elements: [
      { elementID: 'element-title', kind: 'heading', order: 0, text: '이전 제목', contentHTML: '이전 제목', inlineIDs: [], styleID: 'style-title' },
      { elementID: 'element-section-1-body', kind: 'paragraph', order: 1, text: '이전 내용', contentHTML: '이전 내용', inlineIDs: [], styleID: 'style-body' },
    ],
    revisions: [],
    history: [],
    templateBinding: { templateID: 'public-draft', requiredSections: ['본문'], checklistResults: {} },
  }
  const state = { currentProject: project, focusedEditorElementID: 'element-section-1-body', easyUndoStack: [], easyRedoStack: [] }
  const studio = {
    state,
    dom: { titleInput, editor: {}, page: {} },
    revisionTimestamp: () => '2026-09-05T00:00:00Z',
    officialTitleFor: () => '제목',
    fallbackProjectElements: () => project.elements,
    projectElements: () => project.elements,
    isTitleElement: (element) => element?.elementID === 'element-title',
    easyTools: () => null,
    isEasyTableElement: () => false,
    renderProject: () => {},
    projectBridge: () => {},
    announce: () => {},
    runEditorCommand: () => false,
    tablePlainText: () => '',
    isLocalWeb: () => true,
    hasOfficialTitleRule: () => false,
    openDialog: () => {},
    closeDialog: () => {},
  }
  const document = {
    querySelector: (selector) => selector === '[data-wizard-fields]' ? fieldsRoot : null,
    querySelectorAll: () => [],
  }
  const context = vm.createContext({
    console,
    crypto: { randomUUID: () => 'fixed-id' },
    document,
    TextEncoder,
    window: { PublicDocumentStudio: studio },
  })
  vm.runInContext(studioSource('project-model.js'), context)
  vm.runInContext(studioSource('easy-library.js'), context)
  vm.runInContext(studioSource('draft-wizard.js'), context)

  const escapedTitle = '&lt;strong&gt;제목&lt;/strong&gt;\n둘째 줄'
  const escapedBody = '가. &lt;em&gt;내용&lt;/em&gt;\n다음 줄'
  assert.equal(studio.plainTextContentHTML('<strong>제목</strong>\n둘째 줄'), escapedTitle)

  const revision = studio.newRevision(project, 'saved')
  assert.equal(revision.elements[0].contentHTML, escapedTitle)
  assert.equal(revision.elements[0].text, titleInput.value)

  const replaced = studio.replacePlainTextElement(project.elements[1], '<b>본문</b>\n다음 줄')
  assert.equal(replaced.contentHTML, '&lt;b&gt;본문&lt;/b&gt;\n다음 줄')
  assert.equal(replaced.text, '<b>본문</b>\n다음 줄')

  assert.equal(studio.applyDraftWizard(), true)
  assert.equal(state.currentProject.elements[1].contentHTML, escapedBody)
  assert.equal(state.currentProject.elements[1].text, '가. <em>내용</em>\n다음 줄')
})
