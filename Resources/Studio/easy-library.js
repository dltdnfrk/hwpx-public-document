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

  const liveElements = () => {
    const persisted = store.currentProject?.elements || fallbackProjectElements()
    const live = projectElements({ silent: true })
    const base = live || persisted
    const missingTables = persisted.filter((element) => (
      isEasyTableElement(element) && !base.some((item) => item.elementID === element.elementID)
    ))
    return missingTables.length ? [...base, ...missingTables] : base
  }

  const commitProjectElements = (elements, summary, message, extra = {}) => {
    if (!store.currentProject) store.currentProject = initialProject()
    const nextElements = elements.map((element, order) => ({ ...element, order }))
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
    renderProject(store.currentProject)
    projectBridge('save', store.currentProject)
    announce(message)
  }

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

  const insertPlainText = (text, fallbackMessage) => {
    if (!text) return announce('넣을 값이 없습니다.')
    const elements = liveElements()
    const focused = elements.find((element) => element.elementID === store.focusedEditorElementID)
    if (!isTitleElement(focused) && runEditorCommand('insertText', text)) {
      announce(fallbackMessage)
      return
    }
    const index = insertTargetIndex(elements)
    const target = elements[index]
    if (!target || isTitleElement(target)) return announce('본문 위치를 먼저 선택하세요.')
    const next = `${target.text || ''}${text}`
    elements[index] = { ...target, text: next, contentHTML: next }
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
    commitProjectElements,
    insertTargetIndex,
    hangingIndentTargetIndex,
    insertPlainText,
    focusedTable,
    updateTableElement,
    applyLibraryMerge,
    persistLibraryDocument,
    requestLibraryDocument
  })
}(window.PublicDocumentStudio))
