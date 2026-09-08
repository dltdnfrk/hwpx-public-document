(function (studio) {
  const store = studio.state
  const titleInput = studio.dom.titleInput
  const lockLabel = document.querySelector('.title-lock-label')

  const pinnedEntry = (project) => {
    const templateID = project && project.templateBinding && project.templateBinding.templateID
    const catalog = store.currentTemplateCatalog
    if (!catalog || !templateID) return null
    return (catalog.entries || []).find((entry) => entry.templateID === templateID) || null
  }

  const hasOfficialTitleRule = (project) => {
    const templateID = project && project.templateBinding && project.templateBinding.templateID
    if (templateID === 'public-draft') return false
    const entry = pinnedEntry(project)
    if (entry) return (entry.officialRules || []).some((rule) => rule.field === 'title')
    return templateID === 'public-plan'
  }

  const applyTitleLock = (project) => {
    if (!titleInput) return false
    const locked = hasOfficialTitleRule(project)
    titleInput.readOnly = locked
    titleInput.setAttribute('aria-readonly', String(locked))
    if (lockLabel) lockLabel.hidden = !locked
    return locked
  }

  const previousRenderProject = studio.renderProject
  studio.renderProject = (...args) => {
    const result = previousRenderProject(...args)
    const [project] = args
    applyTitleLock(project || store.currentProject)
    return result
  }

  const previousRenderCatalog = studio.renderTemplateCatalog
  if (typeof previousRenderCatalog === 'function') {
    studio.renderTemplateCatalog = (catalog, announceStatus) => {
      const result = previousRenderCatalog(catalog, announceStatus)
      applyTitleLock(store.currentProject)
      return result
    }
  }

  if (store.currentProject) applyTitleLock(store.currentProject)

  Object.assign(studio, {
    hasOfficialTitleRule,
    applyTitleLock,
  })
}(window.PublicDocumentStudio))
