(function (studio) {
  const store = studio.state
  const { editor, workspace, outlineToggle, outlineList } = studio.dom
  const announce = (...args) => studio.announce(...args)
  const focusEditorElement = (...args) => studio.focusEditorElement(...args)
  const setOutlineCurrent = (...args) => studio.setOutlineCurrent(...args)
  const compactLayout = studio.compactLayout

  const runEditorCommand = (command, value, control) => {
    if (command === 'undo' && studio.undoEasyProjectChange?.()) return true
    if (command === 'redo' && studio.redoEasyProjectChange?.()) return true
    if (!store.editorReady) {
      announce('GenOffice 편집기가 준비되지 않아 편집 명령을 실행하지 않았습니다.')
      return false
    }
    if (typeof editor.supportsCommand === 'function' && !editor.supportsCommand(command)) {
      if (control instanceof HTMLElement) {
        control.disabled = true
        control.title = '현재 GenOffice 편집기에서 지원하지 않는 명령입니다.'
      }
      announce('현재 GenOffice 편집기는 이 명령을 지원하지 않습니다.')
      return false
    }
    const handled = editor.command(command, value)
    syncFormatStates()
    if (!handled) {
      announce('현재 선택 위치에서는 문서 형식이 바뀌지 않았습니다.')
    }
    return handled
  }

  const syncFormatStates = (selectionState = editor.getSelectionState?.()) => {
    if (!selectionState) return
    if (selectionState.elementID) store.focusedEditorElementID = selectionState.elementID
    document.querySelectorAll('[data-command="bold"], [data-command="italic"], [data-command="underline"]').forEach((button) => {
      button.setAttribute('aria-pressed', String(Boolean(selectionState[button.dataset.command])))
    })
  }

  document.querySelectorAll('[data-command]').forEach((button) => {
    button.addEventListener('click', () => {
      if (runEditorCommand(button.dataset.command, undefined, button)) announce(button.getAttribute('aria-label') || button.textContent.trim())
    })
  })

  document.querySelectorAll('[data-format]').forEach((select) => {
    select.addEventListener('change', () => {
      const value = select.dataset.format === 'fontSize' ? Number(select.value) : select.value
      if (runEditorCommand(select.dataset.format, value, select)) announce(`${select.getAttribute('aria-label')}을 변경했습니다.`)
    })
  })

  const toggleOutline = () => {
    const hidden = workspace.classList.toggle('outline-hidden')
    outlineToggle.setAttribute('aria-pressed', String(!hidden))
    const viewOutline = document.querySelector('[data-view-action="toggle-outline"]')
    if (viewOutline) viewOutline.setAttribute('aria-pressed', String(!hidden))
    announce(hidden ? '문서 구조를 닫았습니다.' : '문서 구조를 열었습니다.')
    return !hidden
  }

  outlineToggle.addEventListener('click', () => {
    toggleOutline()
  })

  const syncOutlineForViewport = () => {
    workspace.classList.toggle('outline-hidden', compactLayout.matches)
    outlineToggle.setAttribute('aria-pressed', String(!compactLayout.matches))
  }

  compactLayout.addEventListener('change', syncOutlineForViewport)

  outlineList.addEventListener('click', (event) => {
    const button = event.target.closest('[data-section]')
    if (!button) return
    if (!focusEditorElement(button.dataset.section, button.dataset.elementId)) return
    setOutlineCurrent(button)
  })

  document.querySelector('[data-action="marker"]').addEventListener('click', (event) => {
    if (runEditorCommand('insertText', ' [확인 필요]', event.currentTarget)) announce('확인 필요 표시를 삽입했습니다.')
  })

  document.querySelector('[data-action="check"]').addEventListener('click', () => {
    const results = Object.entries(store.currentProject?.templateBinding?.checklistResults || {})
    const complete = results.filter(([, done]) => done).length
    const missing = results.filter(([, done]) => !done).map(([label]) => label)
    const missingText = missing.length ? ` ${missing.join('과 ')}을 확인하세요.` : ''
    announce(`필수항목 ${results.length}개 중 ${complete}개를 작성했습니다.${missingText}`)
  })

  document.addEventListener('keydown', (event) => {
    if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'y') return
    event.preventDefault()
    runEditorCommand('redo')
  })

  Object.assign(studio, {
    runEditorCommand,
    syncFormatStates,
    syncOutlineForViewport,
    toggleOutline
  })
}(window.PublicDocumentStudio))
