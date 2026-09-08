import { Editor } from '@tiptap/core'
import { DOMSerializer, type Node as ProseMirrorNode } from '@tiptap/pm/model'
import { createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { IconStop } from '@genoffice/ui'
import { NavPane } from '@genoffice-upstream/apps/docs/src/renderer/components/NavPane'
import { editorExtensions } from '@genoffice-upstream/apps/docs/src/renderer/editor/extensions'
import { ProjectMetadata } from './project-metadata'
import { alignmentOf, ProjectInlineIdentity, serializedInlineIDs } from './project-inline-identity'
import { PublicDocumentProtected } from './project-protected'
import { selectionState, type SelectionState } from './selection-state'

type InputElement = Readonly<{ elementID: string; kind: string; text: string; contentHTML?: string; styleID?: string }>
type Project = Readonly<{ elements: readonly InputElement[] }>
type OutputElement = Readonly<{ id: string; type: string; text: string; contentHTML: string; inlineIDs: readonly string[]; level?: number }>
type PmInline = Readonly<{ type: string; text?: string; marks?: readonly Readonly<{ type: string; attrs?: Readonly<Record<string, unknown>> }>[] }>

const COMMIT = 'd8305ff2dc152593a1ec5639d77e6860c6a512bd'
const css = `:host{display:block;min-height:480px;color:var(--studio-ink);background:var(--studio-panel);font:13px -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}.shell{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:480px;border:1px solid var(--studio-border-strong)}.brand{grid-column:1/-1;display:flex;gap:8px;align-items:center;padding:8px 12px;color:var(--studio-accent-strong);background:var(--studio-accent-soft);border-bottom:1px solid var(--studio-accent-border);font-weight:700}.nav-pane{padding:12px;border-right:1px solid var(--studio-border);background:var(--studio-panel)}.nav-pane-title{font-weight:700;margin-bottom:8px}.nav-item{display:block;width:100%;padding:6px 8px;border:0;background:transparent;text-align:left;color:var(--studio-ink)}.nav-l2{padding-left:20px}.nav-l3,.nav-l4{padding-left:32px}.nav-empty{color:var(--studio-muted)}.paper{box-sizing:border-box;width:min(794px,calc(100% - 48px));margin:24px auto;padding:48px;min-height:1123px;background:var(--studio-surface);box-shadow:0 1px 2px color-mix(in srgb,var(--studio-ink) 12%,transparent),0 12px 32px color-mix(in srgb,var(--studio-ink) 8%,transparent)}.ProseMirror{outline:none;font-size:15px;line-height:1.78;word-break:keep-all;overflow-wrap:anywhere}.ProseMirror h1{font-size:28px}.ProseMirror h2,.ProseMirror h3{font-size:17px}.doc-table{width:100%;margin:12px 0;border-collapse:collapse}.doc-table th,.doc-table td{padding:8px 12px;border:1px solid var(--studio-document-rule);text-align:left}.doc-table th{background:var(--studio-document-fill);font-weight:700}:host([hide-navigation]) .shell{grid-template-columns:1fr}:host([hide-navigation]) .navigation{display:none}[data-project-protected]{padding:12px;border:1px solid var(--studio-border);background:var(--studio-document-fill)}@media(max-width:1100px){.shell{grid-template-columns:1fr}.navigation{display:none}}`

function isProject(value: unknown): value is Project {
  if (typeof value !== 'object' || value === null) return false
  const elements = Reflect.get(value, 'elements')
  return Array.isArray(elements) && elements.every((item) => typeof item === 'object' && item !== null && typeof Reflect.get(item, 'elementID') === 'string' && typeof Reflect.get(item, 'kind') === 'string' && typeof Reflect.get(item, 'text') === 'string')
}

function pmContent(elements: readonly InputElement[]) {
  return { type: 'doc', content: elements.map((item) => {
    const metadata = { projectElementID: item.elementID, projectKind: item.kind, projectContentHTML: item.contentHTML ?? '' }
    const inline = richInline(item.contentHTML ?? '', item.text)
    const align = alignmentOf(item.contentHTML ?? '')
    if (item.kind === 'heading' || item.kind === 'title') return { type: 'docHeading', attrs: { ...metadata, docxIndex: null, styleId: item.styleID ?? null, aiChanged: false, align, level: item.kind === 'title' || item.styleID === 'style-title' || item.elementID === 'element-title' ? 1 : 2 }, content: inline }
    if (item.kind === 'list' || item.kind === 'list-item') return { type: 'docListItem', attrs: { ...metadata, docxIndex: null, styleId: null, aiChanged: false, align, kind: 'bullet', ilvl: 0 }, content: inline }
    if (item.kind === 'table' || item.kind === 'approval-grid') return tableNode(item, metadata)
    if (item.kind === 'paragraph' || item.kind === 'body') return { type: 'docParagraph', attrs: { ...metadata, docxIndex: null, styleId: null, aiChanged: false, align }, content: inline }
    return { type: 'publicDocumentProtected', attrs: { ...metadata, previewText: item.text } }
  }) }
}

function richInline(html: string, fallback: string): PmInline[] {
  const body = new DOMParser().parseFromString(html, 'text/html').body
  if (!html) body.textContent = fallback
  const output: PmInline[] = []
  const isBlock = (node: Node): boolean => node instanceof HTMLElement && node.matches('div,p,h1,h2,h3,h4,h5,h6,li,ul,ol,blockquote,pre,section,article')
  const children = (node: Node, marks: readonly Readonly<{ type: string; attrs?: Readonly<Record<string, unknown>> }>[]): void => {
    node.childNodes.forEach((child, index) => {
      const previous = node.childNodes.item(index - 1)
      if (previous && (isBlock(previous) || isBlock(child))) output.push({ type: 'hardBreak' })
      walk(child, marks)
    })
  }
  const walk = (node: Node, marks: readonly Readonly<{ type: string; attrs?: Readonly<Record<string, unknown>> }>[]): void => {
    if (node.nodeType === Node.TEXT_NODE) {
      node.textContent?.split('\n').forEach((text, index) => {
        if (index > 0) output.push({ type: 'hardBreak', marks })
        if (text) output.push({ type: 'text', text, marks })
      })
      return
    }
    if (!(node instanceof HTMLElement)) return
    if (node.matches('br.ProseMirror-trailingBreak')) return
    if (node.matches('br')) {
      output.push({ type: 'hardBreak', marks })
      return
    }
    const next = [...marks]
    const inlineID = node.getAttribute('data-inline-id')
    if (inlineID) next.push({ type: 'publicDocumentInlineIdentity', attrs: { inlineID } })
    if (node.matches('b,strong')) next.push({ type: 'bold' })
    if (node.matches('i,em')) next.push({ type: 'italic' })
    if (node.matches('u')) next.push({ type: 'underline' })
    const font = node.getAttribute('face') ?? node.style.fontFamily.split(',')[0].trim().replace(/["']/g, '')
    const sizeText = node.style.fontSize
    const size = sizeText.endsWith('pt') ? Number.parseFloat(sizeText) * 2 : null
    if (font || size) next.push({ type: 'docTextStyle', attrs: { font: font || null, fontAscii: font || null, sizeHalfPoints: size } })
    children(node, next)
  }
  children(body, [])
  return output
}

function tableNode(item: InputElement, metadata: Readonly<Record<string, unknown>>) {
  const html = item.contentHTML ?? ''
  let parsed = new DOMParser().parseFromString(html, 'text/html')
  let tableRows = [...parsed.querySelectorAll('tr')]
  if (tableRows.length === 0 && /<t[dh]|<tr/i.test(html)) {
    parsed = new DOMParser().parseFromString(`<table><tbody>${html}</tbody></table>`, 'text/html')
    tableRows = [...parsed.querySelectorAll('tr')]
  }
  const approvalCells = tableRows.length === 0 ? [...parsed.body.children].filter((node) => node.matches('span,b,strong')).slice(0, 6) : []
  const rows = tableRows.length > 0 ? tableRows.map((row) => [...row.querySelectorAll(':scope > th,:scope > td')]) : approvalCells.length === 6 ? [approvalCells.slice(0, 3), approvalCells.slice(3, 6)] : [[document.createTextNode(item.text)]]
  return { type: 'docTable', attrs: { ...metadata, docxIndex: null, widthPct: 100 }, content: rows.map((cells, rowIndex) => ({ type: 'docTableRow', content: cells.map((cell) => ({ type: item.kind === 'approval-grid' && rowIndex === 0 || cell.nodeName === 'TH' ? 'docTableHeader' : 'docTableCell', attrs: { colspan: cell instanceof HTMLElement ? Number(cell.getAttribute('colspan') ?? 1) : 1, rowspan: cell instanceof HTMLElement ? Number(cell.getAttribute('rowspan') ?? 1) : 1 }, content: [{ type: 'docParagraph', attrs: { docxIndex: null, styleId: null, aiChanged: false }, content: richInline(cell instanceof HTMLElement ? cell.innerHTML : '', cell.textContent?.trim() ?? '') }] })) })) }
}

class PublicDocumentEditor extends HTMLElement {
  readonly #shadow = this.attachShadow({ mode: 'open' })
  readonly #editorNode = document.createElement('article')
  readonly #navNode = document.createElement('div')
  #editor: Editor | undefined
  #root: Root | undefined
  #revision = 0
  #focusedElementID: string | undefined
  #assigningMetadata = false

  connectedCallback(): void {
    if (this.#editor) return
    const style = document.createElement('style')
    style.textContent = css
    const shell = document.createElement('section')
    shell.className = 'shell'
    const brand = document.createElement('div')
    brand.className = 'brand'
    brand.append('Public Document · GenOffice Docs')
    this.#navNode.className = 'navigation'
    this.#editorNode.className = 'paper'
    shell.append(brand, this.#navNode, this.#editorNode)
    this.#shadow.append(style, shell)
    this.#root = createRoot(this.#navNode)
    this.#navNode.addEventListener('click', (event) => this.#focusNavItem(event))
    this.#editor = new Editor({ element: this.#editorNode, extensions: [...editorExtensions, ProjectMetadata, ProjectInlineIdentity, PublicDocumentProtected], content: pmContent([]), editorProps: { attributes: { 'aria-label': '공공문서 본문' } }, onUpdate: () => this.#changed(), onSelectionUpdate: () => this.dispatchEvent(new CustomEvent('public-document-genoffice-selection-change', { bubbles: true, composed: true, detail: this.getSelectionState() })) })
    brand.prepend(createElementNode(IconStop))
    this.#renderNav()
    this.dispatchEvent(new CustomEvent('public-document-genoffice-ready', { bubbles: true, composed: true, detail: { version: 1, upstreamCommit: COMMIT } }))
  }

  disconnectedCallback(): void {
    this.#root?.unmount()
    this.#editor?.destroy()
    this.#root = undefined
    this.#editor = undefined
  }

  setProject(value: unknown): void {
    if (!isProject(value) || !this.#editor) return
    this.#editor.commands.setContent(pmContent(value.elements), false)
    let firstEditable: Readonly<{ id: string; position: number }> | undefined
    this.#editor.state.doc.forEach((node, position) => {
      if (!firstEditable && node.isTextblock && typeof node.attrs['projectElementID'] === 'string') firstEditable = { id: node.attrs['projectElementID'], position }
    })
    this.#focusedElementID = firstEditable?.id
    if (firstEditable) this.#editor.commands.setTextSelection(firstEditable.position + 1)
    this.#renderNav()
  }

  getElements(): OutputElement[] {
    if (!this.#editor) return []
    const output: OutputElement[] = []
    const serializer = DOMSerializer.fromSchema(this.#editor.schema)
    this.#editor.state.doc.forEach((node, _offset, index) => {
      const rawID = node.attrs['projectElementID']
      const id = typeof rawID === 'string' && rawID ? rawID : `element-${this.#revision + 1}-${index + 1}`
      const rawKind = node.attrs['projectKind']
      const type = typeof rawKind === 'string' && rawKind ? rawKind : node.type.name === 'docHeading' ? 'heading' : node.type.name === 'docListItem' ? 'list-item' : node.type.name === 'publicDocumentProtected' ? 'protected' : 'paragraph'
      const rawHTML = node.attrs['projectContentHTML']
      const protectedHTML = typeof rawHTML === 'string' ? rawHTML : ''
      // Serialize document content, not view-only caret/trailing-break decorations.
      const dom = serializer.serializeNode(node)
      const contentHTML = node.type.name === 'publicDocumentProtected' ? protectedHTML : dom instanceof HTMLElement ? dom.innerHTML : protectedHTML
      const alignedHTML = typeof node.attrs['align'] === 'string' ? `<span data-public-document-align="${node.attrs['align']}">${contentHTML}</span>` : contentHTML
      const inlineIDs = serializedInlineIDs(alignedHTML)
      const level = node.type.name === 'docHeading' ? Number(node.attrs['level'] ?? 2) : undefined
      const text = node.type.name === 'publicDocumentProtected' ? String(node.attrs['previewText'] ?? '') : node.textBetween(0, node.content.size, '\n', (leaf) => leaf.type.name === 'hardBreak' ? '\n' : '')
      output.push(level === undefined ? { id, type, text, contentHTML: alignedHTML, inlineIDs } : { id, type, text, contentHTML: alignedHTML, inlineIDs, level })
    })
    return output
  }

  command(name: string, value?: unknown): boolean {
    const editor = this.#editor
    if (!editor) return false
    const block = this.#focusedBlock()
    if (!block) return false
    const selectedAttrs = block.node.attrs
    const metadata = { projectElementID: selectedAttrs['projectElementID'] ?? null, projectKind: selectedAttrs['projectKind'] ?? null, projectContentHTML: selectedAttrs['projectContentHTML'] ?? '' }
    const { selection } = editor.state
    // Collapsed selections intentionally retain the whole-block formatting macros.
    const from = selection.empty ? block.position + 1 : selection.from
    const to = selection.empty ? from + block.node.content.size : selection.to
    if (name === 'bold' || name === 'italic' || name === 'underline') {
      const mark = editor.schema.marks[name]
      if (!mark || from === to) return false
      const transaction = editor.state.tr
      let hasText = false
      let allMarked = true
      editor.state.doc.nodesBetween(from, to, (node) => { if (node.isText) { hasText = true; if (!mark.isInSet(node.marks)) allMarked = false } })
      if (hasText && allMarked) transaction.removeMark(from, to, mark)
      else transaction.addMark(from, to, mark.create())
      editor.view.dispatch(transaction)
      return true
    }
    if (name === 'undo') return editor.commands.undo()
    if (name === 'redo') return editor.commands.redo()
    if (name === 'paragraph') return this.#setBlockType('docParagraph', metadata)
    if (name === 'heading' && typeof value === 'number' && value >= 1 && value <= 6) return this.#setBlockType('docHeading', { ...metadata, level: value })
    if ((name === 'fontName' && typeof value === 'string' && value) || (name === 'fontSize' && typeof value === 'number' && value >= 3 && value <= 96)) {
      const mark = editor.schema.marks['docTextStyle']
      if (!mark || from === to) return false
      const transaction = editor.state.tr
      editor.state.doc.nodesBetween(from, to, (node, position) => {
        if (!node.isText) return
        const existing = node.marks.find((candidate) => candidate.type === mark)?.attrs ?? {}
        const attrs = name === 'fontName' ? { ...existing, font: value, fontAscii: value } : { ...existing, sizeHalfPoints: Number(value) * 2 }
        transaction.addMark(Math.max(from, position), Math.min(to, position + node.nodeSize), mark.create(attrs))
      })
      editor.view.dispatch(transaction)
      return true
    }
    if (name === 'justifyLeft' || name === 'justifyCenter') {
      const attrs = { align: name === 'justifyCenter' ? 'center' : 'left' }
      editor.view.dispatch(editor.state.tr.setNodeMarkup(block.position, undefined, { ...block.node.attrs, ...attrs }))
      return true
    }
    if (name === 'insertUnorderedList') return block.node.type.name === 'docListItem' ? this.#setBlockType('docParagraph', { ...metadata, projectKind: 'paragraph' }) : this.#setBlockType('docListItem', { ...metadata, projectKind: 'list-item', kind: 'bullet', numId: null, ilvl: 0 })
    if (name === 'insertText' && typeof value === 'string' && block.node.isTextblock) {
      editor.view.dispatch(editor.state.tr.insertText(value))
      return true
    }
    return false
  }

  supportsCommand(name: string): boolean {
    return ['bold', 'italic', 'underline', 'undo', 'redo', 'paragraph', 'heading', 'fontName', 'fontSize', 'justifyLeft', 'justifyCenter', 'insertUnorderedList', 'insertText'].includes(name)
  }

  getSelectionState(): SelectionState { return selectionState(this.#editor, this.#focusedElementID) }

  focusElement(elementID: string, placement: 'start' | 'end' = 'start'): boolean {
    if (!this.#editor) return false
    let position: number | undefined
    let contentSize = 0
    this.#editor.state.doc.forEach((node, offset) => {
      if (node.attrs['projectElementID'] === elementID) {
        position = offset
        contentSize = node.content.size
      }
    })
    if (position === undefined) return false
    this.#focusedElementID = elementID
    this.#editor.commands.setTextSelection(position + (placement === 'end' ? contentSize + 1 : 1))
    this.#editor.view.focus()
    const target = this.#editor.view.nodeDOM(position)
    if (target instanceof HTMLElement) {
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      target.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' })
    }
    return true
  }

  #focusedBlock(): Readonly<{ node: ProseMirrorNode; position: number }> | undefined {
    if (!this.#editor) return undefined
    const { $from } = this.#editor.state.selection
    // The document selection is authoritative for pointer, keyboard, and API focus.
    if ($from.depth > 0) return { node: $from.node(1), position: $from.before(1) }
    const node = this.#editor.state.doc.nodeAt($from.pos)
    return node ? { node, position: $from.pos } : undefined
  }

  #focusNavItem(event: Event): void {
    if (!this.#editor || !(event.target instanceof HTMLElement)) return
    const button = event.target.closest('.nav-item')
    if (!button) return
    const index = [...this.#navNode.querySelectorAll('.nav-item')].indexOf(button)
    const headingIDs: string[] = []
    this.#editor.state.doc.forEach((node) => { if (node.type.name === 'docHeading' && typeof node.attrs['projectElementID'] === 'string') headingIDs.push(node.attrs['projectElementID']) })
    const id = headingIDs[index]
    if (id) this.focusElement(id)
  }

  #setBlockType(name: string, attrs: Readonly<Record<string, unknown>>): boolean {
    const editor = this.#editor
    const block = this.#focusedBlock()
    const type = editor?.schema.nodes[name]
    if (!editor || !block || !type || !type.validContent(block.node.content)) return false
    editor.view.dispatch(editor.state.tr.setNodeMarkup(block.position, type, { ...block.node.attrs, ...attrs }))
    return true
  }

  #renderNav(): void {
    if (this.#root && this.#editor) this.#root.render(createElement(NavPane, { editor: this.#editor, doc: this.#editor.state.doc }))
  }

  #changed(): void {
    if (this.#editor && !this.#assigningMetadata) {
      const transaction = this.#editor.state.tr
      this.#editor.state.doc.forEach((node, offset, index) => {
        if (!node.attrs['projectElementID']) transaction.setNodeMarkup(offset, undefined, { ...node.attrs, projectElementID: `element-${crypto.randomUUID()}`, projectKind: node.type.name === 'docListItem' ? 'list-item' : node.type.name === 'docHeading' ? 'heading' : 'paragraph', projectContentHTML: '' })
      })
      if (transaction.docChanged) {
        this.#assigningMetadata = true
        this.#editor.view.dispatch(transaction)
        this.#assigningMetadata = false
        return
      }
    }
    this.#revision += 1
    this.#renderNav()
    this.dispatchEvent(new CustomEvent('public-document-genoffice-change', { bubbles: true, composed: true, detail: { revision: this.#revision, elements: this.getElements() } }))
    this.dispatchEvent(new CustomEvent('public-document-genoffice-selection-change', { bubbles: true, composed: true, detail: this.getSelectionState() }))
  }
}

function createElementNode(component: typeof IconStop): Node { const node = document.createElement('span'); createRoot(node).render(createElement(component, { size: 14 })); return node }

customElements.define('public-document-genoffice-editor', PublicDocumentEditor)
