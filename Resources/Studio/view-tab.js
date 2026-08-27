(function (studio) {
  const { editor, workspace, outlineToggle } = studio.dom
  const announce = (...args) => studio.announce(...args)
  const PAGE_WIDTH = 794
  const PAGE_HEIGHT = 1123
  const MIN_ZOOM = 70
  const MAX_ZOOM = 130
  const zoomInput = document.querySelector('.zoom-control input')
  const zoomOutput = document.querySelector('.zoom-control output')
  const pageStatus = document.querySelector('[data-page-status]')
  const viewNote = document.querySelector('[data-view-page-note]')

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
    const available = (canvas && canvas.clientWidth) || (workspace && workspace.clientWidth) || PAGE_WIDTH
    return clampZoom((available / PAGE_WIDTH) * 100)
  }

  const fitPageZoom = () => {
    const canvas = document.querySelector('.canvas')
    const availableW = (canvas && canvas.clientWidth) || PAGE_WIDTH
    const availableH = (canvas && canvas.clientHeight) || PAGE_HEIGHT
    return clampZoom(Math.min(availableW / PAGE_WIDTH, availableH / PAGE_HEIGHT) * 100)
  }

  const previewSheetCount = () => {
    const surface = editor || document.querySelector('#static-editor-fallback')
    const height = surface && (surface.scrollHeight || (surface.getBoundingClientRect && surface.getBoundingClientRect().height))
    if (!height) return 1
    return Math.max(1, Math.ceil(height / PAGE_HEIGHT))
  }

  const updatePreviewSheets = () => {
    const count = previewSheetCount()
    const text = `미리보기 ${count}장`
    if (pageStatus) pageStatus.textContent = text
    if (viewNote) viewNote.textContent = `${text}. 캔버스 높이 기준이며 쪽 나누기 엔진은 없습니다.`
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
    studio.renderProject = (project, officialRuleState) => {
      const result = previousRender(project, officialRuleState)
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
  })
}(window.PublicDocumentStudio))
