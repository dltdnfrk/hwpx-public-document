(function (studio) {
  const store = studio.state
  const isLocalWeb = (...args) => studio.isLocalWeb(...args)
  const projectBridge = (...args) => studio.projectBridge(...args)
  const renderTemplateCatalog = (...args) => studio.renderTemplateCatalog(...args)
  const newRevision = (...args) => studio.newRevision(...args)
  const announce = (...args) => studio.announce(...args)

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
      checklistConsent: prefs?.checklistConsent === true,
    }
  }

  const renderMyForms = () => {
    const select = document.querySelector('[data-easy="my-form"]')
    if (!select) return
    const current = select.value
    select.replaceChildren(...(store.studioPrefs.myForms.length ? store.studioPrefs.myForms : [{ id: '', name: '저장된 양식 없음', text: '' }]).map((form) => {
      const option = document.createElement('option')
      option.value = form.id
      option.textContent = form.name
      return option
    }))
    if (store.studioPrefs.myForms.some((form) => form.id === current)) select.value = current
  }

  const applyStudioPrefs = (prefs, persist = false) => {
    store.studioPrefs = normalizeClientPrefs(prefs)
    const select = document.querySelector('[data-easy="autosave-interval"]')
    if (select) select.value = String(store.studioPrefs.autosaveIntervalMs)
    renderMyForms()
    if (typeof studio.bindChecklistConsent === 'function') studio.bindChecklistConsent()
    if (typeof studio.setChecklistConsent === 'function') studio.setChecklistConsent(Boolean(store.studioPrefs.checklistConsent))
    if (store.currentTemplateCatalog) renderTemplateCatalog(store.currentTemplateCatalog, false)
    window.clearInterval(store.periodicSaveTimer)
    store.periodicSaveTimer = window.setInterval(() => {
      if (!store.currentProject) return
      const snapshot = newRevision(store.currentProject, 'autosaved')
      if (snapshot === store.currentProject) return
      store.currentProject = snapshot
      projectBridge('autosave', store.currentProject)
    }, store.studioPrefs.autosaveIntervalMs)
    if (persist) persistPrefs(store.studioPrefs)
  }

  const persistPrefs = (prefs) => {
    store.studioPrefs = normalizeClientPrefs(prefs)
    if (isLocalWeb()) projectBridge('saveStudioPrefs', null, { prefs: store.studioPrefs })
  }

  const toggleFavorite = (templateID) => {
    const favorites = store.studioPrefs.favorites.includes(templateID)
      ? store.studioPrefs.favorites.filter((item) => item !== templateID)
      : [...store.studioPrefs.favorites, templateID]
    persistPrefs({ ...store.studioPrefs, favorites })
    applyStudioPrefs({ ...store.studioPrefs, favorites })
    announce(favorites.includes(templateID) ? '즐겨찾기에 넣었습니다.' : '즐겨찾기를 해제했습니다.')
  }

  document.querySelector('[data-easy="autosave-interval"]').addEventListener('change', (event) => {
    persistPrefs({ ...store.studioPrefs, autosaveIntervalMs: Number(event.target.value) })
    applyStudioPrefs({ ...store.studioPrefs, autosaveIntervalMs: Number(event.target.value) })
    announce('자동저장 간격을 바꿨습니다.')
  })

  Object.assign(studio, {
    normalizeClientPrefs,
    renderMyForms,
    applyStudioPrefs,
    persistPrefs,
    toggleFavorite
  })
}(window.PublicDocumentStudio))
