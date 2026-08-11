import type { Editor } from '@tiptap/core'

export type SelectionState = Readonly<{ elementID: string | null; bold: boolean; italic: boolean; underline: boolean }>

function markActive(editor: Editor, name: 'bold' | 'italic' | 'underline'): boolean {
  const mark = editor.schema.marks[name]
  if (!mark) return false
  const { doc, selection, storedMarks } = editor.state
  if (selection.empty) return Boolean(mark.isInSet(storedMarks ?? selection.$from.marks()))
  let hasText = false
  let allMarked = true
  doc.nodesBetween(selection.from, selection.to, (node, position) => {
    if (node.isText && selection.from < position + node.nodeSize && selection.to > position) {
      hasText = true
      if (!mark.isInSet(node.marks)) allMarked = false
    }
  })
  return hasText && allMarked
}

export function selectionState(editor: Editor | undefined, fallbackElementID: string | undefined): SelectionState {
  if (!editor) return { elementID: fallbackElementID ?? null, bold: false, italic: false, underline: false }
  const topLevel = editor.state.selection.$from.depth > 0 ? editor.state.selection.$from.node(1) : null
  const selectedID = topLevel?.attrs['projectElementID']
  return { elementID: typeof selectedID === 'string' ? selectedID : fallbackElementID ?? null, bold: markActive(editor, 'bold'), italic: markActive(editor, 'italic'), underline: markActive(editor, 'underline') }
}
