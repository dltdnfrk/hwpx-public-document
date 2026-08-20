const statusMessage = document.querySelector('.status-message')
const page = document.querySelector('#static-editor-fallback')
const editor = document.querySelector('public-document-genoffice-editor')
const workspace = document.querySelector('.workspace')
const outlineToggle = document.querySelector('[data-action="outline"]')
const titleInput = document.querySelector('.document-title input')
const inspector = document.querySelector('.project-inspector')
const outlineList = document.querySelector('.outline-list')
const checklist = document.querySelector('.checklist')
const templatePanel = document.querySelector('.template-governance')
const exportResult = document.querySelector('.export-result')
const exportSetup = document.querySelector('.export-setup')
const exportConsent = document.querySelector('[data-export-consent]')
const batchExportProgress = document.querySelector('.batch-export-progress')
const aiWorkspace = document.querySelector('.ai-workspace')
const aiProposalReview = document.querySelector('[data-ai-proposal-review]')
const compactLayout = window.matchMedia('(max-width: 1099px)')
const easyToolDialog = document.querySelector('.easy-tool-dialog')
const easyTools = () => window.PublicDocumentEasyTools
const revisionTimestamp = () => new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')
const isTitleElement = (element) => Boolean(element && (element.elementID === 'element-title' || element.styleID === 'style-title'))
const isEasyTableElement = (element) => Boolean(
  element && (element.kind === 'table' || /data-easy-table/i.test(element.contentHTML || ''))
)
const tablePlainText = (html) => {
  const tools = easyTools()
  return tools ? tools.tablePlainText(html) : String(html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}
const preserveTableMarkup = (liveHTML, previous, fallbackText) => {
  const live = liveHTML ?? ''
  const prior = previous?.contentHTML || ''
  const raw = (/data-easy-table/i.test(live) || /<table/i.test(live))
    ? live
    : (/data-easy-table/i.test(prior) || /<table/i.test(prior))
      ? prior
      : (live || prior || fallbackText || '')
  if (!/<tr/i.test(raw) || !/ProseMirror-trailingBreak|<br/i.test(raw)) return raw
  const tools = easyTools()
  return tools ? (tools.cleanPastedTable(raw) || raw) : raw
}
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
  if (!currentProject || !incoming?.currentRevisionID) return false
  if (incoming.documentID && currentProject.documentID && incoming.documentID !== currentProject.documentID) return false
  if (incoming.currentRevisionID === currentProject.currentRevisionID) return false
  const localChain = revisionAncestors(currentProject)
  if (localChain.includes(incoming.currentRevisionID)) return true
  const incomingChain = revisionAncestors(incoming)
  if (incomingChain.includes(currentProject.currentRevisionID)) return false
  const incomingIDs = new Set((incoming.elements || []).map((element) => element.elementID))
  return (currentProject.elements || []).some((element) => isEasyTableElement(element) && !incomingIDs.has(element.elementID))
}
const applyBridgeProject = (incoming, officialRuleState) => {
  if (!incoming || incoming.currentRevisionID === currentProject?.currentRevisionID || isStaleBridgeProject(incoming)) return false
  renderProject(incoming, officialRuleState)
  return true
}
const officialTitleFor = (entry) => (
  (entry?.officialRules || []).find((rule) => rule.field === 'title')?.requiredValue || entry?.documentType || '추진계획서'
)
let currentProject = null
let currentTemplateCatalog = null
let currentOfficialRuleState = null
let autosaveTimer = null
let periodicSaveTimer = null
let selectedAIOperation = 'source-grounded-draft'
let pendingAIProposal = null
let pendingEasyConfirm = null
let pendingMergeHeading = ''
let studioPrefs = { autosaveIntervalMs: 180000, favorites: [], myForms: [] }
let libraryEntries = []
let libraryProjects = {}
let activeBatchOperationID = null
let activeBatchRetryOperationID = null
let editorReady = false
let focusedEditorElementID = 'element-title'
const dialogOpeners = new WeakMap()
const allowedRichTags = new Set(['B', 'BR', 'DIV', 'EM', 'FONT', 'I', 'LI', 'OL', 'SPAN', 'STRONG', 'TABLE', 'TBODY', 'TD', 'TFOOT', 'TH', 'THEAD', 'TR', 'U', 'UL'])
const allowedFontFaces = new Set(Array.from(document.querySelectorAll('[data-format="fontName"] option'), (option) => option.value))

const announce = (message) => {
  statusMessage.textContent = message
}

const resetExportConsent = () => {
  exportConsent.checked = false
}

const openDialog = (dialog, opener = document.activeElement) => {
  if (dialog === exportSetup) resetExportConsent()
  if (opener instanceof HTMLElement) dialogOpeners.set(dialog, opener)
  if (!dialog.open) dialog.showModal()
}

const closeDialog = (dialog) => {
  dialog.close()
  const opener = dialogOpeners.get(dialog)
  if (opener?.isConnected && !opener.disabled) opener.focus()
}

const projectBridge = (action, project, details = {}) => {
  const message = project ? { action, project, ...details } : { action, ...details }
  if (window.webkit && window.webkit.messageHandlers.projectStore) {
    window.webkit.messageHandlers.projectStore.postMessage(message)
    return
  }
  fetch('/api/bridge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(message),
  }).then(async (response) => {
    const payload = await response.json()
    const events = Array.isArray(payload.events) ? payload.events : [payload]
    if (!response.ok && !events.length) {
      throw new Error(payload.message || '로컬 웹 저장소 요청이 실패했습니다.')
    }
    events.forEach((entry) => window.projectStoreReceive(entry))
  }).catch((error) => {
    announce(error.message || '로컬 웹 저장소에 연결하지 못했습니다.')
  })
}

const ensureStableInlineIDs = (container) => {
  Array.from(container.childNodes).forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE && child.textContent.trim()) {
      const inline = document.createElement('span')
      inline.dataset.inlineId = `inline-${crypto.randomUUID()}`
      inline.textContent = child.textContent
      child.replaceWith(inline)
      return
    }
    if (child.nodeType === Node.ELEMENT_NODE) {
      if (!child.dataset.inlineId) child.dataset.inlineId = `inline-${crypto.randomUUID()}`
      ensureStableInlineIDs(child)
    }
  })
}

const sanitizeRichContent = (element) => {
  ensureStableInlineIDs(element)
  const clone = element.cloneNode(true)
  clone.querySelectorAll('*').forEach((child) => {
    if (!allowedRichTags.has(child.tagName)) {
      child.replaceWith(...child.childNodes)
      return
    }
    Array.from(child.attributes).forEach((attribute) => {
      const safeLayoutAttribute = ['colspan', 'rowspan'].includes(attribute.name) && ['TD', 'TH'].includes(child.tagName)
      const safeClass = attribute.name === 'class' && child.classList.contains('keep-phrase')
      const safeEasyTable = child.tagName === 'TABLE' && attribute.name === 'data-easy-table'
      const safeTableStyle = ['TABLE', 'TD', 'TH', 'TR'].includes(child.tagName)
        && attribute.name === 'style'
        && /^(?:\s*(?:border-collapse\s*:\s*collapse|border\s*:\s*(?:none|1px solid (?:transparent|#[0-9a-fA-F]{3,8}))|background\s*:\s*#[0-9a-fA-F]{3,8})\s*;?\s*)+$/.test(attribute.value)
      const safeFontAttribute = child.tagName === 'FONT' && (
        (attribute.name === 'face' && allowedFontFaces.has(attribute.value))
        || (attribute.name === 'size' && /^(10|11|12|14)$/.test(attribute.value))
      )
      if (attribute.name !== 'data-inline-id' && !safeLayoutAttribute && !safeClass && !safeEasyTable && !safeTableStyle && !safeFontAttribute) child.removeAttribute(attribute.name)
    })
  })
  return {
    html: clone.innerHTML,
    inlineIDs: Array.from(clone.querySelectorAll('[data-inline-id]')).map((inline) => inline.dataset.inlineId),
    nodes: Array.from(clone.childNodes).map((child) => child.cloneNode(true)),
  }
}

const rehydrateRichContent = (target, contentHTML) => {
  const containerTag = target.tagName === 'TABLE' ? 'table' : 'div'
  const parsed = new DOMParser().parseFromString(`<${containerTag}>${contentHTML}</${containerTag}>`, 'text/html')
  const safeContent = sanitizeRichContent(parsed.body.querySelector(containerTag))
  target.replaceChildren(...safeContent.nodes)
}

const inlineIDsFromContent = (contentHTML) => Array.from(
  new DOMParser().parseFromString(contentHTML, 'text/html').querySelectorAll('[data-inline-id]'),
  (inline) => inline.dataset.inlineId,
)

const fallbackProjectElements = () => Array.from(page.querySelectorAll('[data-element-id]')).map((element, order) => {
  const richContent = sanitizeRichContent(element)
  return {
    elementID: element.dataset.elementId,
    kind: element.dataset.elementKind,
    order,
    text: element.textContent.trim(),
    contentHTML: richContent.html,
    inlineIDs: richContent.inlineIDs,
    styleID: element.dataset.styleId,
    evidenceIDs: (element.dataset.evidenceIds || '').split(',').filter(Boolean),
  }
})

const projectElements = (options = {}) => {
  if (!editorReady) return fallbackProjectElements()
  const liveElements = editor.getElements()
  const expectedElements = currentProject?.elements || fallbackProjectElements()
  const editableBlockKinds = new Set(['heading', 'paragraph', 'list-item'])
  const kindMatches = (live, expected) => live === expected || (editableBlockKinds.has(live) && editableBlockKinds.has(expected))
  const structureMatches = liveElements.length === expectedElements.length && liveElements.every((element, order) => (
    element.id === expectedElements[order].elementID && kindMatches(element.type, expectedElements[order].kind)
  ))
  if (!structureMatches) {
    if (!options.silent) announce('GenOffice 편집기 구조가 프로젝트 원본과 달라 저장하거나 내보낼 수 없습니다.')
    return null
  }
  const elements = liveElements.map((element, order) => {
    const previous = expectedElements[order]
    const contentHTML = preserveTableMarkup(element.contentHTML ?? previous.contentHTML ?? element.text, previous, element.text)
    const inlineIDs = inlineIDsFromContent(contentHTML)
    if (Array.isArray(element.inlineIDs) && element.inlineIDs.join('\u0000') !== inlineIDs.join('\u0000')) {
      if (!options.silent) announce('GenOffice 편집기 인라인 식별자가 프로젝트 원본과 달라 저장하거나 내보낼 수 없습니다.')
      return null
    }
    return {
      ...previous,
      elementID: element.id,
      kind: element.type,
      order,
      text: element.text,
      contentHTML,
      inlineIDs,
      styleID: previous?.styleID || (element.level === 1 ? 'style-title' : element.level ? 'style-section-heading' : 'style-body'),
      evidenceIDs: previous?.evidenceIDs || [],
    }
  })
  return elements.some((element) => element === null) ? null : elements
}

const newRevision = (project, kind) => {
  const revisionID = `revision-${crypto.randomUUID()}`
  const createdAt = revisionTimestamp()
  const title = titleInput.value.trim() || '[확인 필요]'
  const elements = (projectElements() || []).map((element) => (
    isTitleElement(element) ? { ...element, text: title, contentHTML: title } : element
  ))
  if (!elements.length) return project
  return {
    ...project,
    title,
    currentRevisionID: revisionID,
    elements,
    revisions: [...project.revisions, {
      revisionID,
      parentRevisionID: project.currentRevisionID,
      createdAt,
      summary: kind,
      elementIDs: elements.map((element) => element.elementID),
      snapshotElements: elements,
    }],
    history: [...project.history, {
      eventID: `history-${crypto.randomUUID()}`,
      kind,
      revisionID,
      createdAt,
    }],
  }
}

const initialProject = () => {
  const documentID = `document-${crypto.randomUUID()}`
  const revisionID = `revision-${crypto.randomUUID()}`
  const createdAt = revisionTimestamp()
  const plan = currentTemplateCatalog?.entries.find((entry) => entry.templateID === 'public-plan')
  const title = plan ? officialTitleFor(plan) : '추진계획서'
  const elements = plan ? elementsFromTemplate(plan, title) : fallbackProjectElements()
  titleInput.value = title
  return {
    schemaVersion: 1,
    documentID,
    locale: 'ko-KR',
    title,
    currentRevisionID: revisionID,
    elements,
    assets: [],
    styles: officialProjectStyles(),
    templateBinding: {
      templateID: 'public-plan',
      version: plan?.version || '3.2',
      publishingAuthority: plan?.publishingAuthority || '기관 표준',
      requiredSections: plan?.requiredSections || ['개요', '추진 배경', '세부 추진계획', '예산 및 일정', '검토 및 결재'],
      checklistResults: plan
        ? Object.fromEntries((plan.checklist || []).map((item) => [item, false]))
        : { '목적과 대상': true, '추진 근거': true, '담당 부서': true, '시행 일정': true, '소요 예산': false, '결재선': false },
    },
    evidenceLinks: [],
    revisions: [{ revisionID, createdAt, summary: 'created', elementIDs: elements.map((element) => element.elementID) }],
    history: [{ eventID: `history-${crypto.randomUUID()}`, kind: 'created', revisionID, createdAt }],
    aiProposalHistory: [],
    providerConfigurations: [],
    consentGrants: [],
    redoRevisionIDs: [],
  }
}

const aiRequestDetails = () => {
  const provider = document.querySelector('[data-ai-provider]').value
  const endpointIdentity = document.querySelector('[data-ai-endpoint]').value.trim()
  const payloadScope = document.querySelector('[data-ai-payload-scope]').value
  const instruction = document.querySelector('[data-ai-free-form]').value.trim()
  return {
    provider, endpointIdentity, payloadScope, instruction,
    operation: instruction ? 'free-form' : selectedAIOperation,
  }
}

const selectedAIElementIDs = () => {
  const selection = document.getSelection()
  const anchor = selection?.anchorNode?.nodeType === Node.ELEMENT_NODE
    ? selection.anchorNode
    : selection?.anchorNode?.parentElement
  const target = anchor?.closest?.('[data-element-id]')
  return target ? [target.dataset.elementId] : []
}

const requestAIProposal = () => {
  const consent = document.querySelector('[data-ai-consent]')
  if (!consent.checked) {
    announce('선택한 문서·제공자·엔드포인트·작업·전송 범위에 대한 동의가 필요합니다.')
    consent.focus()
    return
  }
  const details = aiRequestDetails()
  const selectedElementIDs = selectedAIElementIDs()
  if (details.payloadScope === 'selected-elements' && !selectedElementIDs.length) {
    announce('문서에서 AI에 전송할 요소를 먼저 선택하세요.')
    page.focus()
    return
  }
  projectBridge('requestAIProposal', currentProject || initialProject(), {
    ...details, selectedElementIDs, consent: true,
  })
  announce('동의 범위를 확인하고 AI 제안을 요청했습니다. 문서는 변경되지 않았습니다.')
}

const diffLine = (prefix, text) => {
  const line = document.createElement('span')
  const words = text.trim().split(/\s+/)
  const tail = words.splice(Math.max(0, words.length - 2)).join(' ')
  line.append(document.createTextNode(`${prefix}: ${words.join(' ')}${words.length ? ' ' : ''}`))
  const keptTail = document.createElement('span')
  keptTail.className = 'ai-diff-tail'
  keptTail.textContent = tail
  line.append(keptTail)
  return line
}

const showAIProposal = (proposal) => {
  pendingAIProposal = proposal
  aiProposalReview.hidden = false
  aiProposalReview.querySelector('.ai-base-revision').textContent = '현재 저장본을 기준으로 변경 내용을 검토합니다.'
  aiProposalReview.querySelector('[data-ai-diff]').replaceChildren(...proposal.commands.map((command) => {
    const target = currentProject.elements.find((element) => element.elementID === command.targetElementID)
    const item = document.createElement('li')
    const choice = document.createElement('input')
    choice.type = 'checkbox'
    choice.checked = true
    choice.value = command.commandID
    const label = document.createElement('label')
    const targetName = document.createElement('strong')
    const persisted = proposal.diffs?.find((diff) => diff.commandID === command.commandID)
    const before = diffLine('변경 전', persisted?.before ?? target?.text ?? '')
    const after = diffLine('변경 후', persisted?.after ?? command.value)
    targetName.textContent = target?.text || '선택한 문서 항목'
    label.append(choice, targetName, before, after)
    item.append(label)
    return item
  }))
  aiProposalReview.querySelector('[data-ai-approve-selected]').focus()
}

const applyAIProposal = () => {
  if (!pendingAIProposal || pendingAIProposal.baseRevisionID !== currentProject.currentRevisionID) {
    announce('현재 리비전과 다른 오래된 제안은 적용할 수 없습니다.')
    return
  }
  const selected = new Set(Array.from(aiProposalReview.querySelectorAll('input:checked')).map((input) => input.value))
  const commandIDs = pendingAIProposal.commands.filter((command) => selected.has(command.commandID)).map((command) => command.commandID)
  if (!commandIDs.length) {
    announce('적용할 수 있는 스키마 유효 변경을 하나 이상 선택하세요.')
    return
  }
  projectBridge('applyAIProposal', null, { proposalID: pendingAIProposal.proposalID, commandIDs })
  announce('선택한 변경의 원자적 적용을 요청했습니다.')
}

const renderProject = (project, officialRuleState = null) => {
  currentProject = project
  titleInput.value = project.title
  applyPageMarginStyles(project.pageMargins)
  if (editorReady) editor.setProject(project)
  else project.elements.forEach((element) => {
    const target = page.querySelector(`[data-element-id="${CSS.escape(element.elementID)}"]`)
    if (target && element.contentHTML && target.innerHTML !== element.contentHTML) rehydrateRichContent(target, element.contentHTML)
    else if (target && !element.contentHTML && target.textContent.trim() !== element.text) target.textContent = element.text
  })
  renderGuidance(project.templateBinding)
  if (currentTemplateCatalog) renderTemplateCatalog(currentTemplateCatalog, false)
  if (officialRuleState) renderOfficialRuleState(officialRuleState)
}

const renderGuidance = (binding) => {
  const typeLabel = currentTemplateCatalog?.entries.find((entry) => entry.templateID === binding.templateID)?.documentType
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

const highestPrecedenceRules = (rules) => Array.from(rules.reduce((selected, rule) => {
  const current = selected.get(rule.field)
  if (!current || rule.precedence > current.precedence) selected.set(rule.field, rule)
  return selected
}, new Map()).values())

const renderOfficialRules = (rules, conflicts = []) => {
  const details = templatePanel.querySelector('.official-rules')
  const ruleItems = rules.map((rule) => {
    const item = document.createElement('li')
    item.textContent = `${rule.source} · ${rule.field} · 우선순위 ${rule.precedence} · 필수값 “${rule.requiredValue}”`
    return item
  })
  const conflictItems = conflicts.map((conflict) => {
    const item = document.createElement('li')
    item.dataset.officialRuleConflict = 'true'
    item.textContent = `충돌 경고 · ${conflict.warning}`
    return item
  })
  details.querySelector('ul').replaceChildren(...ruleItems, ...conflictItems)
  if (conflicts.length) details.open = true
}

const renderOfficialRuleState = (state) => {
  currentOfficialRuleState = state
  renderOfficialRules(state.appliedRules, state.conflicts)
}

const officialRuleWarning = (payload) => payload.officialRuleState?.conflicts?.[0]?.warning || ''

const renderTemplateCatalog = (catalog, announceStatus = true) => {
  currentTemplateCatalog = catalog
  templatePanel.querySelector('.catalog-version').textContent = `신뢰 카탈로그 ${catalog.catalogVersion} · ${catalog.publishedAt.slice(0, 10)}`
  templatePanel.querySelector('[data-template-action="rollback-template"]').disabled = !catalog.rollbackAvailable
  const ranked = [...catalog.entries].sort((left, right) => {
    const leftFavorite = studioPrefs.favorites.includes(left.templateID) ? 0 : 1
    const rightFavorite = studioPrefs.favorites.includes(right.templateID) ? 0 : 1
    return leftFavorite - rightFavorite
  })
  templatePanel.querySelector('.catalog-entries').replaceChildren(...ranked.map((entry) => {
    const item = document.createElement('li')
    const button = document.createElement('button')
    button.type = 'button'
    button.dataset.templateId = entry.templateID
    button.textContent = `${entry.documentType} · ${entry.templateID} v${entry.version}`
    button.setAttribute('aria-pressed', String(entry.templateID === currentProject?.templateBinding.templateID))
    button.addEventListener('click', () => applyCatalogEntry(entry))
    const favorite = document.createElement('button')
    favorite.type = 'button'
    favorite.className = 'favorite-toggle'
    favorite.setAttribute("data-easy-action", "toggle-favorite")
    favorite.dataset.templateId = entry.templateID
    const isFavorite = studioPrefs.favorites.includes(entry.templateID)
    favorite.setAttribute('aria-pressed', String(isFavorite))
    favorite.setAttribute('aria-label', `${entry.documentType} 즐겨찾기`)
    favorite.textContent = isFavorite ? '★' : '☆'
    favorite.addEventListener('click', () => toggleFavorite(entry.templateID))
    item.append(button, favorite)
    return item
  }))
  const pinnedID = currentProject?.templateBinding.templateID
  const pinnedEntry = catalog.entries.find((entry) => entry.templateID === pinnedID) || catalog.entries[0]
  renderOfficialRules(highestPrecedenceRules(pinnedEntry?.officialRules || []))
  const catalogEntry = catalog.entries.find((entry) => entry.templateID === pinnedID)
  if (!announceStatus) return
  if (catalogEntry && currentProject && catalogEntry.version !== currentProject.templateBinding.version) {
    announce(`새 템플릿 v${catalogEntry.version}을 확인했습니다. 현재 문서는 v${currentProject.templateBinding.version}에 고정되어 있습니다.`)
  } else {
    announce('서명된 신뢰 템플릿 카탈로그를 확인했습니다.')
  }
}

const scheduleAutosave = () => {
  window.clearTimeout(autosaveTimer)
  autosaveTimer = window.setTimeout(() => {
    if (!currentProject) return
    const autosavedProject = newRevision(currentProject, 'autosaved')
    if (autosavedProject === currentProject) return
    currentProject = autosavedProject
    projectBridge('autosave', currentProject)
  }, 600)
}

const activateGenOfficeEditor = () => {
  if (editorReady || typeof editor?.setProject !== 'function' || typeof editor.getElements !== 'function') return false
  editorReady = true
  editor.dataset.runtime = 'ready'
  renderProject(currentProject || initialProject())
  announce('GenOffice 편집기를 연결했습니다.')
  return true
}

const runEditorCommand = (command, value, control) => {
  if (!editorReady) {
    announce('GenOffice 편집기가 준비되지 않아 편집 명령을 실행하지 않았습니다.')
    return false
  }
  if (typeof editor.supportsCommand === 'function' && !editor.supportsCommand(command)) {
    if (control instanceof HTMLElement) {
      control.disabled = true
      control.title = '현재 GenOffice 편집기에서 지원하지 않는 명령입니다.'
    }
    announce('현재 GenOffice 편집기는 이 명령을 지원하지 않습니다.')
    return false
  }
  const handled = editor.command(command, value)
  syncFormatStates()
  if (!handled) {
    announce('현재 선택 위치에서는 문서 형식이 바뀌지 않았습니다.')
  }
  return handled
}

const syncFormatStates = (selectionState = editor.getSelectionState?.()) => {
  if (!selectionState) return
  if (selectionState.elementID) focusedEditorElementID = selectionState.elementID
  document.querySelectorAll('[data-command="bold"], [data-command="italic"], [data-command="underline"]').forEach((button) => {
    button.setAttribute('aria-pressed', String(Boolean(selectionState[button.dataset.command])))
  })
}

const officialProjectStyles = () => ([
  { styleID: 'style-title', name: '문서 제목', properties: { level: '1', preset: 'title', font: '헤드라인', macFont: 'Apple SD Gothic Neo', pointSize: '16', align: 'center' } },
  { styleID: 'style-section-heading', name: '□ 소제목', properties: { level: '2', preset: 'section-heading', font: '헤드라인', macFont: 'Apple SD Gothic Neo', pointSize: '16', marker: '□ ' } },
  { styleID: 'style-body', name: '○ 주요내용', properties: { preset: 'body', font: '휴먼명조', macFont: 'AppleMyungjo', pointSize: '15', marker: '○' } },
  { styleID: 'style-body-detail', name: '- 세부내용', properties: { preset: 'body-detail', font: '휴먼명조', macFont: 'AppleMyungjo', pointSize: '15', marker: '-' } },
  { styleID: 'style-reference-note', name: '※ 참고내용', properties: { preset: 'reference', font: '맑은고딕', macFont: 'Apple SD Gothic Neo', pointSize: '12', marker: '※' } },
  { styleID: 'style-annotation', name: '* 주석내용', properties: { preset: 'annotation', font: '맑은고딕', macFont: 'Apple SD Gothic Neo', pointSize: '12', marker: '*' } },
  { styleID: 'style-reference', name: '참고 글상자', properties: { preset: 'reference-box', font: '맑은고딕', macFont: 'Apple SD Gothic Neo', pointSize: '12' } },
  { styleID: 'style-table', name: '표', properties: { preset: 'public-table' } },
  { styleID: 'style-metadata', name: '문서 정보', properties: { preset: 'metadata' } },
  { styleID: 'style-review', name: '확인 필요', properties: { preset: 'review-required' } },
])

const elementsFromTemplate = (entry, title) => {
  const documentTitle = title || entry.documentType
  const elements = [{
    elementID: 'element-title',
    kind: 'heading',
    order: 0,
    text: documentTitle,
    styleID: 'style-title',
    evidenceIDs: [],
  }]
  entry.requiredSections.forEach((section, index) => {
    const slug = `section-${index + 1}`
    elements.push({
      elementID: `element-${slug}-heading`,
      kind: 'heading',
      order: elements.length,
      text: `□ ${section}`,
      styleID: 'style-section-heading',
      evidenceIDs: [],
    })
    elements.push({
      elementID: `element-${slug}-body`,
      kind: 'paragraph',
      order: elements.length,
      text: `○ ${section}`,
      styleID: 'style-body',
      evidenceIDs: [],
    })
  })
  return elements
}

const applyCatalogEntry = (entry) => {
  if (!currentProject) currentProject = initialProject()
  const title = officialTitleFor(entry)
  titleInput.value = title
  const elements = elementsFromTemplate(entry, title)
  const revisionID = `revision-${crypto.randomUUID()}`
  const createdAt = revisionTimestamp()
  currentProject = {
    ...currentProject,
    title,
    currentRevisionID: revisionID,
    elements,
    styles: officialProjectStyles(),
    templateBinding: {
      templateID: entry.templateID,
      version: entry.version,
      publishingAuthority: entry.publishingAuthority,
      requiredSections: entry.requiredSections,
      checklistResults: Object.fromEntries(entry.checklist.map((item) => [item, false])),
    },
    revisions: [...currentProject.revisions, {
      revisionID,
      parentRevisionID: currentProject.currentRevisionID,
      createdAt,
      summary: 'template-applied',
      elementIDs: elements.map((element) => element.elementID),
      snapshotElements: elements,
    }],
    history: [...currentProject.history, {
      eventID: `history-${crypto.randomUUID()}`,
      kind: 'template-applied',
      revisionID,
      createdAt,
    }],
  }
  renderProject(currentProject)
  projectBridge('save', currentProject)
  announce(`${entry.documentType} 템플릿을 적용했습니다.`)
}

const focusEditorElement = (section, explicitElementID) => {
  const headingID = explicitElementID || `element-${section}-heading`
  const bodyID = String(headingID).replace(/-heading$/, '-body')
  const elementID = (currentProject?.elements || []).some((element) => element.elementID === bodyID)
    ? bodyID
    : headingID
  if (!editorReady || !elementID || typeof editor.focusElement !== 'function' || !editor.focusElement(elementID)) {
    announce('GenOffice 편집기에서 선택한 문서 구조로 이동할 수 없습니다.')
    return false
  }
  focusedEditorElementID = elementID
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

const showExportResult = (receipt) => {
  const published = receipt.publishedFormats.length
  const blocked = receipt.blockedFormats.length
  const runtimeFailures = receipt.runtimeFailures || receipt.failures || []
  const failed = Array.isArray(receipt.failedFormats)
    ? receipt.failedFormats.length
    : runtimeFailures.length || receipt.results.filter((result) => result.runtimeFailure || result.failure).length
  const valueOrBlocked = (value, label) => value ? String(value) : `${label} 미제공(안전하게 확인 필요)`
  exportResult.querySelector('.export-summary').textContent = `게시 완료 ${published}개 · 차단 ${blocked}개 · 실패 ${failed}개 · 현재 저장본 기준`
  exportResult.querySelector('.export-results').replaceChildren(...receipt.results.map((result) => {
    const item = document.createElement('li')
    const failure = result.runtimeFailure || result.failure
    item.textContent = failure
      ? `${valueOrBlocked(result.format, '형식')} · 실행 실패 · ${valueOrBlocked(failure.message || failure.reason, '실패 사유')}`
      : `${valueOrBlocked(result.format, '형식')} · ${valueOrBlocked(result.fileName, '파일명')} · 구조 및 의미 검증 통과`
    if (!failure && result.downloadURL) {
      const link = document.createElement('a')
      link.href = result.downloadURL
      link.textContent = '내려받기'
      link.setAttribute('download', result.fileName || '')
      item.append(' · ', link)
    }
    return item
  }))
  const reports = [...receipt.lossReports, ...runtimeFailures.map((failure) => ({
    ...failure,
    classification: 'runtime-failure',
    fallback: failure.fallback || failure.message || failure.reason,
  }))]
  exportResult.querySelector('.loss-report ul').replaceChildren(...reports.map((report) => {
    const item = document.createElement('li')
    const disposition = report.classification === 'semantic-loss'
      ? '형식 차단'
      : report.classification === 'runtime-failure' ? '실행 실패' : '동의 후 시각 변환'
    const location = document.createElement('strong')
    location.className = 'loss-location'
    location.textContent = [
      valueOrBlocked(report.format, '형식'),
      `분류 ${valueOrBlocked(report.classification, '분류')}`,
      disposition,
      `요소 ID ${valueOrBlocked(report.elementID, '요소 ID')}`,
      `요소 경로 ${valueOrBlocked(report.elementPath, '요소 경로')}`,
      `기능 ${valueOrBlocked(report.capability, '기능')}`,
    ].join(' · ')
    const fallback = document.createElement('span')
    fallback.textContent = `대체: ${valueOrBlocked(report.fallback, '대체 방법')}`
    item.append(location, fallback)
    return item
  }))
  openDialog(exportResult)
}

const showBatchExportProgress = (manifest, recovered = false) => {
  const stateLabels = {
    queued: '대기',
    exporting: '내보내는 중',
    validated: '검증 완료',
    published: '게시 완료',
    failed: '실패',
    cancelled: '취소',
  }
  const completed = manifest.items.reduce((total, item) => total + item.progressCompleted, 0)
  const total = manifest.items.reduce((sum, item) => sum + item.progressTotal, 0)
  const published = manifest.items.filter((item) => item.state === 'published').length
  const failed = manifest.items.filter((item) => item.state === 'failed').length
  const cancelled = manifest.items.filter((item) => item.state === 'cancelled').length
  const cleanupLabel = manifest.cleanupState === 'clean' ? '정리 완료' : '정리 대기'
  batchExportProgress.querySelector('progress').value = completed
  batchExportProgress.querySelector('progress').max = Math.max(total, 1)
  batchExportProgress.querySelector('.batch-export-summary').textContent = recovered
    ? `중단 작업 복구 완료 · 게시 ${published} · 실패 ${failed} · ${cleanupLabel}`
    : `게시 ${published} · 실패 ${failed} · 취소 ${cancelled}`
  batchExportProgress.querySelector('.batch-export-items').replaceChildren(...manifest.items.map((item) => {
    const row = document.createElement('li')
    row.dataset.state = item.state
    const displayName = item.documentDisplayName || '문서 표시명 미제공(안전하게 확인 필요)'
    const documentID = item.documentID || '문서 ID 미제공(안전하게 확인 필요)'
    row.textContent = `${displayName} · ID ${documentID} · ${item.format.toUpperCase()} · ${stateLabels[item.state] || item.state} · ${item.progressCompleted}/${item.progressTotal}`
    return row
  }))
  const cancel = batchExportProgress.querySelector('[data-action="cancel-batch-export"]')
  const close = batchExportProgress.querySelector('[data-action="close-batch-export-progress"]')
  const retry = batchExportProgress.querySelector('[data-action="retry-batch-export"]')
  activeBatchOperationID = manifest.state === 'running' ? manifest.operationID : null
  retry.hidden = manifest.state === 'running' || !manifest.items.some((item) => item.state === 'failed' || item.state === 'cancelled')
  activeBatchRetryOperationID = retry.hidden ? null : manifest.operationID
  cancel.disabled = manifest.state !== 'running'
  cancel.hidden = manifest.state !== 'running'
  close.disabled = manifest.state === 'running'
  if (!batchExportProgress.open) openDialog(batchExportProgress)
}

window.projectStoreReceive = ({ event, payload }) => {
  if (event === 'templateCatalog') {
    currentOfficialRuleState = null
    renderTemplateCatalog(payload.project)
    return
  }
  if (event === 'templateCatalogCancelled') {
    announce('템플릿 카탈로그 업데이트를 취소했습니다.')
    return
  }
  if (event === 'studioPrefs') {
    applyStudioPrefs(payload.project)
    return
  }
  if (event === 'documentLibrary') {
    libraryEntries = payload.project?.entries || []
    return
  }
  if (event === 'libraryDocument') {
    applyLibraryMerge(payload.project)
    return
  }
  if (event === 'empty') {
    currentProject = initialProject()
    projectBridge('save', currentProject)
    return
  }
  if (['opened', 'recovered'].includes(event)) {
    renderProject(payload.project, payload.officialRuleState)
    announce(officialRuleWarning(payload) || (event === 'recovered' ? '중단 전 자동저장 상태를 복구했습니다.' : '앱 프로젝트를 다시 열었습니다.'))
    return
  }
  if (event === 'saved') {
    if (!applyBridgeProject(payload.project, payload.officialRuleState)) return
    announce(officialRuleWarning(payload) || '앱 프로젝트에 저장했습니다.')
    return
  }
  if (event === 'autosaved') {
    if (payload.project && !applyBridgeProject(payload.project, payload.officialRuleState)) return
    announce(officialRuleWarning(payload) || '자동저장됨')
    return
  }
  if (event === 'officialRuleEnforced') {
    if (!applyBridgeProject(payload.project, payload.officialRuleState)) return
    announce(officialRuleWarning(payload) || '현재 서명 카탈로그의 공식 규칙을 내보내기 원본에 적용했습니다.')
    return
  }
  if (event === 'inspection') {
    showInspection(payload.project)
    return
  }
  if (event === 'exportCompleted') {
    resetExportConsent()
    showExportResult(payload.project)
    announce(`선택 형식 ${payload.project.publishedFormats.length}개를 검증 후 게시했습니다.`)
    return
  }
  if (event === 'exportCancelled') {
    resetExportConsent()
    announce('내보내기를 취소했습니다. 게시된 파일은 없습니다.')
    return
  }
  if (event === 'batchExportStarted') {
    activeBatchOperationID = payload.operationID
    activeBatchRetryOperationID = null
    batchExportProgress.querySelector('.batch-export-summary').textContent = '일괄 내보내기를 준비하고 있습니다.'
    batchExportProgress.querySelector('[data-action="close-batch-export-progress"]').disabled = true
    batchExportProgress.querySelector('[data-action="cancel-batch-export"]').hidden = false
    batchExportProgress.querySelector('[data-action="retry-batch-export"]').hidden = true
    if (!batchExportProgress.open) openDialog(batchExportProgress)
    announce('일괄 내보내기를 시작했습니다.')
    return
  }
  if (event === 'batchExportProgress' || event === 'batchExportCompleted') {
    if (event === 'batchExportCompleted') resetExportConsent()
    showBatchExportProgress(payload.project)
    announce(event === 'batchExportCompleted' ? '일괄 내보내기 결과를 기록했습니다.' : '문서별 형식 내보내기를 진행하고 있습니다.')
    return
  }
  if (event === 'batchExportRecovered') {
    showBatchExportProgress(payload.project, true)
    announce('중단된 일괄 내보내기 상태와 정리 결과를 복구했습니다.')
    return
  }
  if (event === 'batchExportFailed') {
    activeBatchRetryOperationID = activeBatchOperationID
    activeBatchOperationID = null
    batchExportProgress.querySelector('.batch-export-summary').textContent = `일괄 내보내기 실패 · ${payload.message}`
    batchExportProgress.querySelector('[data-action="close-batch-export-progress"]').disabled = false
    batchExportProgress.querySelector('[data-action="cancel-batch-export"]').disabled = true
    batchExportProgress.querySelector('[data-action="cancel-batch-export"]').hidden = true
    announce('일괄 내보내기가 실패했습니다. 진단을 확인한 뒤 새 작업으로 다시 시도하세요.')
    return
  }
  if (event === 'batchExportCancelling') {
    announce('현재 검증 단계를 마친 뒤 나머지 항목을 취소합니다.')
    return
  }
  if (event === 'batchExportCancelled') {
    resetExportConsent()
    announce('일괄 내보내기 선택을 취소했습니다.')
    return
  }
  if (event === 'aiProposal') {
    renderProject(payload.project, payload.officialRuleState)
    showAIProposal(payload.project.aiProposalHistory.at(-1))
    announce('AI 제안을 받았습니다. 변경 전·후를 검토한 뒤 승인할 항목을 선택하세요.')
    return
  }
  if (event === 'aiProviderUnavailable') {
    renderProject(payload.project, payload.officialRuleState)
    announce('선택한 AI 제공자 자격 증명이 구성되지 않았습니다. 오프라인 편집과 내보내기는 계속 사용할 수 있습니다.')
    return
  }
  if (event === 'aiProviderConfigured') {
    renderProject(payload.project, payload.officialRuleState)
    document.querySelector('[data-ai-secret]').value = ''
    announce('제공자 자격 증명을 macOS 키체인에 저장했습니다.')
    return
  }
  if (event === 'aiConsentRevoked') {
    renderProject(payload.project, payload.officialRuleState)
    document.querySelector('[data-ai-consent]').checked = false
    announce('이 요청 범위의 AI 전송 동의를 철회했습니다.')
    return
  }
  if (event === 'aiProposalApplied') {
    renderProject(payload.project, payload.officialRuleState)
    pendingAIProposal = null
    aiProposalReview.hidden = true
    announce('선택한 AI 제안을 하나의 새 리비전으로 적용했습니다.')
    aiWorkspace.querySelector('[data-ai-request]').focus()
    return
  }
  if (event === 'aiProposalRejected') {
    renderProject(payload.project, payload.officialRuleState)
    pendingAIProposal = null
    aiProposalReview.hidden = true
    announce('AI 제안을 거절하고 기록에 보존했습니다.')
    aiWorkspace.querySelector('[data-ai-request]').focus()
    return
  }
  announce(payload.message || '프로젝트 작업을 완료하지 못했습니다.')
}

document.querySelectorAll('[data-project-action]').forEach((button) => {
  button.addEventListener('click', () => {
    const action = button.dataset.projectAction
    if (action === 'new') {
      currentProject = initialProject()
      renderProject(currentProject)
      projectBridge('save', currentProject)
      return
    }
    if (action === 'save') {
      const savedProject = newRevision(currentProject || initialProject(), 'saved')
      if (savedProject === currentProject) return
      currentProject = savedProject
      projectBridge('save', currentProject)
      return
    }
    projectBridge(action)
  })
})

document.querySelector('[data-action="close-inspector"]').addEventListener('click', () => closeDialog(inspector))
document.querySelector('[data-action="close-export-result"]').addEventListener('click', () => closeDialog(exportResult))
document.querySelector('[data-action="close-batch-export-progress"]').addEventListener('click', () => {
  if (!activeBatchOperationID) closeDialog(batchExportProgress)
})
batchExportProgress.addEventListener('cancel', (event) => {
  if (activeBatchOperationID) event.preventDefault()
})
document.querySelector('[data-action="cancel-batch-export"]').addEventListener('click', () => {
  projectBridge('cancelBatchExport')
})
document.querySelector('[data-action="retry-batch-export"]').addEventListener('click', () => {
  if (!activeBatchRetryOperationID) return
  projectBridge('retryBatchExport', null, { operationID: activeBatchRetryOperationID })
})
document.querySelector('[data-action="open-ai"]').addEventListener('click', (event) => openDialog(aiWorkspace, event.currentTarget))
document.querySelector('[data-action="close-ai"]').addEventListener('click', () => closeDialog(aiWorkspace))
document.querySelector('[data-action="open-export"]').addEventListener('click', (event) => openDialog(exportSetup, event.currentTarget))
document.querySelectorAll('[data-action="close-export-setup"]').forEach((button) => {
  button.addEventListener('click', () => {
    resetExportConsent()
    closeDialog(exportSetup)
  })
})
exportSetup.addEventListener('cancel', resetExportConsent)
editor.addEventListener('public-document-genoffice-change', (event) => {
  if (editorReady && Array.isArray(event.detail?.elements)) scheduleAutosave()
})
editor.addEventListener('public-document-genoffice-selection-change', (event) => {
  syncFormatStates(event.detail)
})
titleInput.addEventListener('input', scheduleAutosave)

document.querySelectorAll('[data-command]').forEach((button) => {
  button.addEventListener('click', () => {
    if (runEditorCommand(button.dataset.command, undefined, button)) announce(button.getAttribute('aria-label') || button.textContent.trim())
  })
})

document.querySelectorAll('[data-format]').forEach((select) => {
  select.addEventListener('change', () => {
    const value = select.dataset.format === 'fontSize' ? Number(select.value) : select.value
    if (runEditorCommand(select.dataset.format, value, select)) announce(`${select.getAttribute('aria-label')}을 변경했습니다.`)
  })
})

outlineToggle.addEventListener('click', () => {
  const hidden = workspace.classList.toggle('outline-hidden')
  outlineToggle.setAttribute('aria-pressed', String(!hidden))
  announce(hidden ? '문서 구조를 닫았습니다.' : '문서 구조를 열었습니다.')
})

const syncOutlineForViewport = () => {
  workspace.classList.toggle('outline-hidden', compactLayout.matches)
  outlineToggle.setAttribute('aria-pressed', String(!compactLayout.matches))
}

compactLayout.addEventListener('change', syncOutlineForViewport)

outlineList.addEventListener('click', (event) => {
  const button = event.target.closest('[data-section]')
  if (!button) return
  if (!focusEditorElement(button.dataset.section, button.dataset.elementId)) return
  setOutlineCurrent(button)
})

document.querySelectorAll('[data-template-action]').forEach((button) => {
  button.addEventListener('click', () => {
    const action = button.dataset.templateAction
    projectBridge(action === 'update-template' ? 'updateTemplateCatalog' : 'rollbackTemplateCatalog')
  })
})

document.querySelector('[data-action="marker"]').addEventListener('click', (event) => {
  if (runEditorCommand('insertText', ' [확인 필요]', event.currentTarget)) announce('확인 필요 표시를 삽입했습니다.')
})

document.querySelector('[data-action="check"]').addEventListener('click', () => {
  announce('필수항목 6개 중 4개를 작성했습니다. 소요 예산과 결재선을 확인하세요.')
})

document.querySelectorAll('[data-ai-operation]').forEach((button) => {
  button.addEventListener('click', () => {
    selectedAIOperation = button.dataset.aiOperation
    document.querySelectorAll('[data-ai-operation]').forEach((candidate) => candidate.setAttribute('aria-pressed', String(candidate === button)))
    announce(`${button.textContent.trim()} 작업을 선택했습니다.`)
  })
})

document.querySelector('[data-ai-request]').addEventListener('click', requestAIProposal)
document.querySelector('[data-ai-configure]').addEventListener('click', () => {
  const secret = document.querySelector('[data-ai-secret]').value
  if (!secret) {
    announce('키체인에 저장할 제공자 자격 증명을 입력하세요.')
    document.querySelector('[data-ai-secret]').focus()
    return
  }
  projectBridge('configureAIProvider', currentProject || initialProject(), { ...aiRequestDetails(), secret })
})
document.querySelector('[data-ai-approve-selected]').addEventListener('click', applyAIProposal)
document.querySelector('[data-ai-reject]').addEventListener('click', () => {
  if (!pendingAIProposal) return
  projectBridge('rejectAIProposal', null, { proposalID: pendingAIProposal.proposalID })
  announce('AI 제안 거절을 기록하고 있습니다.')
})
document.querySelector('[data-ai-revoke]').addEventListener('click', () => {
  projectBridge('revokeAIConsent', currentProject || initialProject(), aiRequestDetails())
  announce('AI 전송 동의를 철회하고 있습니다.')
})

document.querySelectorAll('[data-ai-provider], [data-ai-endpoint], [data-ai-payload-scope], [data-ai-free-form], [data-ai-operation]').forEach((input) => {
  input.addEventListener('input', () => { document.querySelector('[data-ai-consent]').checked = false })
  input.addEventListener('change', () => { document.querySelector('[data-ai-consent]').checked = false })
})

document.addEventListener('keydown', (event) => {
  if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'y') return
  event.preventDefault()
  runEditorCommand('redo')
})

document.querySelector('[data-action="export"]').addEventListener('click', () => {
  const formats = Array.from(document.querySelectorAll('[name="export-format"]:checked')).map((input) => input.value)
  if (!formats.length) {
    announce('내보낼 형식을 하나 이상 선택하세요.')
    return
  }
  const flatteningConsent = exportConsent.checked
  resetExportConsent()
  const exportProject = newRevision(currentProject || initialProject(), 'export-snapshot')
  if (exportProject === currentProject) {
    announce('내보낼 문서 스냅샷을 만들지 못했습니다. 편집기 상태를 확인하세요.')
    return
  }
  currentProject = exportProject
  closeDialog(exportSetup)
  announce('내보내기를 준비하고 있습니다.')
  const details = {
    formats,
    flatteningConsent,
  }
  if (document.querySelector('[data-batch-export]').checked) {
    projectBridge('batchExport', currentProject, details)
  } else {
    projectBridge('export', currentProject, details)
  }
})

document.querySelector('.zoom-control input').addEventListener('input', (event) => {
  const zoom = Number(event.target.value)
  editor.style.zoom = zoom / 100
  document.querySelector('.zoom-control output').value = `${zoom}%`
})

const isLocalWeb = () => document.body.dataset.host === 'local-web'

const normalizeClientPrefs = (prefs) => {
  const allowed = new Set([60000, 180000, 300000, 600000])
  return {
    autosaveIntervalMs: allowed.has(prefs?.autosaveIntervalMs) ? prefs.autosaveIntervalMs : 180000,
    favorites: Array.isArray(prefs?.favorites)
      ? prefs.favorites.map((item) => String(item).slice(0, 80)).filter(Boolean).slice(0, 20)
      : [],
    myForms: Array.isArray(prefs?.myForms)
      ? prefs.myForms.flatMap((item) => {
        const name = String(item?.name || '').trim().slice(0, 80)
        const text = String(item?.text || '').trim().slice(0, 4000)
        const id = String(item?.id || '').trim().slice(0, 80)
        return name && text ? [{ id: id || `form-${name}`, name, text }] : []
      }).slice(0, 20)
      : [],
  }
}

const applyPageMarginStyles = (margins) => {
  const box = margins || { top: 20, right: 20, bottom: 20, left: 20 }
  const targets = [document.documentElement, editor, page].filter(Boolean)
  targets.forEach((target) => {
    target.style.setProperty('--easy-page-pad-top', `${box.top}mm`)
    target.style.setProperty('--easy-page-pad-right', `${box.right}mm`)
    target.style.setProperty('--easy-page-pad-bottom', `${box.bottom}mm`)
    target.style.setProperty('--easy-page-pad-left', `${box.left}mm`)
  })
}

const renderMyForms = () => {
  const select = document.querySelector('[data-easy="my-form"]')
  if (!select) return
  const current = select.value
  select.replaceChildren(...(studioPrefs.myForms.length ? studioPrefs.myForms : [{ id: '', name: '저장된 양식 없음', text: '' }]).map((form) => {
    const option = document.createElement('option')
    option.value = form.id
    option.textContent = form.name
    return option
  }))
  if (studioPrefs.myForms.some((form) => form.id === current)) select.value = current
}

const applyStudioPrefs = (prefs, persist = false) => {
  studioPrefs = normalizeClientPrefs(prefs)
  const select = document.querySelector('[data-easy="autosave-interval"]')
  if (select) select.value = String(studioPrefs.autosaveIntervalMs)
  renderMyForms()
  if (currentTemplateCatalog) renderTemplateCatalog(currentTemplateCatalog, false)
  window.clearInterval(periodicSaveTimer)
  periodicSaveTimer = window.setInterval(() => {
    if (!currentProject) return
    const snapshot = newRevision(currentProject, 'autosaved')
    if (snapshot === currentProject) return
    currentProject = snapshot
    projectBridge('autosave', currentProject)
  }, studioPrefs.autosaveIntervalMs)
  if (persist) persistPrefs(studioPrefs)
}

const persistPrefs = (prefs) => {
  studioPrefs = normalizeClientPrefs(prefs)
  if (isLocalWeb()) projectBridge('saveStudioPrefs', null, { prefs: studioPrefs })
}

const toggleFavorite = (templateID) => {
  const favorites = studioPrefs.favorites.includes(templateID)
    ? studioPrefs.favorites.filter((item) => item !== templateID)
    : [...studioPrefs.favorites, templateID]
  persistPrefs({ ...studioPrefs, favorites })
  applyStudioPrefs({ ...studioPrefs, favorites })
  announce(favorites.includes(templateID) ? '즐겨찾기에 넣었습니다.' : '즐겨찾기를 해제했습니다.')
}

const liveElements = () => {
  const persisted = currentProject?.elements || fallbackProjectElements()
  const live = projectElements({ silent: true })
  const base = live || persisted
  const missingTables = persisted.filter((element) => (
    isEasyTableElement(element) && !base.some((item) => item.elementID === element.elementID)
  ))
  return missingTables.length ? [...base, ...missingTables] : base
}

const commitProjectElements = (elements, summary, message, extra = {}) => {
  if (!currentProject) currentProject = initialProject()
  const nextElements = elements.map((element, order) => ({ ...element, order }))
  const revisionID = `revision-${crypto.randomUUID()}`
  const createdAt = revisionTimestamp()
  currentProject = {
    ...currentProject,
    ...extra,
    elements: nextElements,
    currentRevisionID: revisionID,
    revisions: [...currentProject.revisions, {
      revisionID,
      parentRevisionID: currentProject.currentRevisionID,
      createdAt,
      summary,
      elementIDs: nextElements.map((element) => element.elementID),
      snapshotElements: nextElements,
    }],
    history: [...currentProject.history, {
      eventID: `history-${crypto.randomUUID()}`,
      kind: summary,
      revisionID,
      createdAt,
    }],
  }
  renderProject(currentProject)
  projectBridge('save', currentProject)
  announce(message)
}

const insertTargetIndex = (elements) => {
  const focused = elements.findIndex((element) => element.elementID === focusedEditorElementID)
  if (focused >= 0 && !isTitleElement(elements[focused])) return focused
  const body = elements.findIndex((element) => element.kind === 'paragraph' && !isTitleElement(element))
  if (body >= 0) return body
  return elements.findIndex((element) => !isTitleElement(element))
}

const hangingIndentTargetIndex = (elements) => {
  const focused = elements.findIndex((element) => element.elementID === focusedEditorElementID)
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
  const focused = elements.find((element) => element.elementID === focusedEditorElementID)
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
  const focused = tables.find((element) => element.elementID === focusedEditorElementID)
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
  const heading = pendingMergeHeading || incoming.title || '취합'
  pendingMergeHeading = ''
  commitProjectElements(
    tools.mergeDocumentElements(liveElements(), incoming.elements || [], heading),
    'document-merged',
    `${incoming.title || '문서'}를 취합했습니다.`,
  )
}

const persistLibraryDocument = (project) => {
  const entry = { documentID: project.documentID, title: project.title }
  libraryEntries = [...libraryEntries.filter((item) => item.documentID !== entry.documentID), entry]
  libraryProjects[project.documentID] = project
  if (isLocalWeb()) projectBridge('saveLibraryDocument', project)
  announce('문서함에 보관했습니다.')
}

const requestLibraryDocument = (documentID) => {
  if (libraryProjects[documentID]) {
    applyLibraryMerge(libraryProjects[documentID])
    return
  }
  if (isLocalWeb()) {
    projectBridge('loadLibraryDocument', null, { documentID })
    return
  }
  applyLibraryMerge(libraryProjects[documentID])
}

const openEasyTool = (title, fields, onConfirm, opener) => {
  easyToolDialog.querySelector('#easy-tool-title').textContent = title
  const form = easyToolDialog.querySelector('[data-easy-fields]')
  form.replaceChildren(...fields.map((field) => {
    const label = document.createElement('label')
    const caption = document.createElement('span')
    caption.textContent = field.label
    const input = field.type === 'textarea'
      ? document.createElement('textarea')
      : field.type === 'select'
        ? document.createElement('select')
        : document.createElement('input')
    if (field.type !== 'textarea' && field.type !== 'select') input.type = field.type || 'text'
    input.name = field.name
    if (field.type === 'select') {
      (field.options || []).forEach((option) => {
        const item = document.createElement('option')
        item.value = option.value
        item.textContent = option.label
        input.append(item)
      })
    }
    input.value = field.value || ''
    if (field.type === 'select' && !input.value && input.options.length) input.selectedIndex = 0
    label.append(caption, input)
    return label
  }))
  pendingEasyConfirm = onConfirm
  openDialog(easyToolDialog, opener)
}

const readEasyFields = () => Object.fromEntries(new FormData(easyToolDialog.querySelector('[data-easy-fields]')))

const handleEasyAction = (action, control) => {
  const tools = easyTools()
  if (!tools) return announce('작성 도구를 불러오지 못했습니다.')
  if (action === 'insert-date') return insertPlainText(tools.formatOfficialDate(new Date()), '오늘 날짜를 넣었습니다.')
  if (action === 'insert-date-range') {
    const today = new Date()
    const start = new Date(today.getFullYear(), today.getMonth(), 1)
    return openEasyTool('기간 넣기', [
      { name: 'start', label: '시작일', type: 'date', value: tools.localISODate(start) },
      { name: 'end', label: '종료일', type: 'date', value: tools.localISODate(today) },
    ], (fields) => {
      const text = tools.formatOfficialDateRange(fields.start, fields.end)
      if (!text) return announce('종료일은 시작일 이후여야 합니다.')
      insertPlainText(text, '기간을 넣었습니다.')
    }, control)
  }
  if (action === 'insert-currency') {
    const selected = document.getSelection()?.toString() || ''
    return openEasyTool('금액 → 한글', [
      { name: 'amount', label: '금액', type: 'text', value: tools.extractAmountFromText(selected) || '12500000' },
    ], (fields) => {
      const text = tools.numberToKoreanCurrency(fields.amount)
      if (!text) return announce('숫자 금액을 입력하세요.')
      insertPlainText(text, '한글 금액을 넣었습니다.')
    }, control)
  }
  if (action === 'normalize-markers') {
    const elements = liveElements().map((element) => {
      const text = tools.normalizeOfficialMarkers(element.text || '')
      return { ...element, text, contentHTML: element.contentHTML ? tools.normalizeOfficialMarkers(element.contentHTML) : text }
    })
    return commitProjectElements(elements, 'easy-markers', 'ㅁ/ㅇ/ㆍ 표기를 □/○/- 로 정리했습니다.')
  }
  if (action === 'insert-my-form') {
    const form = studioPrefs.myForms.find((item) => item.id === document.querySelector('[data-easy="my-form"]').value)
    if (!form) return announce('먼저 내 양식을 저장하세요.')
    return insertPlainText(form.text, `${form.name} 양식을 넣었습니다.`)
  }
  if (action === 'save-my-form') {
    const focused = liveElements().find((element) => element.elementID === focusedEditorElementID)
    return openEasyTool('내 양식 저장', [
      { name: 'name', label: '양식 이름', type: 'text', value: '자주 쓰는 문장' },
      { name: 'text', label: '넣을 내용', type: 'textarea', value: focused?.text || '○ ' },
    ], (fields) => {
      const form = { id: `form-${crypto.randomUUID()}`, name: fields.name, text: fields.text }
      const next = { ...studioPrefs, myForms: [...studioPrefs.myForms, form] }
      persistPrefs(next)
      applyStudioPrefs(next)
      announce('내 양식을 저장했습니다. 서명 템플릿은 바꾸지 않습니다.')
    }, control)
  }
  if (action === 'save-library') {
    const snapshot = newRevision(currentProject || initialProject(), 'library-saved')
    if (snapshot !== currentProject) currentProject = snapshot
    return persistLibraryDocument(currentProject)
  }
  if (action === 'merge-library') {
    if (!libraryEntries.length) return announce('먼저 문서함에 보관하세요.')
    return openEasyTool('문서 취합', [
      { name: 'documentID', label: '문서함', type: 'select', options: libraryEntries.map((item) => ({ value: item.documentID, label: item.title })), value: libraryEntries[0].documentID },
      { name: 'heading', label: '취합 소제목', type: 'text', value: '취합' },
    ], (fields) => {
      pendingMergeHeading = fields.heading
      requestLibraryDocument(fields.documentID)
    }, control)
  }
  if (action === 'insert-table') {
    return openEasyTool('표 넣기', [
      { name: 'rows', label: '행', type: 'number', value: '2' },
      { name: 'cols', label: '열', type: 'number', value: '3' },
    ], (fields) => {
      const html = tools.setTableBorders(tools.createTableHTML(fields.rows, fields.cols), 'all')
      const elements = liveElements()
      const index = Math.max(elements.findIndex((element) => element.elementID === focusedEditorElementID), 0)
      elements.splice(index + 1, 0, {
        elementID: `element-table-${crypto.randomUUID()}`,
        kind: 'table',
        order: index + 1,
        text: tablePlainText(html),
        contentHTML: html,
        inlineIDs: [],
        styleID: 'style-table',
        evidenceIDs: [],
      })
      commitProjectElements(elements, 'easy-table', '표를 넣었습니다.')
    }, control)
  }
  if (action === 'add-table-row') return updateTableElement((html) => tools.addTableRow(html), '표 행을 추가했습니다.')
  if (action === 'clean-table') return updateTableElement((html) => tools.cleanPastedTable(html), '표 칸을 정리했습니다.')
  if (action === 'set-table-borders') return updateTableElement((html) => tools.setTableBorders(html, 'all'), '표 테두리를 적용했습니다.')
  if (action === 'set-table-fill') {
    return openEasyTool('셀 색', [
      { name: 'row', label: '행 번호', type: 'number', value: '1' },
      { name: 'col', label: '열 번호', type: 'number', value: '1' },
      { name: 'color', label: '색', type: 'color', value: '#fff4cc' },
    ], (fields) => updateTableElement(
      (html) => tools.setTableCellFill(html, Math.max(0, Number(fields.row) - 1), Math.max(0, Number(fields.col) - 1), fields.color),
      '셀 색을 넣었습니다.',
    ), control)
  }
  if (action === 'page-margins') {
    const margins = tools.pageMargins(control.dataset.easyMargin || 'normal')
    return commitProjectElements(liveElements(), 'easy-margins', '페이지 여백을 바꿨습니다.', { pageMargins: margins })
  }
  if (action === 'hanging-indent') {
    const elements = liveElements()
    const index = hangingIndentTargetIndex(elements)
    if (index < 0) return announce('내어쓸 문장을 먼저 선택하세요.')
    const text = tools.hangingIndent(elements[index].text)
    elements[index] = { ...elements[index], text, contentHTML: text }
    return commitProjectElements(elements, 'easy-indent', '둘째 줄부터 맞춰 내어썼습니다.')
  }
  if (action === 'confirm-easy-tool') {
    const fields = readEasyFields()
    const confirm = pendingEasyConfirm
    pendingEasyConfirm = null
    closeDialog(easyToolDialog)
    return confirm?.(fields)
  }
}

document.querySelectorAll('.ribbon-tab[data-tab]').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.ribbon-tab[data-tab]').forEach((candidate) => {
      const selected = candidate === tab
      candidate.classList.toggle('active', selected)
      candidate.setAttribute('aria-selected', String(selected))
    })
    document.querySelectorAll('.ribbon[role="tabpanel"]').forEach((panel) => {
      panel.hidden = panel.id !== tab.getAttribute('aria-controls')
    })
    announce(`${tab.textContent.trim()} 도구를 열었습니다.`)
  })
})

document.querySelectorAll('[data-easy-action]').forEach((control) => {
  control.addEventListener('click', () => handleEasyAction(control.dataset.easyAction, control))
})

document.querySelectorAll('[data-action="close-easy-tool"]').forEach((button) => {
  button.addEventListener('click', () => {
    pendingEasyConfirm = null
    closeDialog(easyToolDialog)
  })
})

document.querySelector('[data-easy="autosave-interval"]').addEventListener('change', (event) => {
  persistPrefs({ ...studioPrefs, autosaveIntervalMs: Number(event.target.value) })
  applyStudioPrefs({ ...studioPrefs, autosaveIntervalMs: Number(event.target.value) })
  announce('자동저장 간격을 바꿨습니다.')
})

editor.addEventListener('paste', (event) => {
  const tools = easyTools()
  const html = event.clipboardData?.getData('text/html') || ''
  if (!tools || !/<table/i.test(html)) return
  event.preventDefault()
  const cleaned = tools.setTableBorders(tools.cleanPastedTable(html), 'all')
  const elements = liveElements()
  const index = Math.max(elements.findIndex((element) => element.elementID === focusedEditorElementID), 0)
  elements.splice(index + 1, 0, {
    elementID: `element-table-${crypto.randomUUID()}`,
    kind: 'table',
    order: index + 1,
    text: tablePlainText(cleaned),
    contentHTML: cleaned,
    inlineIDs: [],
    styleID: 'style-table',
    evidenceIDs: [],
  })
  commitProjectElements(elements, 'easy-table', '붙여넣은 표를 정리해 넣었습니다.')
}, true)

syncOutlineForViewport()
if (!(window.webkit && window.webkit.messageHandlers.projectStore)) {
  document.body.dataset.host = 'local-web'
}
applyStudioPrefs(studioPrefs)
currentProject = initialProject()
editor.addEventListener('public-document-genoffice-ready', activateGenOfficeEditor)
if (!activateGenOfficeEditor()) announce('GenOffice 편집기 번들을 불러오지 못해 편집을 차단했습니다.')
projectBridge('ready')
