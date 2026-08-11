import { Mark } from '@tiptap/core'

export const ProjectInlineIdentity = Mark.create({
  name: 'publicDocumentInlineIdentity',
  inclusive: false,
  addAttributes() {
    return {
      inlineID: {
        default: null,
        parseHTML: (element) => element.getAttribute('data-inline-id'),
        renderHTML: (attrs) => attrs['inlineID'] ? { 'data-inline-id': attrs['inlineID'] } : {},
      },
    }
  },
  parseHTML() {
    return [{ tag: '[data-inline-id]' }]
  },
  renderHTML({ HTMLAttributes }) {
    return ['span', HTMLAttributes, 0]
  },
})

export function alignmentOf(html: string): string | null {
  return /data-public-document-align=["'](left|center)["']/.exec(html)?.[1] ?? null
}

export function serializedInlineIDs(html: string): readonly string[] {
  const values = [...new DOMParser().parseFromString(html, 'text/html').querySelectorAll('[data-inline-id]')].map((element) => element.getAttribute('data-inline-id')).filter((value): value is string => Boolean(value))
  return [...new Set(values)]
}
