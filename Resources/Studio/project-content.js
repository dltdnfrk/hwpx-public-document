(function (studio) {
  const store = studio.state
  const { page, editor } = studio.dom
  const easyTools = (...args) => studio.easyTools(...args)
  const announce = (...args) => studio.announce(...args)
  const allowedRichTags = studio.allowedRichTags
  const allowedFontFaces = studio.allowedFontFaces

  const revisionTimestamp = () => new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')
  const isTitleElement = (element) => Boolean(element && (element.elementID === 'element-title' || element.styleID === 'style-title'))
  const isEasyTableElement = (element) => Boolean(
    element && (element.kind === 'table' || /data-easy-table/i.test(element.contentHTML || ''))
  )
  const tablePlainText = (html) => {
    const tools = easyTools()
    return tools ? tools.tablePlainText(html) : String(html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
  }
  const preserveTableMarkup = (liveHTML, previous, fallbackText) => {
    const live = liveHTML ?? ''
    const prior = previous?.contentHTML || ''
    const raw = (/data-easy-table/i.test(live) || /<table/i.test(live))
      ? live
      : (/data-easy-table/i.test(prior) || /<table/i.test(prior))
        ? prior
        : (live || prior || fallbackText || '')
    if (!/<tr/i.test(raw) || !/ProseMirror-trailingBreak|<br/i.test(raw)) return raw
    const tools = easyTools()
    return tools ? (tools.cleanPastedTable(raw) || raw) : raw
  }

  const ensureStableInlineIDs = (container) => {
    Array.from(container.childNodes).forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE && child.textContent.trim()) {
        const inline = document.createElement('span')
        inline.dataset.inlineId = `inline-${crypto.randomUUID()}`
        inline.textContent = child.textContent
        child.replaceWith(inline)
        return
      }
      if (child.nodeType === Node.ELEMENT_NODE) {
        if (!child.dataset.inlineId) child.dataset.inlineId = `inline-${crypto.randomUUID()}`
        ensureStableInlineIDs(child)
      }
    })
  }

  const sanitizeRichContent = (element) => {
    ensureStableInlineIDs(element)
    const clone = element.cloneNode(true)
    clone.querySelectorAll('*').forEach((child) => {
      if (!allowedRichTags.has(child.tagName)) {
        child.replaceWith(...child.childNodes)
        return
      }
      Array.from(child.attributes).forEach((attribute) => {
        const safeLayoutAttribute = ['colspan', 'rowspan'].includes(attribute.name) && ['TD', 'TH'].includes(child.tagName)
        const safeClass = attribute.name === 'class' && child.classList.contains('keep-phrase')
        const safeEasyTable = child.tagName === 'TABLE' && attribute.name === 'data-easy-table'
        const safeTableStyle = ['TABLE', 'TD', 'TH', 'TR'].includes(child.tagName)
          && attribute.name === 'style'
          && /^(?:\s*(?:border-collapse\s*:\s*collapse|border\s*:\s*(?:none|1px solid (?:transparent|#[0-9a-fA-F]{3,8}))|background\s*:\s*#[0-9a-fA-F]{3,8})\s*;?\s*)+$/.test(attribute.value)
        const safeFontAttribute = child.tagName === 'FONT' && (
          (attribute.name === 'face' && allowedFontFaces.has(attribute.value))
          || (attribute.name === 'size' && /^(10|11|12|14)$/.test(attribute.value))
        )
        if (attribute.name !== 'data-inline-id' && !safeLayoutAttribute && !safeClass && !safeEasyTable && !safeTableStyle && !safeFontAttribute) child.removeAttribute(attribute.name)
      })
    })
    return {
      html: clone.innerHTML,
      inlineIDs: Array.from(clone.querySelectorAll('[data-inline-id]')).map((inline) => inline.dataset.inlineId),
      nodes: Array.from(clone.childNodes).map((child) => child.cloneNode(true)),
    }
  }

  const rehydrateRichContent = (target, contentHTML) => {
    const containerTag = target.tagName === 'TABLE' ? 'table' : 'div'
    const parsed = new DOMParser().parseFromString(`<${containerTag}>${contentHTML}</${containerTag}>`, 'text/html')
    const safeContent = sanitizeRichContent(parsed.body.querySelector(containerTag))
    target.replaceChildren(...safeContent.nodes)
  }

  const inlineIDsFromContent = (contentHTML) => Array.from(
    new DOMParser().parseFromString(contentHTML, 'text/html').querySelectorAll('[data-inline-id]'),
    (inline) => inline.dataset.inlineId,
  )

  const fallbackProjectElements = () => Array.from(page.querySelectorAll('[data-element-id]')).map((element, order) => {
    const richContent = sanitizeRichContent(element)
    return {
      elementID: element.dataset.elementId,
      kind: element.dataset.elementKind,
      order,
      text: element.textContent.trim(),
      contentHTML: richContent.html,
      inlineIDs: richContent.inlineIDs,
      styleID: element.dataset.styleId,
      evidenceIDs: (element.dataset.evidenceIds || '').split(',').filter(Boolean),
    }
  })

  const projectElements = (options = {}) => {
    if (!store.editorReady) return fallbackProjectElements()
    const liveElements = editor.getElements()
    const expectedElements = store.currentProject?.elements || fallbackProjectElements()
    const editableBlockKinds = new Set(['heading', 'paragraph', 'list-item'])
    const kindMatches = (live, expected) => live === expected || (editableBlockKinds.has(live) && editableBlockKinds.has(expected))
    const structureMatches = liveElements.length === expectedElements.length && liveElements.every((element, order) => (
      element.id === expectedElements[order].elementID && kindMatches(element.type, expectedElements[order].kind)
    ))
    if (!structureMatches) {
      if (!options.silent) announce('GenOffice 편집기 구조가 프로젝트 원본과 달라 저장하거나 내보낼 수 없습니다.')
      return null
    }
    const elements = liveElements.map((element, order) => {
      const previous = expectedElements[order]
      const contentHTML = preserveTableMarkup(element.contentHTML ?? previous.contentHTML ?? element.text, previous, element.text)
      const inlineIDs = inlineIDsFromContent(contentHTML)
      const tableSnapshot = isEasyTableElement(previous)
        || element.type === 'table'
        || element.type === 'approval-grid'
      if (!tableSnapshot
        && Array.isArray(element.inlineIDs)
        && element.inlineIDs.join('\u0000') !== inlineIDs.join('\u0000')) {
        if (!options.silent) announce('GenOffice 편집기 인라인 식별자가 프로젝트 원본과 달라 저장하거나 내보낼 수 없습니다.')
        return null
      }
      const snapshot = {
        ...previous,
        elementID: element.id,
        kind: element.type,
        order,
        text: element.text,
        contentHTML,
        inlineIDs,
        styleID: previous?.styleID || (element.level === 1 ? 'style-title' : element.level ? 'style-section-heading' : 'style-body'),
        evidenceIDs: previous?.evidenceIDs || [],
      }
      const tools = easyTools()
      return tools && typeof tools.bindTableText === 'function' ? tools.bindTableText(snapshot) : snapshot
    })
    return elements.some((element) => element === null) ? null : elements
  }

  Object.assign(studio, {
    revisionTimestamp,
    isTitleElement,
    isEasyTableElement,
    tablePlainText,
    preserveTableMarkup,
    ensureStableInlineIDs,
    sanitizeRichContent,
    rehydrateRichContent,
    inlineIDsFromContent,
    fallbackProjectElements,
    projectElements
  })
}(window.PublicDocumentStudio))
