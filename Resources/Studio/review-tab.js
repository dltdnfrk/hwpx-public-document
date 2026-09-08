(function (studio) {
  const store = studio.state

  const citationValues = (project) => ([
    project && project.title,
    ...((project && project.elements) || []).map((element) => element.text),
    ...((project && project.elements) || []).map((element) => element.contentHTML),
  ])

  const failClosedReviews = (values) => {
    if (typeof studio.reviewStatuteCitations !== 'function') return []
    const allowed = Array.isArray(studio.verifiedStatuteCitations) ? studio.verifiedStatuteCitations : []
    return studio.reviewStatuteCitations(values).map((item) => {
      const verified = Boolean(item && item.verified === true && allowed.indexOf(item.citation) !== -1)
      return {
        citation: item.citation,
        verified,
        label: verified ? '확인됨' : '법령 인용 미확인',
      }
    })
  }

  const renderDocumentStatuteWarnings = (project) => {
    const box = document.querySelector('#review-tools [data-statute-warnings]')
    if (!box) return []
    const reviews = failClosedReviews(citationValues(project))
    box.replaceChildren(...reviews.map((item) => {
      const row = document.createElement('li')
      row.dataset.statuteVerified = String(item.verified)
      row.textContent = `${item.label} · ${item.citation}`
      return row
    }))
    box.hidden = reviews.length === 0
    return reviews
  }

  const revealLocalAppOnly = (root) => {
    if (!root) return
    const note = root.querySelector('.local-app-only')
    if (note) note.hidden = false
  }

  const markLocalAppOnlyControls = () => {
    if (!studio.isLocalWeb()) return
    const update = document.querySelector('[data-template-action="update-template"]')
    if (update) {
      update.disabled = true
      update.setAttribute('aria-disabled', 'true')
      revealLocalAppOnly(update)
    }
    const batch = document.querySelector('[data-batch-export]')
    if (batch) {
      batch.checked = false
      batch.disabled = true
      batch.setAttribute('aria-disabled', 'true')
      revealLocalAppOnly(batch.closest('label'))
    }
  }

  const previousRenderProject = studio.renderProject
  studio.renderProject = (...args) => {
    const result = previousRenderProject(...args)
    const [project] = args
    renderDocumentStatuteWarnings(project || store.currentProject)
    return result
  }

  markLocalAppOnlyControls()
  if (store.currentProject) renderDocumentStatuteWarnings(store.currentProject)

  Object.assign(studio, {
    renderDocumentStatuteWarnings,
    markLocalAppOnlyControls,
  })
}(window.PublicDocumentStudio))
