import { Node } from '@tiptap/core'

export const PublicDocumentProtected = Node.create({
  name: 'publicDocumentProtected',
  group: 'block',
  atom: true,
  selectable: true,
  addAttributes() {
    return { previewText: { default: '' } }
  },
  renderHTML({ node }) {
    return ['div', { 'data-project-protected': '', contenteditable: 'false' }, String(node.attrs['previewText'] ?? '')]
  },
})
