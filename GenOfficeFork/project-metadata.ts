import { Extension } from '@tiptap/core'

const types = ['docParagraph', 'docHeading', 'docListItem', 'docProtected', 'docTable', 'publicDocumentProtected'] as const

export const ProjectMetadata = Extension.create({
  name: 'publicDocumentProjectMetadata',
  addGlobalAttributes() {
    return [{
      types: [...types],
      attributes: {
        projectElementID: {
          default: null,
          parseHTML: (element) => element.getAttribute('data-element-id'),
          renderHTML: (attrs) => attrs['projectElementID'] ? { 'data-element-id': attrs['projectElementID'] } : {},
        },
        projectKind: { default: null },
        projectContentHTML: { default: '' },
      },
    }]
  },
})
