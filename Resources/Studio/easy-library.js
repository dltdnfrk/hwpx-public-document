(function (studio) {
  const store = studio.state
  const fallbackProjectElements = (...args) => studio.fallbackProjectElements(...args)
  const projectElements = (...args) => studio.projectElements(...args)
  const isEasyTableElement = (...args) => studio.isEasyTableElement(...args)
  const initialProject = (...args) => studio.initialProject(...args)
  const revisionTimestamp = (...args) => studio.revisionTimestamp(...args)
  const renderProject = (...args) => studio.renderProject(...args)
  const projectBridge = (...args) => studio.projectBridge(...args)
  const announce = (...args) => studio.announce(...args)
  const isTitleElement = (...args) => studio.isTitleElement(...args)
  const runEditorCommand = (...args) => studio.runEditorCommand(...args)
  const easyTools = (...args) => studio.easyTools(...args)
  const tablePlainText = (...args) => studio.tablePlainText(...args)
  const isLocalWeb = (...args) => studio.isLocalWeb(...args)
  const plainTextContentHTML = (...args) => studio.plainTextContentHTML(...args)
  const MAX_EASY_HISTORY_ENTRIES = 20
  const MAX_EASY_HISTORY_BYTES = 8 * 1024 * 1024

  const liveElements = () => {
    const persisted = store.currentProject?.elements || fallbackProjectElements()
    const live = projectElements({ silent: true })
    const base = live || persisted
    const missingTables = persisted.filter((element) => (
      isEasyTableElement(element) && !base.some((item) => item.elementID === element.elementID)
    ))
    return missingTables.length ? [...base, ...missingTables] : base
  }

  const bindTableText = (element) => {
    const tools = easyTools()
    return tools && typeof tools.bindTableText === 'function' ? tools.bindTableText(element) : element
  }

  const historyEntry = (project) => {
    let serialized
    try {
      serialized = JSON.stringify(project)
    } catch {
      return null
    }
    if (!serialized) return null
    const bytes = new TextEncoder().encode(serialized).byteLength
    if (bytes > MAX_EASY_HISTORY_BYTES) return null
    return { project: JSON.parse(serialized), bytes }
  }

  const pushEasyHistory = (stack, project) => {
    const entry = historyEntry(project)
    if (!entry) return false
    stack.push(entry)
    let bytes = stack.reduce((sum, item) => sum + item.bytes, 0)
    while (stack.length > MAX_EASY_HISTORY_ENTRIES || bytes > MAX_EASY_HISTORY_BYTES) {
      bytes -= stack.shift().bytes
    }
    return true
  }

  const invalidateEasyHistory = () => {
    store.easyUndoStack = []
    store.easyRedoStack = []
  }

  const commitProjectElements = (elements, summary, message, extra = {}) => {
    if (!store.currentProject) store.currentProject = initialProject()
    if (!pushEasyHistory(store.easyUndoStack, store.currentProject)) {
      announce('문서가 너무 커서 되돌리기 상태를 안전하게 만들 수 없어 작업을 실행하지 않았습니다.')
      return false
    }
    store.easyRedoStack = []
    const nextElements = elements.map((element, order) => ({ ...bindTableText(element), order }))
    const revisionID = `revision-${crypto.randomUUID()}`
    const createdAt = revisionTimestamp()
    store.currentProject = {
      ...store.currentProject,
      ...extra,
      elements: nextElements,
      currentRevisionID: revisionID,
      revisions: [...store.currentProject.revisions, {
        revisionID,
        parentRevisionID: store.currentProject.currentRevisionID,
        createdAt,
        summary,
        elementIDs: nextElements.map((element) => element.elementID),
        snapshotElements: nextElements,
      }],
      history: [...store.currentProject.history, {
        eventID: `history-${crypto.randomUUID()}`,
        kind: summary,
        revisionID,
        createdAt,
      }],
    }
    renderProject(store.currentProject, null, true)
    projectBridge('save', store.currentProject)
    announce(message)
    return true
  }

  const restoreEasyProjectChange = (source, destination) => {
    if (!source.length || !store.currentProject) return false
    if (!pushEasyHistory(destination, store.currentProject)) {
      announce('문서가 너무 커서 반대 작업 상태를 안전하게 만들 수 없어 작업을 실행하지 않았습니다.')
      return false
    }
    store.currentProject = source.pop().project
    renderProject(store.currentProject, null, true)
    projectBridge('save', store.currentProject)
    return true
  }

  const undoEasyProjectChange = () => (
    restoreEasyProjectChange(store.easyUndoStack, store.easyRedoStack)
  )

  const redoEasyProjectChange = () => (
    restoreEasyProjectChange(store.easyRedoStack, store.easyUndoStack)
  )

  const insertTargetIndex = (elements) => {
    const focused = elements.findIndex((element) => element.elementID === store.focusedEditorElementID)
    if (focused >= 0 && !isTitleElement(elements[focused])) return focused
    const body = elements.findIndex((element) => element.kind === 'paragraph' && !isTitleElement(element))
    if (body >= 0) return body
    return elements.findIndex((element) => !isTitleElement(element))
  }

  const hangingIndentTargetIndex = (elements) => {
    const focused = elements.findIndex((element) => element.elementID === store.focusedEditorElementID)
    const target = focused >= 0 ? elements[focused] : null
    if (target && !isTitleElement(target) && target.kind === 'paragraph') return focused
    if (target?.elementID) {
      const bodyID = String(target.elementID).replace(/-heading$/, '-body')
      const body = elements.findIndex((element) => element.elementID === bodyID && !isTitleElement(element))
      if (body >= 0) return body
    }
    return elements.findIndex((element) => element.kind === 'paragraph' && !isTitleElement(element))
  }

  const focusedTextTargetIndex = (elements) => {
    const index = elements.findIndex((element) => element.elementID === store.focusedEditorElementID)
    const target = index >= 0 ? elements[index] : null
    if (!target || isTitleElement(target) || ['table', 'approval-grid'].includes(target.kind)) return -1
    return index
  }

  const replacePlainTextElement = (element, text) => ({
    ...element,
    text,
    contentHTML: plainTextContentHTML(text),
    inlineIDs: [],
  })

  const insertPlainText = (text, fallbackMessage) => {
    if (!text) return announce('넣을 값이 없습니다.')
    const elements = liveElements()
    const focused = elements.find((element) => element.elementID === store.focusedEditorElementID)
    const insertion = focused?.text
      && !/\s$/.test(focused.text)
      && !/^\s/.test(text)
      ? ` ${text}`
      : text
    if (!isTitleElement(focused) && runEditorCommand('insertText', insertion)) {
      announce(fallbackMessage)
      return
    }
    const index = insertTargetIndex(elements)
    const target = elements[index]
    if (!target || isTitleElement(target)) return announce('본문 위치를 먼저 선택하세요.')
    const next = `${target.text || ''}${insertion}`
    elements[index] = replacePlainTextElement(target, next)
    commitProjectElements(elements, 'easy-insert', fallbackMessage)
  }

  const focusedTable = (elements) => {
    const tables = elements.filter((element) => (
      element.kind === 'table' || /<table|data-easy-table|<tbody/i.test(element.contentHTML || '')
    ))
    const focused = tables.find((element) => element.elementID === store.focusedEditorElementID)
    if (focused) return focused
    const easy = tables.find((element) => /data-easy-table/i.test(element.contentHTML || ''))
    if (easy) return easy
    return tables.length === 1 ? tables[0] : null
  }

  const updateTableElement = (mutate, message) => {
    const tools = easyTools()
    if (!tools) return announce('작성 도구를 불러오지 못했습니다.')
    const elements = liveElements()
    const table = focusedTable(elements)
    if (!table) return announce('먼저 표를 넣으세요.')
    const html = mutate(tools.parseTable(table.contentHTML || table.text) || table.contentHTML || table.text)
    const index = elements.findIndex((element) => element.elementID === table.elementID)
    elements[index] = { ...table, kind: 'table', styleID: 'style-table', contentHTML: html, text: tablePlainText(html) }
    commitProjectElements(elements, 'easy-table', message)
  }

  const applyLibraryMerge = (incoming) => {
    const tools = easyTools()
    if (!tools || !incoming) return
    const heading = store.pendingMergeHeading || incoming.title || '취합'
    store.pendingMergeHeading = ''
    commitProjectElements(
      tools.mergeDocumentElements(liveElements(), incoming.elements || [], heading),
      'document-merged',
      `${incoming.title || '문서'}를 취합했습니다.`,
    )
  }

  const persistLibraryDocument = (project) => {
    const entry = { documentID: project.documentID, title: project.title }
    store.libraryEntries = [...store.libraryEntries.filter((item) => item.documentID !== entry.documentID), entry]
    store.libraryProjects[project.documentID] = project
    if (isLocalWeb()) projectBridge('saveLibraryDocument', project)
    announce('문서함에 보관했습니다.')
  }

  const requestLibraryDocument = (documentID) => {
    if (store.libraryProjects[documentID]) {
      applyLibraryMerge(store.libraryProjects[documentID])
      return
    }
    if (isLocalWeb()) {
      projectBridge('loadLibraryDocument', null, { documentID })
      return
    }
    applyLibraryMerge(store.libraryProjects[documentID])
  }

  Object.assign(studio, {
    liveElements,
    invalidateEasyHistory,
    commitProjectElements,
    undoEasyProjectChange,
    redoEasyProjectChange,
    insertTargetIndex,
    hangingIndentTargetIndex,
    focusedTextTargetIndex,
    replacePlainTextElement,
    insertPlainText,
    focusedTable,
    updateTableElement,
    applyLibraryMerge,
    persistLibraryDocument,
    requestLibraryDocument
  })
}(window.PublicDocumentStudio))
