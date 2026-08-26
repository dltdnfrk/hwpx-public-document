window.PublicDocumentStudio = window.PublicDocumentStudio || {}

;(function (studio) {
  studio.dom = {
    statusMessage: document.querySelector('.status-message'),
    page: document.querySelector('#static-editor-fallback'),
    editor: document.querySelector('public-document-genoffice-editor'),
    workspace: document.querySelector('.workspace'),
    outlineToggle: document.querySelector('[data-action="outline"]'),
    titleInput: document.querySelector('.document-title input'),
    inspector: document.querySelector('.project-inspector'),
    outlineList: document.querySelector('.outline-list'),
    checklist: document.querySelector('.checklist'),
    templatePanel: document.querySelector('.template-governance'),
    exportResult: document.querySelector('.export-result'),
    exportSetup: document.querySelector('.export-setup'),
    exportConsent: document.querySelector('[data-export-consent]'),
    batchExportProgress: document.querySelector('.batch-export-progress'),
    aiWorkspace: document.querySelector('.ai-workspace'),
    aiProposalReview: document.querySelector('[data-ai-proposal-review]'),
    byokSettings: document.querySelector('.byok-settings'),
    easyToolDialog: document.querySelector('.easy-tool-dialog'),
  }

  studio.state = {
    studioSession: '',
    currentProject: null,
    currentTemplateCatalog: null,
    currentOfficialRuleState: null,
    autosaveTimer: null,
    periodicSaveTimer: null,
    selectedAIOperation: 'source-grounded-draft',
    pendingAIProposal: null,
    aiSettingsSnapshot: { activeProvider: null, providers: [], catalog: [] },
    suppressEditorAutosave: false,
    pendingEasyConfirm: null,
    pendingMergeHeading: '',
    studioPrefs: { autosaveIntervalMs: 180000, favorites: [], myForms: [] },
    libraryEntries: [],
    libraryProjects: {},
    activeBatchOperationID: null,
    activeBatchRetryOperationID: null,
    editorReady: false,
    focusedEditorElementID: null,
    selectedEditorElementID: null,
    selectionStartedByUser: false,
  }

  studio.isLocalWeb = () => !(window.webkit && window.webkit.messageHandlers.projectStore)
  studio.easyTools = () => window.PublicDocumentEasyTools
  studio.compactLayout = window.matchMedia('(max-width: 1099px)')
  studio.dialogOpeners = new WeakMap()
  studio.allowedRichTags = new Set(['B', 'BR', 'DIV', 'EM', 'FONT', 'I', 'LI', 'OL', 'SPAN', 'STRONG', 'TABLE', 'TBODY', 'TD', 'TFOOT', 'TH', 'THEAD', 'TR', 'U', 'UL'])
  studio.allowedFontFaces = new Set(Array.from(document.querySelectorAll('[data-format="fontName"] option'), (option) => option.value))
}(window.PublicDocumentStudio))
