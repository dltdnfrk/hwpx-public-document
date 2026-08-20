const PublicDocumentEasyTools = (() => {
  const SMALL = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']

  const normalizeOfficialMarkers = (text) => String(text || '').split('\n').map((line) => {
    const match = line.match(/^(\s*)([ㅁㅇㆍ□○\-*]|ㅁ\.|ㅇ\.)(\s*)(.*)$/)
    if (!match) return line
    const [, indent, marker, , rest] = match
    const body = rest.trim()
    if (marker === 'ㅁ' || marker === 'ㅁ.') return `${indent}□ ${body}`
    if (marker === 'ㅇ' || marker === 'ㅇ.') return `${indent}○ ${body}`
    if (marker === 'ㆍ' || marker === '*') return `${indent}- ${body}`
    if (marker === '□') return `${indent}□ ${body}`
    if (marker === '○') return `${indent}○ ${body}`
    return `${indent}- ${body}`
  }).join('\n')

  const asDate = (value) => (value instanceof Date ? value : new Date(value))

  const localISODate = (value) => {
    const date = asDate(value)
    if (Number.isNaN(date.getTime())) return ''
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${date.getFullYear()}-${month}-${day}`
  }

  const formatOfficialDate = (value) => {
    const date = asDate(value)
    if (Number.isNaN(date.getTime())) return ''
    return `${date.getFullYear()}. ${date.getMonth() + 1}. ${date.getDate()}.`
  }

  const formatOfficialDateRange = (start, end) => {
    const startDate = asDate(start)
    const endDate = asDate(end)
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return ''
    if (startDate.getTime() > endDate.getTime()) return ''
    return `${formatOfficialDate(startDate)} ~ ${formatOfficialDate(endDate)}`
  }

  const parseAmount = (value) => {
    if (typeof value === 'number' && Number.isFinite(value)) return Math.round(Math.abs(value))
    const digits = String(value || '').replace(/[^\d]/g, '')
    return digits ? Number(digits) : null
  }

  const readUnder10000 = (value) => {
    if (!value) return ''
    const parts = [
      [Math.floor(value / 1000), '천'],
      [Math.floor(value / 100) % 10, '백'],
      [Math.floor(value / 10) % 10, '십'],
      [value % 10, ''],
    ]
    return parts.map(([digit, unit]) => {
      if (!digit) return ''
      if (digit === 1 && unit && unit !== '천') return unit
      return `${SMALL[digit]}${unit}`
    }).join('')
  }

  const readKoreanNumber = (value) => {
    if (value === 0) return '영'
    const groups = ['', '만', '억', '조']
    let remaining = value
    let spoken = ''
    groups.forEach((group, index) => {
      const chunk = remaining % 10000
      remaining = Math.floor(remaining / 10000)
      if (!chunk) return
      spoken = `${readUnder10000(chunk)}${group}${spoken}`
    })
    return spoken
  }

  const numberToKoreanCurrency = (value) => {
    const amount = parseAmount(value)
    if (amount == null) return ''
    const comma = amount.toLocaleString('en-US')
    return `${comma}원(금${readKoreanNumber(amount)}원정)`
  }

  const parseTable = (html) => {
    const source = String(html || '')
    const table = source.match(/<table[\s\S]*<\/table>/i)
    if (table) return table[0]
    if (!/<tr/i.test(source)) return ''
    const body = /<tbody/i.test(source) ? source : `<tbody>${source}</tbody>`
    return `<table data-easy-table="true">${body}</table>`
  }

  const tablePlainText = (html) => String(html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()

  const mapCells = (html, mutate) => parseTable(html).replace(/<(th|td)([^>]*)>([\s\S]*?)<\/\1>/gi, (full, tag, attrs, inner) => {
    const next = mutate(tag, attrs, inner)
    return `<${tag}${next.attrs}>${next.inner}</${tag}>`
  })

  const cleanPastedTable = (html) => mapCells(html, (tag, attrs, inner) => ({
    attrs,
    inner: inner.replace(/&nbsp;|\u00a0/g, ' ').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim(),
  }))

  const createTableHTML = (rows, cols) => {
    const safeRows = Math.max(1, Number(rows) || 1)
    const safeCols = Math.max(1, Number(cols) || 1)
    const cells = Array.from({ length: safeCols }, () => '<td></td>').join('')
    const body = Array.from({ length: safeRows }, () => `<tr>${cells}</tr>`).join('')
    return `<table data-easy-table="true"><tbody>${body}</tbody></table>`
  }

  const addTableRow = (html) => {
    const table = parseTable(html)
    const cols = (table.match(/<tr[\s\S]*?<\/tr>/i) || [''])[0].match(/<(td|th)\b/gi)?.length || 1
    const row = `<tr>${Array.from({ length: cols }, () => '<td></td>').join('')}</tr>`
    if (/<\/tbody>/i.test(table)) return table.replace(/<\/tbody>/i, `${row}</tbody>`)
    return table.replace(/<\/table>/i, `${row}</table>`)
  }

  const setTableBorders = (html, style = 'all') => {
    const color = style === 'none' ? 'transparent' : '#1d1d1f'
    return parseTable(html)
      .replace(/<table([^>]*)>/i, (full, attrs) => `<table${attrs} style="border-collapse:collapse;border:1px solid ${color}">`)
      .replace(/<(td|th)([^>]*)>/gi, (full, tag, attrs) => {
        const cleaned = String(attrs).replace(/\sstyle="[^"]*"/i, '')
        return `<${tag}${cleaned} style="border:1px solid ${color}">`
      })
  }

  const setTableCellFill = (html, rowIndex, colIndex, color) => {
    let row = -1
    return parseTable(html).replace(/<tr[\s\S]*?<\/tr>/gi, (rowHTML) => {
      row += 1
      if (row !== rowIndex) return rowHTML
      let col = -1
      return rowHTML.replace(/<(td|th)([^>]*)>/gi, (full, tag, attrs) => {
        col += 1
        if (col !== colIndex) return full
        const cleaned = String(attrs).replace(/\sstyle="[^"]*"/i, '')
        return `<${tag}${cleaned} style="background:${color}">`
      })
    })
  }

  const hangingIndent = (text) => {
    const words = String(text || '').trim().split(/\s+/).filter(Boolean)
    if (words.length < 2) return words.join(' ')
    const mid = Math.max(1, Math.ceil(words.length / 2))
    const first = words.slice(0, mid).join(' ')
    const second = words.slice(mid).join(' ')
    return `${first}\n${' '.repeat(Math.min(first.length, 8))}${second}`
  }

  const pageMargins = (preset) => {
    if (preset === 'narrow') return { top: 15, right: 15, bottom: 15, left: 15 }
    if (preset === 'wide') return { top: 20, right: 20, bottom: 20, left: 30 }
    return { top: 20, right: 20, bottom: 20, left: 20 }
  }

  const mergeDocumentElements = (current, incoming, heading) => {
    const merged = (current || []).map((element, order) => ({ ...element, order }))
    merged.push({
      elementID: `element-merge-${merged.length}-heading`,
      kind: 'heading',
      order: merged.length,
      text: `□ ${heading}`,
      styleID: 'style-section-heading',
      evidenceIDs: [],
    })
    ;(incoming || []).filter((element) => element.kind === 'paragraph').forEach((element) => {
      merged.push({
        ...element,
        elementID: `element-merge-${merged.length}-body`,
        kind: 'paragraph',
        order: merged.length,
        styleID: element.styleID || 'style-body',
        evidenceIDs: element.evidenceIDs || [],
      })
    })
    return merged
  }

  const extractAmountFromText = (text) => {
    const match = String(text || '').match(/(\d[\d,]*)/)
    return match ? match[1] : ''
  }

  return {
    normalizeOfficialMarkers,
    localISODate,
    formatOfficialDate,
    formatOfficialDateRange,
    numberToKoreanCurrency,
    parseTable,
    tablePlainText,
    cleanPastedTable,
    createTableHTML,
    addTableRow,
    setTableBorders,
    setTableCellFill,
    hangingIndent,
    pageMargins,
    mergeDocumentElements,
    extractAmountFromText,
  }
})()

globalThis.PublicDocumentEasyTools = PublicDocumentEasyTools
if (typeof module === 'object' && module.exports) module.exports = PublicDocumentEasyTools
