(function (studio) {
  const store = studio.state
  const { easyToolDialog, editor } = studio.dom
  const openDialog = (...args) => studio.openDialog(...args)
  const closeDialog = (...args) => studio.closeDialog(...args)
  const easyTools = (...args) => studio.easyTools(...args)
  const announce = (...args) => studio.announce(...args)
  const insertPlainText = (...args) => studio.insertPlainText(...args)
  const liveElements = (...args) => studio.liveElements(...args)
  const commitProjectElements = (...args) => studio.commitProjectElements(...args)
  const persistPrefs = (...args) => studio.persistPrefs(...args)
  const applyStudioPrefs = (...args) => studio.applyStudioPrefs(...args)
  const newRevision = (...args) => studio.newRevision(...args)
  const initialProject = (...args) => studio.initialProject(...args)
  const persistLibraryDocument = (...args) => studio.persistLibraryDocument(...args)
  const requestLibraryDocument = (...args) => studio.requestLibraryDocument(...args)
  const updateTableElement = (...args) => studio.updateTableElement(...args)
  const tablePlainText = (...args) => studio.tablePlainText(...args)
  const hangingIndentTargetIndex = (...args) => studio.hangingIndentTargetIndex(...args)
  const focusedTextTargetIndex = (...args) => studio.focusedTextTargetIndex(...args)
  const replacePlainTextElement = (...args) => studio.replacePlainTextElement(...args)

  const openEasyTool = (title, fields, onConfirm, opener) => {
    easyToolDialog.querySelector('#easy-tool-title').textContent = title
    const form = easyToolDialog.querySelector('[data-easy-fields]')
    form.replaceChildren(...fields.map((field) => {
      const label = document.createElement('label')
      const caption = document.createElement('span')
      caption.textContent = field.label
      const input = field.type === 'textarea'
        ? document.createElement('textarea')
        : field.type === 'select'
          ? document.createElement('select')
          : document.createElement('input')
      if (field.type !== 'textarea' && field.type !== 'select') input.type = field.type || 'text'
      input.name = field.name
      if (field.type === 'select') {
        (field.options || []).forEach((option) => {
          const item = document.createElement('option')
          item.value = option.value
          item.textContent = option.label
          input.append(item)
        })
      }
      input.value = field.value || ''
      if (field.type === 'select' && !input.value && input.options.length) input.selectedIndex = 0
      label.append(caption, input)
      return label
    }))
    store.pendingEasyConfirm = onConfirm
    openDialog(easyToolDialog, opener)
  }

  const readEasyFields = () => Object.fromEntries(new FormData(easyToolDialog.querySelector('[data-easy-fields]')))

  const handleEasyAction = (action, control) => {
    const tools = easyTools()
    if (!tools) return announce('작성 도구를 불러오지 못했습니다.')
    if (action === 'insert-date') return insertPlainText(tools.formatOfficialDate(new Date()), '오늘 날짜를 넣었습니다.')
    if (action === 'insert-date-range') {
      const today = new Date()
      const start = new Date(today.getFullYear(), today.getMonth(), 1)
      return openEasyTool('기간 넣기', [
        { name: 'start', label: '시작일', type: 'date', value: tools.localISODate(start) },
        { name: 'end', label: '종료일', type: 'date', value: tools.localISODate(today) },
      ], (fields) => {
        const text = tools.formatOfficialDateRange(fields.start, fields.end)
        if (!text) return announce('종료일은 시작일 이후여야 합니다.')
        insertPlainText(text, '기간을 넣었습니다.')
      }, control)
    }
    if (action === 'insert-currency') {
      const selected = document.getSelection()?.toString() || ''
      return openEasyTool('금액 → 한글', [
        { name: 'amount', label: '금액', type: 'text', value: tools.extractAmountFromText(selected) || '12500000' },
      ], (fields) => {
        const text = tools.numberToKoreanCurrency(fields.amount)
        if (!text) return announce('숫자 금액을 입력하세요.')
        insertPlainText(text, '한글 금액을 넣었습니다.')
      }, control)
    }
    if (action === 'normalize-markers') {
      const elements = liveElements()
      const index = focusedTextTargetIndex(elements)
      if (index < 0) return announce('정리할 문장을 먼저 선택하세요.')
      const text = tools.normalizeOfficialMarkers(elements[index].text || '')
      if (text === elements[index].text) return announce('선택한 문장에 변경할 표기가 없습니다.')
      elements[index] = replacePlainTextElement(elements[index], text)
      return commitProjectElements(elements, 'easy-markers', 'ㅁ/ㅇ/ㆍ 표기를 □/○/- 로 정리했습니다.')
    }
    if (action === 'apply-official-block') {
      const elements = liveElements()
      const index = focusedTextTargetIndex(elements)
      if (index < 0) return announce('블록을 적용할 문장을 먼저 선택하세요.')
      const text = tools.applyOfficialBlock(elements[index].text || '')
      if (text === elements[index].text) return announce('선택한 문장에 변경할 블록 명령이 없습니다.')
      elements[index] = replacePlainTextElement(elements[index], text)
      return commitProjectElements(elements, 'easy-block', '범피스 블록 표기를 적용했습니다.')
    }
    if (action === 'apply-marker') {
      const marker = control && control.getAttribute('data-easy-marker')
      const elements = liveElements()
      const index = focusedTextTargetIndex(elements)
      if (index < 0) return announce('적용할 문장을 먼저 선택하세요.')
      const text = tools.applyOfficialMarker(elements[index].text || '', marker)
      if (text === elements[index].text) return announce('선택한 문장에 적용할 글머리가 없습니다.')
      elements[index] = replacePlainTextElement(elements[index], text)
      return commitProjectElements(elements, 'easy-marker', '글머리를 적용했습니다.')
    }
    if (action === 'wrap-bracket') {
      const kind = control && control.getAttribute('data-easy-bracket')
      const elements = liveElements()
      const index = focusedTextTargetIndex(elements)
      if (index < 0) return announce('묶을 문장을 먼저 선택하세요.')
      const text = tools.wrapOfficialBracket(elements[index].text || '', kind)
      if (!text || text === elements[index].text) return announce('선택한 문장에 적용할 따옴표가 없습니다.')
      elements[index] = replacePlainTextElement(elements[index], text)
      return commitProjectElements(elements, 'easy-bracket', '따옴표를 적용했습니다.')
    }
    if (action === 'format-thousands') {
      const elements = liveElements()
      const index = focusedTextTargetIndex(elements)
      if (index < 0) return announce('숫자를 포함한 문장을 먼저 선택하세요.')
      const text = tools.formatThousandsInText(elements[index].text || '')
      if (text === elements[index].text) return announce('선택한 문장에 변경할 숫자가 없습니다.')
      elements[index] = replacePlainTextElement(elements[index], text)
      return commitProjectElements(elements, 'easy-thousands', '세 자리 콤마를 넣었습니다.')
    }
    if (action === 'insert-end-mark') {
      return insertPlainText(tools.endMark(), '끝 표시를 넣었습니다.')
    }
    if (action === 'insert-attachment') {
      return openEasyTool('붙임 넣기', [
        { name: 'title', label: '붙임 문서명', type: 'text', value: '자료' },
        { name: 'copies', label: '부수', type: 'text', value: '1' },
      ], (fields) => {
        insertPlainText(tools.attachmentLine(fields.title, fields.copies), '붙임을 넣었습니다.')
      }, control)
    }
    if (action === 'insert-report-structure') {
      const items = tools.reportStructure(control && control.getAttribute('data-easy-report'))
      if (!items.length) return announce('지원하는 보고서 골격을 선택하세요.')
      const elements = liveElements()
      const index = elements.findIndex((element) => element.elementID === store.focusedEditorElementID)
      if (index < 0) return announce('보고서 골격을 넣을 위치를 먼저 선택하세요.')
      const inserted = items.map((item) => ({
        elementID: `element-report-${crypto.randomUUID()}`,
        kind: item.kind,
        order: 0,
        text: item.text,
        contentHTML: item.text,
        inlineIDs: [],
        styleID: item.styleID,
        evidenceIDs: [],
      }))
      elements.splice(index + 1, 0, ...inserted)
      return commitProjectElements(elements, 'easy-report-structure', '공문서 보고서 골격을 넣었습니다.')
    }
    if (action === 'insert-my-form') {
      const form = store.studioPrefs.myForms.find((item) => item.id === document.querySelector('[data-easy="my-form"]').value)
      if (!form) return announce('먼저 내 양식을 저장하세요.')
      return insertPlainText(form.text, `${form.name} 양식을 넣었습니다.`)
    }
    if (action === 'save-my-form') {
      const focused = liveElements().find((element) => element.elementID === store.focusedEditorElementID)
      return openEasyTool('내 양식 저장', [
        { name: 'name', label: '양식 이름', type: 'text', value: '자주 쓰는 문장' },
        { name: 'text', label: '넣을 내용', type: 'textarea', value: focused?.text || '○ ' },
      ], (fields) => {
        const form = { id: `form-${crypto.randomUUID()}`, name: fields.name, text: fields.text }
        const next = { ...store.studioPrefs, myForms: [...store.studioPrefs.myForms, form] }
        persistPrefs(next)
        applyStudioPrefs(next)
        announce('내 양식을 저장했습니다. 서명 템플릿은 바꾸지 않습니다.')
      }, control)
    }
    if (action === 'save-library') {
      const snapshot = newRevision(store.currentProject || initialProject(), 'library-saved')
      if (snapshot !== store.currentProject) store.currentProject = snapshot
      return persistLibraryDocument(store.currentProject)
    }
    if (action === 'merge-library') {
      if (!store.libraryEntries.length) return announce('먼저 문서함에 보관하세요.')
      return openEasyTool('문서 취합', [
        { name: 'documentID', label: '문서함', type: 'select', options: store.libraryEntries.map((item) => ({ value: item.documentID, label: item.title })), value: store.libraryEntries[0].documentID },
        { name: 'heading', label: '취합 소제목', type: 'text', value: '취합' },
      ], (fields) => {
        store.pendingMergeHeading = fields.heading
        requestLibraryDocument(fields.documentID)
      }, control)
    }
    if (action === 'insert-table') {
      return openEasyTool('표 넣기', [
        { name: 'rows', label: '행', type: 'number', value: '2' },
        { name: 'cols', label: '열', type: 'number', value: '3' },
      ], (fields) => {
        const html = tools.setTableBorders(tools.createTableHTML(fields.rows, fields.cols), 'all')
        if (!html) return announce('표는 1~100행, 1~20열의 정수 범위로 입력하세요.')
        const elements = liveElements()
        const index = Math.max(elements.findIndex((element) => element.elementID === store.focusedEditorElementID), 0)
        elements.splice(index + 1, 0, {
          elementID: `element-table-${crypto.randomUUID()}`,
          kind: 'table',
          order: index + 1,
          text: tablePlainText(html),
          contentHTML: html,
          inlineIDs: [],
          styleID: 'style-table',
          evidenceIDs: [],
        })
        commitProjectElements(elements, 'easy-table', '표를 넣었습니다.')
      }, control)
    }
    if (action === 'add-table-row') return updateTableElement((html) => tools.addTableRow(html), '표 행을 추가했습니다.')
    if (action === 'clean-table') return updateTableElement((html) => tools.cleanPastedTable(html), '표 칸을 정리했습니다.')
    if (action === 'set-table-borders') return updateTableElement((html) => tools.setTableBorders(html, 'all'), '표 테두리를 적용했습니다.')
    if (action === 'set-table-fill') {
      return openEasyTool('셀 색', [
        { name: 'row', label: '행 번호', type: 'number', value: '1' },
        { name: 'col', label: '열 번호', type: 'number', value: '1' },
        { name: 'color', label: '색', type: 'color', value: '#fff4cc' },
      ], (fields) => updateTableElement(
        (html) => tools.setTableCellFill(html, Math.max(0, Number(fields.row) - 1), Math.max(0, Number(fields.col) - 1), fields.color),
        '셀 색을 넣었습니다.',
      ), control)
    }
    if (action === 'page-margins') {
      const margins = tools.pageMargins(control.dataset.easyMargin || 'normal')
      return commitProjectElements(liveElements(), 'easy-margins', '페이지 여백을 바꿨습니다.', { pageMargins: margins })
    }
    if (action === 'hanging-indent') {
      const elements = liveElements()
      const index = hangingIndentTargetIndex(elements)
      if (index < 0) return announce('내어쓸 문장을 먼저 선택하세요.')
      const text = tools.hangingIndent(elements[index].text)
      elements[index] = replacePlainTextElement(elements[index], text)
      return commitProjectElements(elements, 'easy-indent', '둘째 줄부터 맞춰 내어썼습니다.')
    }
    if (action === 'confirm-easy-tool') {
      const fields = readEasyFields()
      const confirm = store.pendingEasyConfirm
      store.pendingEasyConfirm = null
      closeDialog(easyToolDialog)
      return confirm?.(fields)
    }
  }

  document.querySelectorAll('.ribbon-tab[data-tab]').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.ribbon-tab[data-tab]').forEach((candidate) => {
        const selected = candidate === tab
        candidate.classList.toggle('active', selected)
        candidate.setAttribute('aria-selected', String(selected))
      })
      document.querySelectorAll('.ribbon[role="tabpanel"]').forEach((panel) => {
        panel.hidden = panel.id !== tab.getAttribute('aria-controls')
      })
      announce(`${tab.textContent.trim()} 도구를 열었습니다.`)
    })
  })

  document.querySelectorAll('[data-easy-action]').forEach((control) => {
    control.addEventListener('click', () => handleEasyAction(control.dataset.easyAction, control))
  })

  document.querySelectorAll('[data-action="close-easy-tool"]').forEach((button) => {
    button.addEventListener('click', () => {
      store.pendingEasyConfirm = null
      closeDialog(easyToolDialog)
    })
  })

  editor.addEventListener('paste', (event) => {
    const tools = easyTools()
    const html = event.clipboardData?.getData('text/html') || ''
    if (!tools || !/<table/i.test(html)) return
    event.preventDefault()
    const cleaned = tools.setTableBorders(tools.cleanPastedTable(html), 'all')
    const elements = liveElements()
    const index = Math.max(elements.findIndex((element) => element.elementID === store.focusedEditorElementID), 0)
    elements.splice(index + 1, 0, {
      elementID: `element-table-${crypto.randomUUID()}`,
      kind: 'table',
      order: index + 1,
      text: tablePlainText(cleaned),
      contentHTML: cleaned,
      inlineIDs: [],
      styleID: 'style-table',
      evidenceIDs: [],
    })
    commitProjectElements(elements, 'easy-table', '붙여넣은 표를 정리해 넣었습니다.')
  }, true)

  Object.assign(studio, {
    openEasyTool,
    readEasyFields,
    handleEasyAction
  })
}(window.PublicDocumentStudio))
