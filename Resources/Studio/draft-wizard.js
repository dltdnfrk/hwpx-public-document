(function (studio) {
  const store = studio.state
  const dialog = document.querySelector('.draft-wizard')
  const fieldsRoot = document.querySelector('[data-wizard-fields]')
  const note = document.querySelector('[data-wizard-note]')

  const currentEntry = () => {
    const templateID = store.currentProject && store.currentProject.templateBinding && store.currentProject.templateBinding.templateID
    const catalog = store.currentTemplateCatalog
    if (!catalog || !templateID) return null
    return (catalog.entries || []).find((entry) => entry.templateID === templateID) || null
  }

  const sectionFields = (project) => ((project && project.templateBinding && project.templateBinding.requiredSections) || [])

  const fillFields = (project) => {
    if (!fieldsRoot) return
    const lockedTitle = typeof studio.hasOfficialTitleRule === 'function' && studio.hasOfficialTitleRule(project)
    const fragment = document.createDocumentFragment()
    if (!lockedTitle) {
      const label = document.createElement('label')
      label.append('제목')
      const input = document.createElement('input')
      input.dataset.wizardField = 'title'
      input.value = (project && project.title) || ''
      label.append(input)
      fragment.append(label)
    }
    sectionFields(project).forEach((section) => {
      const label = document.createElement('label')
      label.append(section)
      const input = document.createElement('textarea')
      input.dataset.wizardField = section
      input.rows = 2
      label.append(input)
      fragment.append(label)
    })
    fieldsRoot.replaceChildren(fragment)
    if (note) note.textContent = '템플릿 절을 채웁니다. 완성 공문을 자동 생성하지 않습니다.'
    return currentEntry()
  }

  const openDraftWizard = (project = store.currentProject) => {
    if (!dialog) return false
    fillFields(project)
    studio.openDialog(dialog)
    studio.announce('필수 절을 채울 작성 창을 열었습니다.')
    return true
  }

  const closeDraftWizard = () => {
    if (dialog) studio.closeDialog(dialog)
  }

  const readDraftWizardFields = () => {
    const values = {}
    if (!fieldsRoot) return values
    fieldsRoot.querySelectorAll('[data-wizard-field]').forEach((input) => {
      values[input.dataset.wizardField] = String(input.value || '').trim()
    })
    return values
  }

  const applyDraftWizard = () => {
    const project = store.currentProject
    if (!project || typeof studio.commitProjectElements !== 'function') return false
    const values = readDraftWizardFields()
    const live = typeof studio.projectElements === 'function' ? studio.projectElements({ silent: true }) : null
    const elements = (live || project.elements || []).map((element) => ({ ...element }))
    const draft = project.templateBinding && project.templateBinding.templateID === 'public-draft'
    if (values.title && !(typeof studio.hasOfficialTitleRule === 'function' && studio.hasOfficialTitleRule(project))) {
      const titleEl = elements.find((element) => element.elementID === 'element-title')
      if (titleEl) {
        titleEl.text = values.title
        titleEl.contentHTML = values.title
      }
      if (studio.dom.titleInput) studio.dom.titleInput.value = values.title
    }
    sectionFields(project).forEach((section, index) => {
      const value = values[section]
      if (!value) return
      const body = elements.find((element) => element.elementID === `element-section-${index + 1}-body`)
      if (!body) return
      const text = draft ? `가. ${value}` : `○ ${value}`
      body.text = text
      body.contentHTML = text
    })
    const checklist = { ...((project.templateBinding && project.templateBinding.checklistResults) || {}) }
    Object.keys(checklist).forEach((item) => {
      const related = sectionFields(project).find((section) => item.indexOf(section) !== -1 || section.indexOf(item) !== -1)
      if (related && values[related]) checklist[item] = true
    })
    studio.commitProjectElements(elements, 'draft-wizard', '필수 절을 채웠습니다.', {
      title: (studio.dom.titleInput && studio.dom.titleInput.value.trim()) || project.title,
      templateBinding: {
        ...project.templateBinding,
        checklistResults: checklist,
      },
    })
    closeDraftWizard()
    return true
  }

  const previousApply = studio.applyCatalogEntry
  if (typeof previousApply === 'function') {
    studio.applyCatalogEntry = (entry) => {
      const result = previousApply(entry)
      openDraftWizard(store.currentProject)
      return result
    }
  }

  document.querySelectorAll('[data-action="open-draft-wizard"]').forEach((button) => {
    button.addEventListener('click', () => openDraftWizard())
  })
  document.querySelectorAll('[data-action="close-draft-wizard"]').forEach((button) => {
    button.addEventListener('click', () => closeDraftWizard())
  })
  document.querySelectorAll('[data-action="apply-draft-wizard"]').forEach((button) => {
    button.addEventListener('click', () => applyDraftWizard())
  })
  const newButton = document.querySelector('[data-project-action="new"]')
  if (newButton) {
    newButton.addEventListener('click', () => openDraftWizard(store.currentProject))
  }

  Object.assign(studio, {
    openDraftWizard,
    applyDraftWizard,
    readDraftWizardFields,
  })
}(window.PublicDocumentStudio))
