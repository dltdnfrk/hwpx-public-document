const PublicDocumentPageEngine = (() => {
  const PRINT_TOKENS = {
    schemaVersion: 1,
    tokenID: "print-tokens-1.0.0",
    note: "미리보기·PDF 사이드카 전용. HWPX 페이지네이션을 대체하지 않는다.",
    page: {
      paper: "a4",
      marginMm: { top: 20, right: 20, bottom: 10, left: 20 },
    },
    fonts: { title: "Apple SD Gothic Neo", body: "Apple Myungjo" },
    sizesPt: { title: 16, heading: 16, body: 15 },
  }
  const PAPER_MM = { a4: { widthMm: 210, heightMm: 297 } }

  const mmToPx = (mm) => (Number(mm) * 96) / 25.4
  const ptToPx = (pt) => (Number(pt) * 96) / 72
  const clone = (value) => JSON.parse(JSON.stringify(value))

  const pageMetrics = (tokens = PRINT_TOKENS) => {
    const paper = PAPER_MM[tokens.page.paper] || PAPER_MM.a4
    const margin = tokens.page.marginMm
    return {
      paper: tokens.page.paper,
      tokenID: tokens.tokenID,
      marginMm: { ...margin },
      widthPx: mmToPx(paper.widthMm),
      heightPx: mmToPx(paper.heightMm),
      contentWidthPx: mmToPx(paper.widthMm - margin.left - margin.right),
      contentHeightPx: mmToPx(paper.heightMm - margin.top - margin.bottom),
      marginPx: {
        top: mmToPx(margin.top),
        right: mmToPx(margin.right),
        bottom: mmToPx(margin.bottom),
        left: mmToPx(margin.left),
      },
    }
  }

  const tableRows = (block) => {
    if (Number(block.rows) > 0) return Number(block.rows)
    const matches = String(block.contentHTML || "").match(/<tr\b/gi)
    return matches ? matches.length : 1
  }

  const charsPerLine = (metrics, pt) => Math.max(8, Math.floor(metrics.contentWidthPx / (ptToPx(pt) * 0.92)))

  const lineBox = (pt) => ptToPx(pt) * 1.78

  const estimateBlockHeight = (block, tokens = PRINT_TOKENS, metrics = pageMetrics(tokens)) => {
    if (Number(block.height) > 0) return Number(block.height)
    const sizes = tokens.sizesPt
    const kind = block.kind || ""
    const style = block.styleID || ""
    const text = String(block.text || "")
    if (kind === "table" || style === "style-table") return 28 + tableRows(block) * 32 + 16
    if (kind === "approval-grid" || style === "style-approval") return 88
    if (kind === "review-marker" || style === "style-review") return 56
    if (kind === "metadata" || style === "style-metadata") return 64
    if (style === "style-title") return lineBox(sizes.title) + 42
    if (kind === "heading" || style === "style-section-heading") {
      const lines = Math.max(1, Math.ceil(text.length / charsPerLine(metrics, sizes.heading)))
      return 36 + lines * lineBox(sizes.heading) + 10
    }
    const lines = Math.max(1, Math.ceil((text.length || 1) / charsPerLine(metrics, sizes.body)))
    return lines * lineBox(sizes.body) + 16
  }

  const keepWithNext = (block) => {
    const style = block.styleID || ""
    return block.kind === "heading" || style === "style-section-heading" || style === "style-title"
  }

  const measuredBlock = (block, tokens, metrics) => ({
    id: block.id,
    kind: block.kind,
    styleID: block.styleID,
    text: block.text || "",
    rows: (block.kind === "table" || block.styleID === "style-table") ? tableRows(block) : 0,
    height: estimateBlockHeight(block, tokens, metrics),
  })

  const paginateBlocks = (blocks, tokens = PRINT_TOKENS) => {
    const metrics = pageMetrics(tokens)
    const pages = []
    let current = []
    let used = 0
    const limit = metrics.contentHeightPx

    const flush = () => {
      pages.push({ used, blocks: current })
      current = []
      used = 0
    }

    const place = (item) => {
      if (item.height > limit) {
        let remaining = item.height
        if (used > 0) flush()
        while (remaining > limit) {
          current.push({ ...item, height: limit, overflow: true })
          used = limit
          remaining -= limit
          flush()
        }
        if (remaining > 0) {
          current.push({ ...item, height: remaining, overflow: true })
          used = remaining
        }
        return
      }
      if (used > 0 && used + item.height > limit) flush()
      current.push(item)
      used += item.height
    }

    const items = Array.isArray(blocks) ? blocks : []
    for (let index = 0; index < items.length; index += 1) {
      const first = measuredBlock(items[index], tokens, metrics)
      const group = [first]
      if (keepWithNext(items[index]) && index + 1 < items.length) {
        index += 1
        group.push(measuredBlock(items[index], tokens, metrics))
      }
      const groupHeight = group.reduce((sum, item) => sum + item.height, 0)
      if (group.length > 1 && groupHeight <= limit && used > 0 && used + groupHeight > limit) flush()
      group.forEach(place)
    }
    if (current.length || pages.length === 0) flush()
    return {
      tokenID: tokens.tokenID,
      pageCount: pages.length,
      pages,
      metrics,
    }
  }

  const tokensForProject = (project, tokens = PRINT_TOKENS) => {
    const next = clone(tokens)
    if (project && project.pageMargins) next.page.marginMm = { ...project.pageMargins }
    return next
  }

  const blocksFromProject = (project) => (project && project.elements ? project.elements : [])
    .slice()
    .sort((left, right) => Number(left.order || 0) - Number(right.order || 0))
    .map((element) => ({
      id: element.elementID,
      kind: element.kind,
      styleID: element.styleID,
      text: element.text || "",
      contentHTML: element.contentHTML || "",
      rows: element.rows,
    }))

  const paginateProject = (project, tokens = PRINT_TOKENS) => (
    paginateBlocks(blocksFromProject(project), tokensForProject(project, tokens))
  )

  const pageCountForProject = (project, tokens = PRINT_TOKENS) => (
    Math.max(1, paginateProject(project, tokens).pageCount)
  )

  const statusCopy = (pageCount) => `미리보기 ${Math.max(1, Number(pageCount) || 1)}장`
  const previewCopy = (pageCount) => (
    `A4 ${statusCopy(pageCount)}. 인쇄 토큰 기준이며 한컴 쪽 나누기를 대체하지 않습니다.`
  )

  const escapeHTML = (value) => String(value || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")

  const previewSheets = (layout) => (layout && layout.pages ? layout.pages : []).map((page, index) => ({
    page: index + 1,
    blockIDs: page.blocks.map((block) => block.id),
    texts: page.blocks.map((block) => block.text || ""),
  }))

  const blockTag = (block) => {
    if (block.styleID === "style-title") return "h1"
    if (block.kind === "heading" || block.styleID === "style-section-heading") return "h2"
    if (block.kind === "table" || block.styleID === "style-table") return "table"
    return "p"
  }

  const previewMarkup = (layout) => previewSheets(layout).map((sheet, index) => {
    const body = ((layout.pages[index] && layout.pages[index].blocks) || []).map((block) => {
      const tag = blockTag(block)
      const id = escapeHTML(block.id)
      const text = escapeHTML(block.text)
      if (tag === "table") return `<table data-preview-block="${id}"><caption>${text}</caption></table>`
      return `<${tag} data-preview-block="${id}">${text}</${tag}>`
    }).join("")
    return `<article class="page-preview-sheet" data-preview-page="${sheet.page}">${body}</article>`
  }).join("")

  const renderPreview = (host, layout) => {
    if (!host) return layout
    host.innerHTML = previewMarkup(layout)
    return layout
  }

  const paintOverlay = (overlay, layout) => {
    if (!overlay || !layout) return layout
    overlay.hidden = false
    overlay.replaceChildren()
    layout.pages.slice(0, -1).forEach((_, index) => {
      const mark = document.createElement("div")
      mark.className = "page-engine-break"
      mark.style.top = `${(index + 1) * layout.metrics.heightPx}px`
      const folio = document.createElement("span")
      folio.textContent = `미리보기 ${index + 1} / ${layout.pageCount}`
      mark.appendChild(folio)
      overlay.appendChild(mark)
    })
    return layout
  }

  const syncStudio = (studio) => {
    const project = studio && studio.state && studio.state.currentProject
    if (!project) return null
    const layout = paginateProject(project)
    PublicDocumentPageEngine.lastLayout = layout
    if (typeof document === "undefined") return layout
    paintOverlay(document.querySelector("[data-page-engine-overlay]"), layout)
    const editor = studio.dom && studio.dom.editor
    if (editor) editor.style.minHeight = `${layout.pageCount * layout.metrics.heightPx}px`
    const preview = document.querySelector("[data-page-preview]")
    if (preview && !preview.hidden) renderPreview(preview, layout)
    return layout
  }

  return {
    PRINT_TOKENS,
    mmToPx,
    pageMetrics,
    estimateBlockHeight,
    paginateBlocks,
    blocksFromProject,
    paginateProject,
    pageCountForProject,
    statusCopy,
    previewCopy,
    previewSheets,
    previewMarkup,
    renderPreview,
    paintOverlay,
    syncStudio,
    lastLayout: null,
  }
})()

globalThis.PublicDocumentPageEngine = PublicDocumentPageEngine
if (typeof module === "object" && module.exports) module.exports = PublicDocumentPageEngine
