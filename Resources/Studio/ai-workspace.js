(function (studio) {
  const store = studio.state
  const { aiWorkspace, aiProposalReview, byokSettings, page } = studio.dom
  const announce = (...args) => studio.announce(...args)
  const openDialog = (...args) => studio.openDialog(...args)
  const closeDialog = (...args) => studio.closeDialog(...args)
  const newRevision = (...args) => studio.newRevision(...args)
  const initialProject = (...args) => studio.initialProject(...args)
  const projectBridge = (...args) => studio.projectBridge(...args)
  const aiRequestDetails = (...args) => studio.aiRequestDetails(...args)

  const selectedAIElementIDs = () => {
    const selection = document.getSelection()
    const anchor = selection?.anchorNode?.nodeType === Node.ELEMENT_NODE
      ? selection.anchorNode
      : selection?.anchorNode?.parentElement
    const target = anchor?.closest?.('[data-element-id]')
    if (target) return [target.dataset.elementId]
    return store.selectedEditorElementID ? [store.selectedEditorElementID] : []
  }

  const requestAIProposal = () => {
    if (!store.aiSettingsSnapshot.activeProvider) {
      announce('AI 제공자 설정에서 자격 증명을 먼저 저장하세요.')
      openDialog(byokSettings, document.querySelector('[data-ai-request]'))
      return
    }
    const consent = document.querySelector('[data-ai-consent]')
    if (!consent.checked) {
      announce('선택한 문서·제공자·엔드포인트·작업·전송 범위에 대한 동의가 필요합니다.')
      consent.focus()
      return
    }
    const details = aiRequestDetails()
    const selectedElementIDs = selectedAIElementIDs()
    if (details.payloadScope === 'selected-elements' && !selectedElementIDs.length) {
      announce('문서에서 AI에 전송할 요소를 먼저 선택하세요.')
      page.focus()
      return
    }
    window.clearTimeout(store.autosaveTimer)
    const requestProject = newRevision(store.currentProject || initialProject(), 'ai-request-snapshot')
    if (requestProject !== store.currentProject) store.currentProject = requestProject
    projectBridge('requestAIProposal', store.currentProject, {
      ...details, selectedElementIDs, consent: true,
    })
    announce('동의 범위를 확인하고 AI 제안을 요청했습니다. 문서는 변경되지 않았습니다.')
  }

  const diffLine = (prefix, text) => {
    const line = document.createElement('span')
    const words = text.trim().split(/\s+/)
    const tail = words.splice(Math.max(0, words.length - 2)).join(' ')
    line.append(document.createTextNode(`${prefix}: ${words.join(' ')}${words.length ? ' ' : ''}`))
    const keptTail = document.createElement('span')
    keptTail.className = 'ai-diff-tail'
    keptTail.textContent = tail
    line.append(keptTail)
    return line
  }

  const showAIProposal = (proposal) => {
    store.pendingAIProposal = proposal
    aiProposalReview.hidden = false
    aiProposalReview.querySelector('.ai-base-revision').textContent = '현재 저장본을 기준으로 변경 내용을 검토합니다.'
    aiProposalReview.querySelector('[data-ai-diff]').replaceChildren(...proposal.commands.map((command) => {
      const target = store.currentProject.elements.find((element) => element.elementID === command.targetElementID)
      const item = document.createElement('li')
      const choice = document.createElement('input')
      choice.type = 'checkbox'
      choice.checked = true
      choice.value = command.commandID
      const label = document.createElement('label')
      const targetName = document.createElement('strong')
      const persisted = proposal.diffs?.find((diff) => diff.commandID === command.commandID)
      const before = diffLine('변경 전', persisted?.before ?? target?.text ?? '')
      const after = diffLine('변경 후', persisted?.after ?? command.value)
      targetName.textContent = target?.text || '선택한 문서 항목'
      label.append(choice, targetName, before, after)
      item.append(label)
      return item
    }))
    if (typeof studio.renderStatuteWarnings === 'function') studio.renderStatuteWarnings(proposal)
    aiProposalReview.querySelector('[data-ai-approve-selected]').focus()
  }

  const applyAIProposal = () => {
    if (!store.pendingAIProposal || store.pendingAIProposal.baseRevisionID !== store.currentProject.currentRevisionID) {
      announce('현재 리비전과 다른 오래된 제안은 적용할 수 없습니다.')
      return
    }
    const selected = new Set(Array.from(aiProposalReview.querySelectorAll('input:checked')).map((input) => input.value))
    const commandIDs = store.pendingAIProposal.commands.filter((command) => selected.has(command.commandID)).map((command) => command.commandID)
    if (!commandIDs.length) {
      announce('적용할 수 있는 스키마 유효 변경을 하나 이상 선택하세요.')
      return
    }
    projectBridge('applyAIProposal', store.currentProject, { proposalID: store.pendingAIProposal.proposalID, commandIDs })
    announce('선택한 변경의 원자적 적용을 요청했습니다.')
  }

  document.querySelector('[data-action="open-ai"]').addEventListener('click', (event) => openDialog(aiWorkspace, event.currentTarget))
  document.querySelector('[data-action="close-ai"]').addEventListener('click', () => closeDialog(aiWorkspace))

  document.querySelectorAll('[data-ai-operation]').forEach((button) => {
    button.addEventListener('click', () => {
      store.selectedAIOperation = button.dataset.aiOperation
      document.querySelectorAll('[data-ai-operation]').forEach((candidate) => candidate.setAttribute('aria-pressed', String(candidate === button)))
      document.querySelector('[data-ai-consent]').checked = false
      announce(`${button.textContent.trim()} 작업을 선택했습니다.`)
    })
  })

  document.querySelector('[data-ai-request]').addEventListener('click', requestAIProposal)

  document.querySelector('[data-ai-approve-selected]').addEventListener('click', applyAIProposal)
  document.querySelector('[data-ai-reject]').addEventListener('click', () => {
    if (!store.pendingAIProposal) return
    projectBridge('rejectAIProposal', store.currentProject, { proposalID: store.pendingAIProposal.proposalID })
    announce('AI 제안 거절을 기록하고 있습니다.')
  })
  document.querySelector('[data-ai-revoke]').addEventListener('click', () => {
    projectBridge('revokeAIConsent', store.currentProject || initialProject(), aiRequestDetails())
    announce('AI 전송 동의를 철회하고 있습니다.')
  })

  document.querySelectorAll('[data-ai-payload-scope], [data-ai-free-form]').forEach((input) => {
    input.addEventListener('input', () => { document.querySelector('[data-ai-consent]').checked = false })
    input.addEventListener('change', () => { document.querySelector('[data-ai-consent]').checked = false })
  })

  Object.assign(studio, {
    selectedAIElementIDs,
    requestAIProposal,
    diffLine,
    showAIProposal,
    applyAIProposal
  })
}(window.PublicDocumentStudio))
