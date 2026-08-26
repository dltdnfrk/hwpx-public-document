(function (studio) {
  const store = studio.state
  const { aiProposalReview, batchExportProgress, byokSettings, aiWorkspace } = studio.dom
  const renderTemplateCatalog = (...args) => studio.renderTemplateCatalog(...args)
  const announce = (...args) => studio.announce(...args)
  const applyStudioPrefs = (...args) => studio.applyStudioPrefs(...args)
  const applyLibraryMerge = (...args) => studio.applyLibraryMerge(...args)
  const initialProject = (...args) => studio.initialProject(...args)
  const projectBridge = (...args) => studio.projectBridge(...args)
  const renderProject = (...args) => studio.renderProject(...args)
  const officialRuleWarning = (...args) => studio.officialRuleWarning(...args)
  const applyBridgeProject = (...args) => studio.applyBridgeProject(...args)
  const showInspection = (...args) => studio.showInspection(...args)
  const resetExportConsent = (...args) => studio.resetExportConsent(...args)
  const showExportResult = (...args) => studio.showExportResult(...args)
  const showBatchExportProgress = (...args) => studio.showBatchExportProgress(...args)
  const openDialog = (...args) => studio.openDialog(...args)
  const renderAISettings = (...args) => studio.renderAISettings(...args)
  const setBYOKStatus = (...args) => studio.setBYOKStatus(...args)
  const showAIProposal = (...args) => studio.showAIProposal(...args)

  window.projectStoreReceive = ({ event, payload }) => {
    if (event === 'templateCatalog') {
      store.currentOfficialRuleState = null
      renderTemplateCatalog(payload.project)
      return
    }
    if (event === 'templateCatalogCancelled') {
      announce('템플릿 카탈로그 업데이트를 취소했습니다.')
      return
    }
    if (event === 'studioPrefs') {
      applyStudioPrefs(payload.project)
      return
    }
    if (event === 'documentLibrary') {
      store.libraryEntries = payload.project?.entries || []
      return
    }
    if (event === 'libraryDocument') {
      applyLibraryMerge(payload.project)
      return
    }
    if (event === 'empty') {
      store.currentProject = initialProject()
      projectBridge('save', store.currentProject)
      return
    }
    if (['opened', 'recovered'].includes(event)) {
      store.pendingAIProposal = null
      aiProposalReview.hidden = true
      renderProject(payload.project, payload.officialRuleState)
      announce(officialRuleWarning(payload) || (event === 'recovered' ? '중단 전 자동저장 상태를 복구했습니다.' : '앱 프로젝트를 다시 열었습니다.'))
      return
    }
    if (event === 'saved') {
      if (!applyBridgeProject(payload.project, payload.officialRuleState)) return
      announce(officialRuleWarning(payload) || '앱 프로젝트에 저장했습니다.')
      return
    }
    if (event === 'autosaved') {
      if (payload.project && !applyBridgeProject(payload.project, payload.officialRuleState)) return
      announce(officialRuleWarning(payload) || '자동저장됨')
      return
    }
    if (event === 'officialRuleEnforced') {
      if (!applyBridgeProject(payload.project, payload.officialRuleState)) return
      announce(officialRuleWarning(payload) || '현재 서명 카탈로그의 공식 규칙을 내보내기 원본에 적용했습니다.')
      return
    }
    if (event === 'inspection') {
      showInspection(payload.project)
      return
    }
    if (event === 'exportCompleted') {
      resetExportConsent()
      showExportResult(payload.project)
      announce(`선택 형식 ${payload.project.publishedFormats.length}개를 검증 후 게시했습니다.`)
      return
    }
    if (event === 'exportCancelled') {
      resetExportConsent()
      announce('내보내기를 취소했습니다. 게시된 파일은 없습니다.')
      return
    }
    if (event === 'batchExportStarted') {
      store.activeBatchOperationID = payload.operationID
      store.activeBatchRetryOperationID = null
      batchExportProgress.querySelector('.batch-export-summary').textContent = '일괄 내보내기를 준비하고 있습니다.'
      batchExportProgress.querySelector('[data-action="close-batch-export-progress"]').disabled = true
      batchExportProgress.querySelector('[data-action="cancel-batch-export"]').hidden = false
      batchExportProgress.querySelector('[data-action="retry-batch-export"]').hidden = true
      if (!batchExportProgress.open) openDialog(batchExportProgress)
      announce('일괄 내보내기를 시작했습니다.')
      return
    }
    if (event === 'batchExportProgress' || event === 'batchExportCompleted') {
      if (event === 'batchExportCompleted') resetExportConsent()
      showBatchExportProgress(payload.project)
      announce(event === 'batchExportCompleted' ? '일괄 내보내기 결과를 기록했습니다.' : '문서별 형식 내보내기를 진행하고 있습니다.')
      return
    }
    if (event === 'batchExportRecovered') {
      showBatchExportProgress(payload.project, true)
      announce('중단된 일괄 내보내기 상태와 정리 결과를 복구했습니다.')
      return
    }
    if (event === 'batchExportFailed') {
      store.activeBatchRetryOperationID = store.activeBatchOperationID
      store.activeBatchOperationID = null
      batchExportProgress.querySelector('.batch-export-summary').textContent = `일괄 내보내기 실패 · ${payload.message}`
      batchExportProgress.querySelector('[data-action="close-batch-export-progress"]').disabled = false
      batchExportProgress.querySelector('[data-action="cancel-batch-export"]').disabled = true
      batchExportProgress.querySelector('[data-action="cancel-batch-export"]').hidden = true
      announce('일괄 내보내기가 실패했습니다. 진단을 확인한 뒤 새 작업으로 다시 시도하세요.')
      return
    }
    if (event === 'batchExportCancelling') {
      announce('현재 검증 단계를 마친 뒤 나머지 항목을 취소합니다.')
      return
    }
    if (event === 'batchExportCancelled') {
      resetExportConsent()
      announce('일괄 내보내기 선택을 취소했습니다.')
      return
    }
    if (event === 'aiProposal') {
      renderProject(payload.project, payload.officialRuleState)
      showAIProposal(payload.project.aiProposalHistory.at(-1))
      announce('AI 제안을 받았습니다. 변경 전·후를 검토한 뒤 승인할 항목을 선택하세요.')
      return
    }
    if (event === 'aiProviderUnavailable') {
      renderProject(payload.project, payload.officialRuleState)
      announce('선택한 AI 제공자 자격 증명이 구성되지 않았습니다. 오프라인 편집과 내보내기는 계속 사용할 수 있습니다.')
      return
    }
    if (event === 'aiSettingsLoaded') {
      renderAISettings(payload.settings)
      return
    }
    if (event === 'aiSettingsUnavailable') {
      renderAISettings({ activeProvider: null, providers: [], catalog: [] })
      announce(payload.message || 'AI 설정을 불러오지 못했지만 문서 기능은 계속 사용할 수 있습니다.')
      return
    }
    if (event === 'aiSettingsSaved') {
      renderAISettings(payload.settings, 'saved')
      document.querySelector('[data-byok-secret]').value = ''
      document.querySelector('[data-ai-consent]').checked = false
      announce('제공자 자격 증명을 macOS 키체인에 저장했습니다.')
      return
    }
    if (event === 'aiSettingsTested') {
      renderAISettings(payload.settings, 'tested')
      announce('AI 제공자 연결을 확인했습니다.')
      return
    }
    if (event === 'aiSettingsDeleted') {
      renderAISettings(payload.settings, 'deleted')
      document.querySelector('[data-byok-secret]').value = ''
      document.querySelector('[data-ai-consent]').checked = false
      announce('AI 제공자 자격 증명을 삭제했습니다.')
      return
    }
    if (event === 'aiConsentRevoked') {
      renderProject(payload.project, payload.officialRuleState)
      document.querySelector('[data-ai-consent]').checked = false
      announce('이 요청 범위의 AI 전송 동의를 철회했습니다.')
      return
    }
    if (event === 'aiProposalApplied') {
      renderProject(payload.project, payload.officialRuleState)
      store.pendingAIProposal = null
      aiProposalReview.hidden = true
      announce('선택한 AI 제안을 하나의 새 리비전으로 적용했습니다.')
      aiWorkspace.querySelector('[data-ai-request]').focus()
      return
    }
    if (event === 'aiProposalRejected') {
      renderProject(payload.project, payload.officialRuleState)
      store.pendingAIProposal = null
      aiProposalReview.hidden = true
      announce('AI 제안을 거절하고 기록에 보존했습니다.')
      aiWorkspace.querySelector('[data-ai-request]').focus()
      return
    }
    if (event === 'error' && byokSettings.open) {
      setBYOKStatus('test-failed', payload.message || 'AI 제공자 작업에 실패했습니다.')
    }
    announce(payload.message || '프로젝트 작업을 완료하지 못했습니다.')
  }

  studio.projectStoreReceive = window.projectStoreReceive
}(window.PublicDocumentStudio))
