(function (studio) {
  const store = studio.state
  const { exportResult, exportSetup, exportConsent, batchExportProgress, inspector } = studio.dom
  const openDialog = (...args) => studio.openDialog(...args)
  const closeDialog = (...args) => studio.closeDialog(...args)
  const resetExportConsent = (...args) => studio.resetExportConsent(...args)
  const announce = (...args) => studio.announce(...args)
  const newRevision = (...args) => studio.newRevision(...args)
  const initialProject = (...args) => studio.initialProject(...args)
  const projectBridge = (...args) => studio.projectBridge(...args)

  const showExportResult = (receipt) => {
    const selected = new Set(store.activeExportFormats)
    const inRequest = (item) => selected.size === 0 || selected.has(item.format)
    const publishedFormats = receipt.publishedFormats.filter((format) => selected.size === 0 || selected.has(format))
    const blockedFormats = receipt.blockedFormats.filter((format) => selected.size === 0 || selected.has(format))
    const results = receipt.results.filter(inRequest)
    const lossReports = receipt.lossReports.filter(inRequest)
    const runtimeFailures = (receipt.runtimeFailures || receipt.failures || []).filter(inRequest)
    const failedFormats = (receipt.failedFormats || []).filter((format) => selected.size === 0 || selected.has(format))
    store.activeExportFormats = []
    const published = publishedFormats.length
    const blocked = blockedFormats.length
    const failed = Array.isArray(receipt.failedFormats)
      ? failedFormats.length
      : runtimeFailures.length || results.filter((result) => result.runtimeFailure || result.failure).length
    const valueOrBlocked = (value, label) => value ? String(value) : `${label} 미제공(안전하게 확인 필요)`
    exportResult.querySelector('.export-summary').textContent = `게시 완료 ${published}개 · 차단 ${blocked}개 · 실패 ${failed}개 · 현재 저장본 기준`
    exportResult.querySelector('.export-results').replaceChildren(...results.map((result) => {
      const item = document.createElement('li')
      const failure = result.runtimeFailure || result.failure
      item.textContent = failure
        ? `${valueOrBlocked(result.format, '형식')} · 실행 실패 · ${valueOrBlocked(failure.message || failure.reason, '실패 사유')}`
        : `${valueOrBlocked(result.format, '형식')} · ${valueOrBlocked(result.fileName, '파일명')} · 구조 및 의미 검증 통과`
      if (!failure && result.downloadURL) {
        const link = document.createElement('a')
        link.href = result.downloadURL
        link.textContent = '내려받기'
        link.setAttribute('download', result.fileName || '')
        item.append(' · ', link)
      }
      return item
    }))
    const reports = [...lossReports, ...runtimeFailures.map((failure) => ({
      ...failure,
      classification: 'runtime-failure',
      fallback: failure.fallback || failure.message || failure.reason,
    }))]
    exportResult.querySelector('.loss-report ul').replaceChildren(...reports.map((report) => {
      const item = document.createElement('li')
      const disposition = report.classification === 'semantic-loss'
        ? '형식 차단'
        : report.classification === 'runtime-failure' ? '실행 실패' : '동의 후 시각 변환'
      const location = document.createElement('strong')
      location.className = 'loss-location'
      location.textContent = [
        valueOrBlocked(report.format, '형식'),
        `분류 ${valueOrBlocked(report.classification, '분류')}`,
        disposition,
        `요소 ID ${valueOrBlocked(report.elementID, '요소 ID')}`,
        `요소 경로 ${valueOrBlocked(report.elementPath, '요소 경로')}`,
        `기능 ${valueOrBlocked(report.capability, '기능')}`,
      ].join(' · ')
      const fallback = document.createElement('span')
      fallback.textContent = `대체: ${valueOrBlocked(report.fallback, '대체 방법')}`
      item.append(location, fallback)
      return item
    }))
    openDialog(exportResult)
  }

  const showBatchExportProgress = (manifest, recovered = false) => {
    const stateLabels = {
      queued: '대기',
      exporting: '내보내는 중',
      validated: '검증 완료',
      published: '게시 완료',
      failed: '실패',
      cancelled: '취소',
    }
    const completed = manifest.items.reduce((total, item) => total + item.progressCompleted, 0)
    const total = manifest.items.reduce((sum, item) => sum + item.progressTotal, 0)
    const published = manifest.items.filter((item) => item.state === 'published').length
    const failed = manifest.items.filter((item) => item.state === 'failed').length
    const cancelled = manifest.items.filter((item) => item.state === 'cancelled').length
    const cleanupLabel = manifest.cleanupState === 'clean' ? '정리 완료' : '정리 대기'
    batchExportProgress.querySelector('progress').value = completed
    batchExportProgress.querySelector('progress').max = Math.max(total, 1)
    batchExportProgress.querySelector('.batch-export-summary').textContent = recovered
      ? `중단 작업 복구 완료 · 게시 ${published} · 실패 ${failed} · ${cleanupLabel}`
      : `게시 ${published} · 실패 ${failed} · 취소 ${cancelled}`
    batchExportProgress.querySelector('.batch-export-items').replaceChildren(...manifest.items.map((item) => {
      const row = document.createElement('li')
      row.dataset.state = item.state
      const displayName = item.documentDisplayName || '문서 표시명 미제공(안전하게 확인 필요)'
      const documentID = item.documentID || '문서 ID 미제공(안전하게 확인 필요)'
      row.textContent = `${displayName} · ID ${documentID} · ${item.format.toUpperCase()} · ${stateLabels[item.state] || item.state} · ${item.progressCompleted}/${item.progressTotal}`
      return row
    }))
    const cancel = batchExportProgress.querySelector('[data-action="cancel-batch-export"]')
    const close = batchExportProgress.querySelector('[data-action="close-batch-export-progress"]')
    const retry = batchExportProgress.querySelector('[data-action="retry-batch-export"]')
    store.activeBatchOperationID = manifest.state === 'running' ? manifest.operationID : null
    retry.hidden = manifest.state === 'running' || !manifest.items.some((item) => item.state === 'failed' || item.state === 'cancelled')
    store.activeBatchRetryOperationID = retry.hidden ? null : manifest.operationID
    cancel.disabled = manifest.state !== 'running'
    cancel.hidden = manifest.state !== 'running'
    close.disabled = manifest.state === 'running'
    if (!batchExportProgress.open) openDialog(batchExportProgress)
  }

  document.querySelector('[data-action="close-inspector"]').addEventListener('click', () => closeDialog(inspector))
  document.querySelector('[data-action="close-export-result"]').addEventListener('click', () => closeDialog(exportResult))
  document.querySelector('[data-action="close-batch-export-progress"]').addEventListener('click', () => {
    if (!store.activeBatchOperationID) closeDialog(batchExportProgress)
  })
  batchExportProgress.addEventListener('cancel', (event) => {
    if (store.activeBatchOperationID) event.preventDefault()
  })
  document.querySelector('[data-action="cancel-batch-export"]').addEventListener('click', () => {
    projectBridge('cancelBatchExport')
  })
  document.querySelector('[data-action="retry-batch-export"]').addEventListener('click', () => {
    if (!store.activeBatchRetryOperationID) return
    projectBridge('retryBatchExport', null, { operationID: store.activeBatchRetryOperationID })
  })
  document.querySelector('[data-action="open-export"]').addEventListener('click', (event) => openDialog(exportSetup, event.currentTarget))
  document.querySelectorAll('[data-action="close-export-setup"]').forEach((button) => {
    button.addEventListener('click', () => {
      resetExportConsent()
      closeDialog(exportSetup)
    })
  })
  exportSetup.addEventListener('cancel', resetExportConsent)

  document.querySelector('[data-action="export"]').addEventListener('click', () => {
    const formats = Array.from(document.querySelectorAll('[name="export-format"]:checked')).map((input) => input.value)
    if (!formats.length) {
      announce('내보낼 형식을 하나 이상 선택하세요.')
      return
    }
    const flatteningConsent = exportConsent.checked
    resetExportConsent()
    const exportProject = newRevision(store.currentProject || initialProject(), 'export-snapshot')
    if (exportProject === store.currentProject) {
      announce('내보낼 문서 스냅샷을 만들지 못했습니다. 편집기 상태를 확인하세요.')
      return
    }
    store.currentProject = exportProject
    closeDialog(exportSetup)
    announce('내보내기를 준비하고 있습니다.')
    const details = {
      formats,
      flatteningConsent,
    }
    if (document.querySelector('[data-batch-export]').checked) {
      if (studio.isLocalWeb()) {
        announce('로컬 앱에서만')
        return
      }
      projectBridge('batchExport', store.currentProject, details)
    } else {
      store.activeExportFormats = [...formats]
      projectBridge('export', store.currentProject, details)
    }
  })

  Object.assign(studio, {
    showExportResult,
    showBatchExportProgress
  })
}(window.PublicDocumentStudio))
