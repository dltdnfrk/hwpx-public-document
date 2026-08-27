(function (studio) {
  const store = studio.state
  const persistPrefs = (...args) => studio.persistPrefs(...args)
  const applyStudioPrefs = (...args) => studio.applyStudioPrefs(...args)
  const announce = (...args) => studio.announce(...args)

  const setChecklistConsent = (consented) => {
    const section = document.querySelector('.checklist')
    if (!section) return
    section.dataset.checklistConsent = String(consented)
    const note = section.querySelector('.checklist-note')
    if (note) note.textContent = '기관 템플릿 점검입니다. 행정안전부 표준이 아닙니다.'
    const progress = section.querySelector('[role="progressbar"]')
    const list = section.querySelector('ul')
    if (progress) progress.hidden = !consented
    if (list) list.hidden = !consented
    const checkbox = section.querySelector('[data-checklist-consent]')
    if (checkbox) checkbox.checked = consented
  }

  const bindChecklistConsent = () => {
    const checkbox = document.querySelector('[data-checklist-consent]')
    if (!checkbox || checkbox.dataset.bound === 'true') return
    checkbox.dataset.bound = 'true'
    checkbox.addEventListener('change', () => {
      const next = { ...store.studioPrefs, checklistConsent: checkbox.checked }
      persistPrefs(next)
      applyStudioPrefs(next)
      setChecklistConsent(checkbox.checked)
      announce(checkbox.checked ? '작성 점검을 표시합니다.' : '작성 점검을 숨겼습니다.')
    })
    setChecklistConsent(Boolean(store.studioPrefs.checklistConsent))
  }

  Object.assign(studio, { setChecklistConsent, bindChecklistConsent })
}(window.PublicDocumentStudio))
