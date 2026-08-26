(function (studio) {
  const store = studio.state
  const { page, editor, titleInput, outlineList, checklist, templatePanel, inspector, aiProposalReview } = studio.dom
  const isEasyTableElement = (...args) => studio.isEasyTableElement(...args)
  const renderTemplateCatalog = (...args) => studio.renderTemplateCatalog(...args)
  const renderOfficialRuleState = (...args) => studio.renderOfficialRuleState(...args)
  const applyPageMarginStyles = (...args) => studio.applyPageMarginStyles(...args)
  const rehydrateRichContent = (...args) => studio.rehydrateRichContent(...args)
  const announce = (...args) => studio.announce(...args)
  const initialProject = (...args) => studio.initialProject(...args)
  const newRevision = (...args) => studio.newRevision(...args)
  const projectBridge = (...args) => studio.projectBridge(...args)
  const openDialog = (...args) => studio.openDialog(...args)
  const syncFormatStates = (...args) => studio.syncFormatStates(...args)

  const revisionAncestors = (project, revisionID = project?.currentRevisionID) => {
    const parents = Object.fromEntries((project?.revisions || []).map((revision) => [revision.revisionID, revision.parentRevisionID]))
    const chain = []
    const seen = new Set()
    let cursor = revisionID
    while (cursor && !seen.has(cursor)) {
      chain.push(cursor)
      seen.add(cursor)
      cursor = parents[cursor]
    }
    return chain
  }
  const isStaleBridgeProject = (incoming) => {
    if (!store.currentProject || !incoming?.currentRevisionID) return false
    if (incoming.documentID && store.currentProject.documentID && incoming.documentID !== store.currentProject.documentID) return false
    if (incoming.currentRevisionID === store.currentProject.currentRevisionID) return false
    const localChain = revisionAncestors(store.currentProject)
    if (localChain.includes(incoming.currentRevisionID)) return true
    const incomingChain = revisionAncestors(incoming)
    if (incomingChain.includes(store.currentProject.currentRevisionID)) return false
    const incomingIDs = new Set((incoming.elements || []).map((element) => element.elementID))
    return (store.currentProject.elements || []).some((element) => isEasyTableElement(element) && !incomingIDs.has(element.elementID))
  }
  const applyBridgeProject = (incoming, officialRuleState) => {
    if (!incoming || incoming.currentRevisionID === store.currentProject?.currentRevisionID || isStaleBridgeProject(incoming)) return false
    renderProject(incoming, officialRuleState)
    return true
  }

  const renderProject = (project, officialRuleState = null) => {
    store.selectedEditorElementID = null
    store.currentProject = project
    titleInput.value = project.title
    applyPageMarginStyles(project.pageMargins)
    if (store.editorReady) {
      store.suppressEditorAutosave = true
      editor.setProject(project)
      window.requestAnimationFrame(() => { store.suppressEditorAutosave = false })
    }
    else project.elements.forEach((element) => {
      const target = page.querySelector(`[data-element-id="${CSS.escape(element.elementID)}"]`)
      if (target && element.contentHTML && target.innerHTML !== element.contentHTML) rehydrateRichContent(target, element.contentHTML)
      else if (target && !element.contentHTML && target.textContent.trim() !== element.text) target.textContent = element.text
    })
    renderGuidance(project.templateBinding)
    if (store.currentTemplateCatalog) renderTemplateCatalog(store.currentTemplateCatalog, false)
    if (officialRuleState) renderOfficialRuleState(officialRuleState)
  }

  const renderGuidance = (binding) => {
    const typeLabel = store.currentTemplateCatalog?.entries.find((entry) => entry.templateID === binding.templateID)?.documentType
    if (typeLabel) document.querySelector('.panel-heading h2').textContent = typeLabel
    outlineList.replaceChildren(...binding.requiredSections.map((section, index) => {
      const item = document.createElement('li')
      const button = document.createElement('button')
      button.type = 'button'
      button.dataset.section = `section-${index + 1}`
      button.dataset.elementId = `element-section-${index + 1}-body`
      button.setAttribute('aria-label', `${index + 1}. ${section}`)
      item.classList.toggle('active', index === 0)
      if (index === 0) button.setAttribute('aria-current', 'location')
      const number = document.createElement('span')
      number.textContent = String(index + 1)
      button.append(number, document.createTextNode(section))
      item.append(button)
      return item
    }))
    const results = Object.entries(binding.checklistResults)
    const complete = results.filter(([, done]) => done).length
    checklist.querySelector('.checklist-title strong').textContent = `${complete} / ${results.length}`
    const progress = checklist.querySelector('[role="progressbar"]')
    progress.setAttribute('aria-valuemax', String(results.length))
    progress.setAttribute('aria-valuenow', String(complete))
    progress.querySelector('span').style.width = `${results.length ? complete / results.length * 100 : 0}%`
    checklist.querySelector('ul').replaceChildren(...results.map(([label, done]) => {
      const item = document.createElement('li')
      item.textContent = label
      item.classList.toggle('done', done)
      return item
    }))
    templatePanel.querySelector('.pinned-template strong').textContent = `${binding.templateID} v${binding.version}`
    document.querySelector('.version-badge').textContent = `v${binding.version}`
  }

  const setOutlineCurrent = (button) => {
    outlineList.querySelectorAll('button').forEach((candidate) => {
      const current = candidate === button
      candidate.closest('li')?.classList.toggle('active', current)
      if (current) candidate.setAttribute('aria-current', 'location')
      else candidate.removeAttribute('aria-current')
    })
  }

  const scheduleAutosave = () => {
    window.clearTimeout(store.autosaveTimer)
    store.autosaveTimer = window.setTimeout(() => {
      if (!store.currentProject) return
      const autosavedProject = newRevision(store.currentProject, 'autosaved')
      if (autosavedProject === store.currentProject) return
      store.currentProject = autosavedProject
      projectBridge('autosave', store.currentProject)
    }, 600)
  }

  const activateGenOfficeEditor = () => {
    if (store.editorReady || typeof editor?.setProject !== 'function' || typeof editor.getElements !== 'function') return false
    store.editorReady = true
    editor.dataset.runtime = 'ready'
    renderProject(store.currentProject || initialProject())
    announce('GenOffice 편집기를 연결했습니다.')
    return true
  }

  const focusEditorElement = (section, explicitElementID) => {
    const headingID = explicitElementID || `element-${section}-heading`
    const bodyID = String(headingID).replace(/-heading$/, '-body')
    const elementID = (store.currentProject?.elements || []).some((element) => element.elementID === bodyID)
      ? bodyID
      : headingID
    if (!store.editorReady || !elementID || typeof editor.focusElement !== 'function' || !editor.focusElement(elementID)) {
      announce('GenOffice 편집기에서 선택한 문서 구조로 이동할 수 없습니다.')
      return false
    }
    store.focusedEditorElementID = elementID
    syncFormatStates()
    return true
  }

  const showInspection = (details) => {
    const labels = {
      schemaVersion: '스키마 버전', documentID: '문서', currentRevisionID: '저장본',
      elementCount: '요소', assetCount: '자산', styleCount: '스타일',
      evidenceLinkCount: '근거 연결', revisionCount: '리비전', historyEventCount: '기록',
      templateID: '적용 템플릿', templateVersion: '템플릿 버전',
    }
    const userFacingValues = {
      documentID: '현재 문서',
      currentRevisionID: '현재 저장본',
      templateID: '공식 템플릿',
    }
    inspector.querySelector('dl').replaceChildren(...Object.entries(labels).flatMap(([key, label]) => {
      const term = document.createElement('dt')
      const description = document.createElement('dd')
      term.textContent = label
      description.textContent = userFacingValues[key] || String(details[key])
      return [term, description]
    }))
    openDialog(inspector)
  }

  document.querySelectorAll('[data-project-action]').forEach((button) => {
    button.addEventListener('click', () => {
      const action = button.dataset.projectAction
      if (action === 'new') {
        store.currentProject = initialProject()
        store.pendingAIProposal = null
        aiProposalReview.hidden = true
        renderProject(store.currentProject)
        projectBridge('save', store.currentProject)
        return
      }
      if (action === 'save') {
        const savedProject = newRevision(store.currentProject || initialProject(), 'saved')
        if (savedProject === store.currentProject) return
        store.currentProject = savedProject
        projectBridge('save', store.currentProject)
        return
      }
      projectBridge(action)
    })
  })

  editor.addEventListener('public-document-genoffice-change', (event) => {
    if (!store.suppressEditorAutosave && store.editorReady && Array.isArray(event.detail?.elements)) scheduleAutosave()
  })
  editor.addEventListener('pointerdown', () => {
    store.selectionStartedByUser = true
  })
  editor.addEventListener('public-document-genoffice-selection-change', (event) => {
    syncFormatStates(event.detail)
    if (store.selectionStartedByUser && event.detail?.elementID) {
      store.selectedEditorElementID = event.detail.elementID
    }
    store.selectionStartedByUser = false
  })
  titleInput.addEventListener('input', scheduleAutosave)

  Object.assign(studio, {
    revisionAncestors,
    isStaleBridgeProject,
    applyBridgeProject,
    renderProject,
    renderGuidance,
    setOutlineCurrent,
    scheduleAutosave,
    activateGenOfficeEditor,
    focusEditorElement,
    showInspection
  })
}(window.PublicDocumentStudio))
