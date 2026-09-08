(function (studio) {
  const { editor, workspace, outlineToggle } = studio.dom
  const announce = (...args) => studio.announce(...args)
  const pageEngine = () => globalThis.PublicDocumentPageEngine
  const MIN_ZOOM = 70
  const MAX_ZOOM = 130
  const zoomInput = document.querySelector('.zoom-control input')
  const zoomOutput = document.querySelector('.zoom-control output')
  const pageStatus = document.querySelector('[data-page-status]')
  const viewNote = document.querySelector('[data-view-page-note]')
  const pagePreview = document.querySelector('[data-page-preview]')
  const previewToggle = document.querySelector('[data-view-action="toggle-page-preview"]')
  const canvasNode = document.querySelector('.canvas')

  const pageWidth = () => {
    const engine = pageEngine()
    return engine && engine.pageMetrics ? engine.pageMetrics().widthPx : 794
  }

  const pageHeight = () => {
    const engine = pageEngine()
    return engine && engine.pageMetrics ? engine.pageMetrics().heightPx : 1123
  }

  const clampZoom = (value) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(Number(value) || 100)))

  const currentZoom = () => clampZoom(zoomInput ? zoomInput.value : 100)

  const setZoom = (percent) => {
    const zoom = clampZoom(percent)
    if (editor) editor.style.zoom = String(zoom / 100)
    if (zoomInput) zoomInput.value = String(zoom)
    if (zoomOutput) zoomOutput.value = `${zoom}%`
    document.querySelectorAll('[data-view-zoom]').forEach((button) => {
      button.setAttribute('aria-pressed', String(Number(button.dataset.viewZoom) === zoom))
    })
    return zoom
  }

  const fitWidthZoom = () => {
    const canvas = document.querySelector('.canvas')
    const available = (canvas && canvas.clientWidth) || (workspace && workspace.clientWidth) || pageWidth()
    return clampZoom((available / pageWidth()) * 100)
  }

  const fitPageZoom = () => {
    const canvas = document.querySelector('.canvas')
    const availableW = (canvas && canvas.clientWidth) || pageWidth()
    const availableH = (canvas && canvas.clientHeight) || pageHeight()
    return clampZoom(Math.min(availableW / pageWidth(), availableH / pageHeight()) * 100)
  }

  const previewSheetCount = () => {
    const engine = pageEngine()
    const project = studio.state && studio.state.currentProject
    if (engine && project && typeof engine.pageCountForProject === 'function') {
      return engine.pageCountForProject(project)
    }
    if (engine && engine.lastLayout && engine.lastLayout.pageCount) return engine.lastLayout.pageCount
    const surface = editor || document.querySelector('#static-editor-fallback')
    const height = surface && (surface.scrollHeight || (surface.getBoundingClientRect && surface.getBoundingClientRect().height))
    if (!height) return 1
    return Math.max(1, Math.ceil(height / pageHeight()))
  }

  const setPagePreview = (on) => {
    const engine = pageEngine()
    const show = Boolean(on)
    if (canvasNode) canvasNode.classList.toggle('page-preview-open', show)
    if (pagePreview) {
      pagePreview.hidden = !show
      pagePreview.setAttribute('aria-hidden', String(!show))
      if (show && engine && studio.state && studio.state.currentProject && typeof engine.renderPreview === 'function') {
        engine.renderPreview(pagePreview, engine.paginateProject(studio.state.currentProject))
      }
    }
    if (previewToggle) previewToggle.setAttribute('aria-pressed', String(show))
    return show
  }

  const togglePagePreview = () => setPagePreview(!(pagePreview && !pagePreview.hidden))

  const updatePreviewSheets = () => {
    const engine = pageEngine()
    if (engine && typeof engine.syncStudio === 'function' && studio.state && studio.state.currentProject) {
      engine.syncStudio(studio)
    }
    const count = previewSheetCount()
    const text = engine && typeof engine.statusCopy === 'function' ? engine.statusCopy(count) : `미리보기 ${count}장`
    if (pageStatus) pageStatus.textContent = text
    if (viewNote) {
      viewNote.textContent = engine && typeof engine.previewCopy === 'function'
        ? engine.previewCopy(count)
        : `${text}. 인쇄 토큰 기준이며 한컴 쪽 나누기를 대체하지 않습니다.`
    }
    return count
  }

  const syncOutlineButtons = () => {
    const pressed = outlineToggle ? outlineToggle.getAttribute('aria-pressed') === 'true' : !(workspace && workspace.classList.contains('outline-hidden'))
    const viewOutline = document.querySelector('[data-view-action="toggle-outline"]')
    if (viewOutline) viewOutline.setAttribute('aria-pressed', String(pressed))
    return pressed
  }

  document.querySelectorAll('[data-view-action]').forEach((button) => {
    button.addEventListener('click', () => {
      const action = button.dataset.viewAction
      if (action === 'zoom-out') setZoom(currentZoom() - 10)
      else if (action === 'zoom-in') setZoom(currentZoom() + 10)
      else if (action === 'zoom-100') setZoom(100)
      else if (action === 'zoom-fit-width') setZoom(fitWidthZoom())
      else if (action === 'zoom-fit-page') setZoom(fitPageZoom())
      else if (action === 'toggle-outline' && typeof studio.toggleOutline === 'function') studio.toggleOutline()
      else if (action === 'toggle-page-preview') togglePagePreview()
      syncOutlineButtons()
      updatePreviewSheets()
    })
  })

  if (zoomInput) {
    zoomInput.addEventListener('input', () => {
      setZoom(zoomInput.value)
      updatePreviewSheets()
    })
  }

  if (outlineToggle) {
    outlineToggle.addEventListener('click', () => window.requestAnimationFrame(syncOutlineButtons))
  }

  const previousRender = studio.renderProject
  if (typeof previousRender === 'function') {
    studio.renderProject = (...args) => {
      const result = previousRender(...args)
      window.requestAnimationFrame(updatePreviewSheets)
      return result
    }
  }

  if (editor) {
    editor.addEventListener('public-document-genoffice-change', () => {
      window.requestAnimationFrame(updatePreviewSheets)
    })
  }

  setZoom(100)
  updatePreviewSheets()
  syncOutlineButtons()

  Object.assign(studio, {
    setZoom,
    fitWidthZoom,
    fitPageZoom,
    previewSheetCount,
    updatePreviewSheets,
    togglePagePreview,
    setPagePreview,
  })
}(window.PublicDocumentStudio))
