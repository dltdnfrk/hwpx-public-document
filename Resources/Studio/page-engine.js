const PublicDocumentPageEngine = (() => {
  const PROFILE = globalThis.PublicDocumentOfficialLayoutProfile
  if (!PROFILE || PROFILE.schemaVersion !== 1 || !PROFILE.sources || !PROFILE.page) {
    throw new Error("official layout profile is missing or invalid")
  }
  const PRINT_TOKENS = {
    schemaVersion: PROFILE.schemaVersion,
    tokenID: PROFILE.sources.printTokens.id,
    page: PROFILE.page,
    fonts: PROFILE.fonts,
    sizesPt: PROFILE.sizesPt,
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

  const ATTACHMENT_TAILS = /(?:붙임|별첨|관련|첨부)\s*$/
  const NUMBERED_ITEM = /^\d+\.\s/

  const OFFICIAL_LINE_CACHE = new Map()
  const OFFICIAL_LINE_CACHE_LIMIT = 1024

  const computeOfficialLines = (text) => {
    const source = String(text || "").replace(/\r\n/g, "\n").trim()
    if (!source) return []
    const parts = source
      .split(/(?=\s*(?:○|□|※)\s)|(?=\s+-\s)|(?=\s+\d+단계:)|(?<=(?:함|음|다)\.\s)(?=\d+\.\s)|(?<=\s)(?=[1-9]\d?\.\s[가-힣○□])|(?<=\s)(?=[가나다라마바사아자차카타파하]\.\s[가-힣○□0-9])/)
      .map((line) => line.replace(/\s+/g, " ").trim())
      .filter(Boolean)
    const merged = []
    for (const part of parts) {
      const last = merged[merged.length - 1]
      if (last && ATTACHMENT_TAILS.test(last) && NUMBERED_ITEM.test(part)) {
        merged[merged.length - 1] = `${last} ${part}`
      } else {
        merged.push(part)
      }
    }
    return merged.length ? merged : [source.replace(/\s+/g, " ").trim()]
  }

  const splitOfficialLines = (text) => {
    const key = String(text || "")
    const cached = OFFICIAL_LINE_CACHE.get(key)
    if (cached) return cached.slice()
    const lines = computeOfficialLines(key)
    if (OFFICIAL_LINE_CACHE.size >= OFFICIAL_LINE_CACHE_LIMIT) OFFICIAL_LINE_CACHE.clear()
    OFFICIAL_LINE_CACHE.set(key, lines)
    return lines.slice()
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
    const width = charsPerLine(metrics, sizes.body)
    const lines = splitOfficialLines(text).reduce(
      (sum, line) => sum + Math.max(1, Math.ceil((line.length || 1) / width)),
      0,
    )
    return Math.max(1, lines) * lineBox(sizes.body) + 16
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
    contentHTML: block.contentHTML || "",
    rows: (block.kind === "table" || block.styleID === "style-table") ? tableRows(block) : 0,
    height: estimateBlockHeight(block, tokens, metrics),
  })

  const splitOversizedTable = (item, limit, firstLimit = limit) => {
    if (!(item.kind === "table" || item.styleID === "style-table") || !item.contentHTML) return []
    const rows = [...item.contentHTML.matchAll(/<tr[\s\S]*?<\/tr>/gi)].map((match) => match[0])
    if (rows.length < 2) return []
    const opening = item.contentHTML.match(/<table[^>]*>/i)?.[0] || "<table>"
    const chunks = []
    const header = /<th\b/i.test(rows[0]) ? rows[0] : null
    const dataRows = header ? rows.slice(1) : rows
    let index = 0
    while (index < dataRows.length) {
      const pageLimit = chunks.length === 0 ? firstLimit : limit
      const rowsPerPage = Math.max(1, Math.floor((pageLimit - 44) / 32))
      const dataRowsPerPage = Math.max(1, rowsPerPage - (header ? 1 : 0))
      const pageRows = [
        ...(header ? [header] : []),
        ...dataRows.slice(index, index + dataRowsPerPage),
      ]
      const chunkIndex = chunks.length
      chunks.push({
        ...item,
        id: chunkIndex === 0 ? item.id : `${item.id}-continuation-${chunkIndex}`,
        sourceID: item.id,
        contentHTML: `${opening}<tbody>${pageRows.join("")}</tbody></table>`,
        rows: pageRows.length,
        height: 44 + pageRows.length * 32,
        overflow: true,
      })
      index += dataRowsPerPage
    }
    return chunks
  }

  const splitOversizedText = (item, tokens, metrics, limit, firstLimit = limit) => {
    if (!item.text || item.kind === "table" || item.styleID === "style-table") return []
    const measuredHeight = (text) => estimateBlockHeight({
      kind: item.kind,
      styleID: item.styleID,
      text,
    }, tokens, metrics)
    if (measuredHeight(item.text) <= limit) return []
    const characters = Array.from(item.text)
    const chunks = []
    let offset = 0
    while (offset < characters.length) {
      const pageLimit = chunks.length === 0 ? firstLimit : limit
      let low = 1
      let high = characters.length - offset
      let count = 0
      while (low <= high) {
        const middle = Math.floor((low + high) / 2)
        const text = characters.slice(offset, offset + middle).join("")
        if (measuredHeight(text) <= pageLimit) {
          count = middle
          low = middle + 1
        } else {
          high = middle - 1
        }
      }
      count = Math.max(1, count)
      const text = characters.slice(offset, offset + count).join("")
      const chunkIndex = chunks.length
      chunks.push({
        ...item,
        id: chunkIndex === 0 ? item.id : `${item.id}-continuation-${chunkIndex}`,
        sourceID: item.id,
        text,
        contentHTML: "",
        height: measuredHeight(text),
        overflow: true,
      })
      offset += count
    }
    return chunks
  }

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
        let tableChunks = splitOversizedTable(item, limit, limit - used)
        if (tableChunks.length) {
          if (used > 0 && used + tableChunks[0].height > limit) {
            flush()
            tableChunks = splitOversizedTable(item, limit)
          }
          tableChunks.forEach((chunk, index) => {
            current.push(chunk)
            used += chunk.height
            if (index < tableChunks.length - 1) flush()
          })
          return
        }
        let textChunks = splitOversizedText(item, tokens, metrics, limit, limit - used)
        if (textChunks.length) {
          if (used > 0 && used + textChunks[0].height > limit) {
            flush()
            textChunks = splitOversizedText(item, tokens, metrics, limit)
          }
          textChunks.forEach((chunk, index) => {
            current.push(chunk)
            used += chunk.height
            if (index < textChunks.length - 1) flush()
          })
          return
        }
        let remaining = item.height
        if (used > 0) flush()
        let fragment = 0
        while (remaining > limit) {
          current.push({
            ...item,
            id: fragment === 0 ? item.id : `${item.id}-continuation-${fragment}`,
            sourceID: item.id,
            text: fragment === 0 ? item.text : "",
            contentHTML: fragment === 0 ? item.contentHTML : "",
            height: limit,
            overflow: true,
          })
          fragment += 1
          used = limit
          remaining -= limit
          flush()
        }
        if (remaining > 0) {
          current.push({
            ...item,
            id: fragment === 0 ? item.id : `${item.id}-continuation-${fragment}`,
            sourceID: item.id,
            text: fragment === 0 ? item.text : "",
            contentHTML: fragment === 0 ? item.contentHTML : "",
            height: remaining,
            overflow: true,
          })
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
      if (group.length > 1 && group[1].height > limit && used > 0) flush()
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
  const decodeEntity = (source, entity) => {
    const named = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: "\u00a0" }
    if (Object.prototype.hasOwnProperty.call(named, entity)) return named[entity]
    const match = entity.match(/^#(?:x([0-9a-f]+)|(\d+))$/i)
    if (!match) return source
    const value = Number.parseInt(match[1] || match[2], match[1] ? 16 : 10)
    if (!Number.isInteger(value) || value < 0 || value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff)) return source
    return String.fromCodePoint(value)
  }
  const tableCellText = (value) => String(value || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(?:div|p|li)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&([^;\s]+);/g, decodeEntity)
    .replace(/\r\n?|\n{3,}/g, "\n")
    .trim()
  const tableCellMarkup = (value) => escapeHTML(value).replace(/\n/g, "<br>")

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

  const officialMarkup = (text) => splitOfficialLines(text).map((line) => {
    const kind = line.startsWith("- ")
      ? "detail"
      : /^[가나다라마바사아자차카타파하]\.\s/.test(line) ? "level1"
      : /^(○|□|※|\d+\.\s|\d+단계:|제언\s+\d+\.)/.test(line) ? "hang" : ""
    const cls = kind ? ` class="official-line ${kind}"` : ""
    return `<span${cls}>${escapeHTML(line)}</span>`
  }).join("")

  const tablePreview = (block) => {
    const id = escapeHTML(block.id)
    const html = String(block.contentHTML || "")
    const rows = []
    const rowRe = /<tr[\s\S]*?<\/tr>/gi
    let row
    while ((row = rowRe.exec(html))) {
      const cells = [...row[0].matchAll(/<(td|th)[^>]*>([\s\S]*?)<\/\1>/gi)]
        .map((match) => ({ tag: match[1].toLowerCase(), text: tableCellText(match[2]) }))
      if (cells.length) rows.push(cells)
    }
    if (!rows.length) return `<table data-preview-block="${id}"><caption>${escapeHTML(block.text)}</caption></table>`
    const body = rows.map((cells) => {
      return `<tr>${cells.map((cell) => `<${cell.tag}>${tableCellMarkup(cell.text)}</${cell.tag}>`).join("")}</tr>`
    }).join("")
    return `<table data-preview-block="${id}"><tbody>${body}</tbody></table>`
  }

  const previewMarkup = (layout) => previewSheets(layout).map((sheet, index) => {
    const body = ((layout.pages[index] && layout.pages[index].blocks) || []).map((block) => {
      const tag = blockTag(block)
      const id = escapeHTML(block.id)
      if (tag === "table") return tablePreview(block)
      return `<${tag} data-preview-block="${id}">${officialMarkup(block.text)}</${tag}>`
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
    splitOfficialLines,
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
