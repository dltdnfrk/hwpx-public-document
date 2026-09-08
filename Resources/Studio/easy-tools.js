const PublicDocumentEasyTools = (() => {
  const SMALL = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
  const officialLayoutProfile = () => {
    const profile = globalThis.PublicDocumentOfficialLayoutProfile
    if (!profile || profile.schemaVersion !== 1 || !profile.page || !profile.page.marginMm) {
      throw new Error('official layout profile is missing or invalid')
    }
    return profile
  }

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
    if (typeof value === 'bigint') return value
    if (typeof value === 'number') {
      return Number.isSafeInteger(value) ? BigInt(value) : null
    }
    const match = String(value || '').trim().match(
      /^(-?)(\d+|\d{1,3}(?:,\d{3})+)(?:원)?$/,
    )
    if (!match) return null
    const digits = match[2].replace(/,/g, '')
    if (!digits) return null
    const amount = BigInt(digits)
    return match[1] ? -amount : amount
  }

  const readUnder10000 = (value) => {
    if (value === 0n) return ''
    const numeric = Number(value)
    const parts = [
      [Math.floor(numeric / 1000), '천'],
      [Math.floor(numeric / 100) % 10, '백'],
      [Math.floor(numeric / 10) % 10, '십'],
      [numeric % 10, ''],
    ]
    return parts.map(([digit, unit]) => {
      if (!digit) return ''
      if (digit === 1 && unit && unit !== '천') return unit
      return `${SMALL[digit]}${unit}`
    }).join('')
  }

  const readKoreanNumber = (value) => {
    if (value === 0n) return '영'
    const groups = [
      '', '만', '억', '조', '경', '해', '자', '양', '구', '간',
      '정', '재', '극', '항하사', '아승기', '나유타', '불가사의', '무량대수',
    ]
    let remaining = value
    let spoken = ''
    let index = 0
    while (remaining > 0n) {
      const chunk = remaining % 10000n
      remaining /= 10000n
      if (index >= groups.length) return ''
      const group = groups[index]
      index += 1
      if (chunk === 0n) continue
      spoken = `${readUnder10000(chunk)}${group}${spoken}`
    }
    return spoken
  }

  const numberToKoreanCurrency = (value) => {
    const amount = parseAmount(value)
    if (amount == null) return ''
    const negative = amount < 0n
    const magnitude = negative ? -amount : amount
    const spoken = readKoreanNumber(magnitude)
    if (!spoken) return ''
    const comma = magnitude.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
    return `${negative ? '-' : ''}${comma}원(금${negative ? '마이너스' : ''}${spoken}원정)`
  }

  const parseTable = (html) => {
    const source = String(html || '')
    const table = source.match(/<table[\s\S]*<\/table>/i)
    if (table) return table[0]
    if (!/<tr/i.test(source)) return ''
    const body = /<tbody/i.test(source) ? source : `<tbody>${source}</tbody>`
    return `<table data-easy-table="true">${body}</table>`
  }

  const decodeHTMLEntities = (value) => {
    const source = String(value || '')
    if (typeof document !== 'undefined' && typeof document.createElement === 'function') {
      const template = document.createElement('template')
      template.innerHTML = source
      return template.content.textContent || ''
    }
    return source.replace(/&(?:#(\d+)|#x([0-9a-f]+)|amp|lt|gt|quot|apos);/gi, (entity, decimal, hexadecimal) => {
      if (decimal) return String.fromCodePoint(Number(decimal))
      if (hexadecimal) return String.fromCodePoint(Number.parseInt(hexadecimal, 16))
      return { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&apos;': "'" }[entity.toLowerCase()] || entity
    })
  }

  const tablePlainText = (html) => decodeHTMLEntities(
    String(html || '').replace(/<[^>]+>/g, ' ')
  ).replace(/\s+/g, ' ').trim()

  const bindTableText = (element) => {
    const html = element && element.contentHTML || ''
    const isTable = Boolean(element && (
      element.kind === 'table' || element.kind === 'approval-grid' || /<table|data-easy-table/i.test(html)
    ))
    if (!isTable || !html) return element
    return { ...element, text: tablePlainText(html) }
  }

  const ATTACHMENT_TAILS = /(?:붙임|별첨|관련|첨부)\s*$/
  const NUMBERED_ITEM = /^\d+\.\s/

  const splitOfficialLines = (text) => {
    const source = String(text || '').replace(/\r\n/g, '\n').trim()
    if (!source) return []
    const parts = source
      .split(/(?=\s*(?:○|□|※)\s)|(?=\s+-\s)|(?=\s+\d+단계:)|(?<=(?:함|음|다)\.\s)(?=\d+\.\s)|(?<=\s)(?=[1-9]\d?\.\s[가-힣○□])|(?<=\s)(?=[가나다라마바사아자차카타파하]\.\s[가-힣○□0-9])/)
      .map((line) => line.replace(/\s+/g, ' ').trim())
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
    return merged.length ? merged : [source.replace(/\s+/g, ' ').trim()]
  }

  const mapCells = (html, mutate) => parseTable(html).replace(/<(th|td)([^>]*)>([\s\S]*?)<\/\1>/gi, (full, tag, attrs, inner) => {
    const next = mutate(tag, attrs, inner)
    return `<${tag}${next.attrs}>${next.inner}</${tag}>`
  })

  const cleanPastedTable = (html) => mapCells(html, (tag, attrs, inner) => ({
    attrs,
    inner: inner.replace(/&nbsp;|\u00a0/g, ' ').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim(),
  }))

  const createTableHTML = (rows, cols) => {
    const safeRows = Number(rows)
    const safeCols = Number(cols)
    if (
      !Number.isInteger(safeRows)
      || !Number.isInteger(safeCols)
      || safeRows < 1
      || safeRows > 100
      || safeCols < 1
      || safeCols > 20
    ) return ''
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
    const color = style === 'none' ? 'transparent' : '#7f8986'
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
    if (preset === 'official') return { ...officialLayoutProfile().page.marginMm }
    return { top: 20, right: 20, bottom: 20, left: 20 }
  }

  const labeledBody = (line, names) => {
    const escaped = names.map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
    const colon = line.match(new RegExp(`^(?:${escaped})\\s*[:：]\\s*(.*)$`))
    if (colon) return colon[1]
    const spaced = line.match(new RegExp(`^(?:${escaped})\\s+(.+)$`))
    return spaced ? spaced[1] : null
  }

  const applyOfficialBlockLine = (line) => {
    const indent = (line.match(/^\s*/) || [''])[0]
    const trimmed = line.trim()
    if (!trimmed) return line
    let body = labeledBody(trimmed, ['제목'])
    if (body != null) return indent + body.trim()
    body = labeledBody(trimmed, ['중제목'])
    if (body != null) return indent + `□ ${body}`
    body = labeledBody(trimmed, ['소제목'])
    if (body != null) return indent + `○ ${body}`
    body = labeledBody(trimmed, ['참고', '글상자'])
    if (body != null) return indent + `※ ${body}`
    body = labeledBody(trimmed, ['붙임'])
    if (body != null) return indent + `붙임 ${body}`
    body = labeledBody(trimmed, ['네모', 'ㅁ'])
    if (body != null) return indent + `□ ${body}`
    body = labeledBody(trimmed, ['원', 'ㅇ'])
    if (body != null) return indent + `○ ${body}`
    body = labeledBody(trimmed, ['바'])
    if (body != null) return indent + `- ${body}`
    body = labeledBody(trimmed, ['별'])
    if (body != null) return indent + `* ${body}`
    body = labeledBody(trimmed, ['당구장', '당구'])
    if (body != null) return indent + `※ ${body}`
    return indent + normalizeOfficialMarkers(trimmed)
  }

  const applyOfficialBlock = (text) => String(text || '').split('\n').map(applyOfficialBlockLine).join('\n')

  const applyOfficialMarker = (text, marker) => {
    const prefix = { square: '□ ', circle: '○ ', bar: '- ', star: '* ', note: '※ ' }[marker]
    if (!prefix) return String(text || '')
    return String(text || '').split('\n').map((line) => {
      const indent = (line.match(/^\s*/) || [''])[0]
      const trimmed = line.trim()
      if (!trimmed) return line
      const stripped = trimmed.replace(/^(?:□|○|※|\*(?=\s)|-\s)\s*/, '').replace(/^[ㅁㅇㆍ]\s*/, '')
      return indent + prefix + stripped
    }).join('\n')
  }

  const wrapOfficialBracket = (text, kind) => {
    const inner = String(text || '').trim().replace(/^(?:「|\[)\s*/, '').replace(/\s*(?:」|\])$/, '')
    if (!inner) return ''
    if (kind === 'square') return `[${inner}]`
    return `「${inner}」`
  }

  const formatThousandsInText = (text) => String(text || '').replace(/(?<![\d.,])(\d{4,})(?![\d.,])/g, (digits) => {
    if (/^(?:19|20)\d{2}$/.test(digits)) return digits
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  })

  const attachmentLine = (title, copies) => {
    const name = String(title || '자료').trim() || '자료'
    const count = Math.max(1, Number(copies) || 1)
    return `붙임 1. ${name} ${count}부.`
  }

  const endMark = () => '끝.'

  const REPORT_STRUCTURES = {
    'one-page': [
      { kind: 'heading', text: '□ 개요', styleID: 'style-section-heading' },
      { kind: 'paragraph', text: '○ 추진 배경', styleID: 'style-body' },
      { kind: 'paragraph', text: '○ 주요 내용', styleID: 'style-body' },
      { kind: 'paragraph', text: '- 세부 계획', styleID: 'style-body-detail' },
      { kind: 'paragraph', text: '※ 참고', styleID: 'style-reference-note' },
    ],
    'long-report': [
      { kind: 'heading', text: '1. 보고 개요', styleID: 'style-section-heading' },
      { kind: 'paragraph', text: '가. 추진 배경', styleID: 'style-body' },
      { kind: 'paragraph', text: '나. 주요 내용', styleID: 'style-body' },
      { kind: 'paragraph', text: '다. 향후 계획', styleID: 'style-body' },
      { kind: 'paragraph', text: '붙임 1. 관련 자료 1부.', styleID: 'style-body' },
      { kind: 'paragraph', text: '끝.', styleID: 'style-body' },
    ],
  }

  const reportStructure = (kind) => (REPORT_STRUCTURES[kind] || []).map((item) => ({ ...item }))

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
    bindTableText,
    splitOfficialLines,
    cleanPastedTable,
    createTableHTML,
    addTableRow,
    setTableBorders,
    setTableCellFill,
    hangingIndent,
    pageMargins,
    applyOfficialBlock,
    applyOfficialMarker,
    wrapOfficialBracket,
    formatThousandsInText,
    attachmentLine,
    endMark,
    reportStructure,
    mergeDocumentElements,
    extractAmountFromText,
  }
})()

globalThis.PublicDocumentEasyTools = PublicDocumentEasyTools
if (typeof module === 'object' && module.exports) module.exports = PublicDocumentEasyTools
