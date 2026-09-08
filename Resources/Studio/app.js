(function (studio) {
  const store = studio.state
  const { editor, easyToolDialog } = studio.dom
  const openDialog = studio.openDialog
  const closeDialog = studio.closeDialog
  const focusEditorElement = studio.focusEditorElement
  const showAIProposal = studio.showAIProposal
  const showExportResult = studio.showExportResult
  const showBatchExportProgress = studio.showBatchExportProgress
  const revisionTimestamp = studio.revisionTimestamp
  const isStaleBridgeProject = studio.isStaleBridgeProject
  const revisionAncestors = studio.revisionAncestors
  const applyBridgeProject = studio.applyBridgeProject
  const insertTargetIndex = studio.insertTargetIndex
  const hangingIndentTargetIndex = studio.hangingIndentTargetIndex
  const tablePlainText = studio.tablePlainText
  const preserveTableMarkup = studio.preserveTableMarkup
  const announce = studio.announce
  const projectBridge = studio.projectBridge
  const readEasyFields = studio.readEasyFields
  const applyProviderDefaults = studio.applyProviderDefaults
  const applyStudioPrefs = studio.applyStudioPrefs
  const initialProject = studio.initialProject
  const activateGenOfficeEditor = studio.activateGenOfficeEditor
  const syncOutlineForViewport = studio.syncOutlineForViewport

  const confirmEasyTool = () => {
    const fields = readEasyFields()
    const confirm = store.pendingEasyConfirm
    store.pendingEasyConfirm = null
    closeDialog(easyToolDialog)
    return confirm?.(fields)
  }

  const persistLibraryDocument = (project) => {
    const entry = { documentID: project.documentID, title: project.title }
    store.libraryEntries = [...store.libraryEntries.filter((item) => item.documentID !== entry.documentID), entry]
    store.libraryProjects[project.documentID] = project
    if (studio.isLocalWeb()) projectBridge('saveLibraryDocument', project)
    announce('문서함에 보관했습니다.')
  }
  studio.confirmEasyTool = confirmEasyTool
  studio.persistLibraryDocument = persistLibraryDocument

  studio.entryContract = {
    PublicDocumentEasyTools: window.PublicDocumentEasyTools,
    openerFocus: 'opener.focus()',
    editorFocus: 'editor.focusElement(elementID)',
    setProject: '.setProject(project)',
    getElements: '.getElements()',
    command: '.command(command, value)',
    structureMatches: 'structureMatches',
    contentHTML: 'element.contentHTML ?? previous.contentHTML ?? element.text',
    blocked: '저장하거나 내보낼 수 없습니다.',
    aiApplied: "announce('선택한 AI 제안을 하나의 새 리비전으로 적용했습니다.')",
    toggleFavorite: 'toggle-favorite',
    easyAction: 'data-easy-action',
    saveStudioPrefs: 'saveStudioPrefs',
    saveLibraryDocument: 'saveLibraryDocument',
    loadLibraryDocument: 'loadLibraryDocument',
    localISODate: 'localISODate',
    elementsFromTemplate: 'elementsFromTemplate(plan',
    selectedIndex: 'input.selectedIndex = 0',
    mergeValue: 'value: libraryEntries[0].documentID',
    rangeError: '종료일은 시작일 이후여야 합니다',
    amountError: '숫자 금액을 입력하세요',
    easyTable: 'data-easy-table',
    sectionBody: 'element-section-${index + 1}-body',
    tableText: 'text: tablePlainText(html)',
    singleTable: 'tables.length === 1',
    libraryLookup: 'libraryProjects[documentID]',
    changeEvent: 'public-document-genoffice-change',
  }

  window.projectStoreReceive = studio.projectStoreReceive
  document.querySelectorAll('details > summary').forEach((summary) => {
    summary.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.code !== 'Space') return
      event.preventDefault()
      event.stopPropagation()
      const open = !summary.parentElement.open
      queueMicrotask(() => {
        summary.parentElement.open = open
      })
    })
  })
  syncOutlineForViewport()
  if (!(window.webkit && window.webkit.messageHandlers.projectStore)) {
    document.body.dataset.host = 'local-web'
  }
  applyProviderDefaults('openai')
  document.querySelector('[data-ai-request]').disabled = true
  applyStudioPrefs(store.studioPrefs)
  store.currentProject = initialProject()
  studio.applyTitleLock(store.currentProject)
  editor.addEventListener('public-document-genoffice-ready', activateGenOfficeEditor)
  if (!activateGenOfficeEditor()) announce('GenOffice 편집기 번들을 불러오지 못해 편집을 차단했습니다.')
  projectBridge('ready')
}(window.PublicDocumentStudio))
