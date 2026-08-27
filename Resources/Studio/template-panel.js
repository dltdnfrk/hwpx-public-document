(function (studio) {
  const store = studio.state
  const { templatePanel, titleInput, aiProposalReview } = studio.dom
  const announce = (...args) => studio.announce(...args)
  const toggleFavorite = (...args) => studio.toggleFavorite(...args)
  const initialProject = (...args) => studio.initialProject(...args)
  const elementsFromTemplate = (...args) => studio.elementsFromTemplate(...args)
  const revisionTimestamp = (...args) => studio.revisionTimestamp(...args)
  const officialProjectStyles = (...args) => studio.officialProjectStyles(...args)
  const renderProject = (...args) => studio.renderProject(...args)
  const projectBridge = (...args) => studio.projectBridge(...args)

  const officialTitleFor = (entry) => (
    (entry?.officialRules || []).find((rule) => rule.field === 'title')?.requiredValue || entry?.documentType || '추진계획서'
  )

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
    const lintItems = (store.currentOfficialRuleState?.styleLint?.findings || []).map((finding) => {
      const item = document.createElement('li')
      item.dataset.styleLint = finding.ruleID
      item.textContent = `문체 린트(dry_run) · ${finding.citation} · ${finding.message}`
      return item
    })
    details.querySelector('ul').replaceChildren(...ruleItems, ...conflictItems, ...lintItems)
    if (conflicts.length || lintItems.length) details.open = true
  }

  const renderOfficialRuleState = (state) => {
    store.currentOfficialRuleState = state
    renderOfficialRules(state.appliedRules, state.conflicts)
  }

  const officialRuleWarning = (payload) => payload.officialRuleState?.conflicts?.[0]?.warning || ''

  const renderTemplateCatalog = (catalog, announceStatus = true) => {
    store.currentTemplateCatalog = catalog
    templatePanel.querySelector('.catalog-version').textContent = `신뢰 카탈로그 ${catalog.catalogVersion} · ${catalog.publishedAt.slice(0, 10)}`
    templatePanel.querySelector('[data-template-action="rollback-template"]').disabled = !catalog.rollbackAvailable
    const ranked = [...catalog.entries].sort((left, right) => {
      const leftFavorite = store.studioPrefs.favorites.includes(left.templateID) ? 0 : 1
      const rightFavorite = store.studioPrefs.favorites.includes(right.templateID) ? 0 : 1
      return leftFavorite - rightFavorite
    })
    templatePanel.querySelector('.catalog-entries').replaceChildren(...ranked.map((entry) => {
      const item = document.createElement('li')
      const button = document.createElement('button')
      button.type = 'button'
      button.dataset.templateId = entry.templateID
      button.textContent = `${entry.documentType} · ${entry.templateID} v${entry.version}`
      button.setAttribute('aria-pressed', String(entry.templateID === store.currentProject?.templateBinding.templateID))
      button.addEventListener('click', () => applyCatalogEntry(entry))
      const favorite = document.createElement('button')
      favorite.type = 'button'
      favorite.className = 'favorite-toggle'
      favorite.setAttribute("data-easy-action", "toggle-favorite")
      favorite.dataset.templateId = entry.templateID
      const isFavorite = store.studioPrefs.favorites.includes(entry.templateID)
      favorite.setAttribute('aria-pressed', String(isFavorite))
      favorite.setAttribute('aria-label', `${entry.documentType} 즐겨찾기`)
      favorite.textContent = isFavorite ? '★' : '☆'
      favorite.addEventListener('click', () => toggleFavorite(entry.templateID))
      item.append(button, favorite)
      return item
    }))
    const pinnedID = store.currentProject?.templateBinding.templateID
    const pinnedEntry = catalog.entries.find((entry) => entry.templateID === pinnedID) || catalog.entries[0]
    renderOfficialRules(highestPrecedenceRules(pinnedEntry?.officialRules || []))
    const catalogEntry = catalog.entries.find((entry) => entry.templateID === pinnedID)
    if (!announceStatus) return
    if (catalogEntry && store.currentProject && catalogEntry.version !== store.currentProject.templateBinding.version) {
      announce(`새 템플릿 v${catalogEntry.version}을 확인했습니다. 현재 문서는 v${store.currentProject.templateBinding.version}에 고정되어 있습니다.`)
    } else {
      announce('서명된 신뢰 템플릿 카탈로그를 확인했습니다.')
    }
  }

  const applyCatalogEntry = (entry) => {
    if (!store.currentProject) store.currentProject = initialProject()
    const title = officialTitleFor(entry)
    titleInput.value = title
    const elements = elementsFromTemplate(entry, title)
    const revisionID = `revision-${crypto.randomUUID()}`
    const createdAt = revisionTimestamp()
    store.currentProject = {
      ...store.currentProject,
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
      revisions: [...store.currentProject.revisions, {
        revisionID,
        parentRevisionID: store.currentProject.currentRevisionID,
        createdAt,
        summary: 'template-applied',
        elementIDs: elements.map((element) => element.elementID),
        snapshotElements: elements,
      }],
      history: [...store.currentProject.history, {
        eventID: `history-${crypto.randomUUID()}`,
        kind: 'template-applied',
        revisionID,
        createdAt,
      }],
    }
    store.pendingAIProposal = null
    aiProposalReview.hidden = true
    renderProject(store.currentProject)
    projectBridge('save', store.currentProject)
    announce(`${entry.documentType} 템플릿을 적용했습니다.`)
  }

  document.querySelectorAll('[data-template-action]').forEach((button) => {
    button.addEventListener('click', () => {
      const action = button.dataset.templateAction
      projectBridge(action === 'update-template' ? 'updateTemplateCatalog' : 'rollbackTemplateCatalog')
    })
  })

  Object.assign(studio, {
    officialTitleFor,
    highestPrecedenceRules,
    renderOfficialRules,
    renderOfficialRuleState,
    officialRuleWarning,
    renderTemplateCatalog,
    applyCatalogEntry
  })
}(window.PublicDocumentStudio))
