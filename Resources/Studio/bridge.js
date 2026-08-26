(function (studio) {
  const store = studio.state
  const { statusMessage, exportSetup, exportConsent } = studio.dom
  const isLocalWeb = (...args) => studio.isLocalWeb(...args)
  const dialogOpeners = studio.dialogOpeners

  const bridgeBootstrapToken = new URLSearchParams(window.location.hash.slice(1)).get('bridge-bootstrap') || ''
  const bridgeSessionReady = isLocalWeb()
    ? fetch('/api/bootstrap', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: bridgeBootstrapToken }),
    }).then(async (response) => {
      if (!response.ok) throw new Error('로컬 Studio 세션을 시작할 수 없습니다.')
      const payload = await response.json()
      store.studioSession = payload.sessionToken || ''
      if (!store.studioSession) throw new Error('로컬 Studio 세션을 확인할 수 없습니다.')
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
    })
    : Promise.resolve()

  const announce = (message) => {
    statusMessage.textContent = message
  }

  const resetExportConsent = () => {
    exportConsent.checked = false
  }

  const openDialog = (dialog, opener = document.activeElement) => {
    if (dialog === exportSetup) resetExportConsent()
    if (opener instanceof HTMLElement) dialogOpeners.set(dialog, opener)
    if (!dialog.open) dialog.showModal()
  }

  const closeDialog = (dialog) => {
    dialog.close()
    const opener = dialogOpeners.get(dialog)
    if (opener?.isConnected && !opener.disabled) opener.focus()
  }

  const projectBridge = (action, project, details = {}) => {
    const message = project ? { action, project, ...details } : { action, ...details }
    if (window.webkit && window.webkit.messageHandlers.projectStore) {
      window.webkit.messageHandlers.projectStore.postMessage(message)
      return
    }
    bridgeSessionReady.then(() => fetch('/api/bridge', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-Public-Document-Session': store.studioSession,
        },
        body: JSON.stringify(message),
      })).then(async (response) => {
        const payload = await response.json()
        const events = Array.isArray(payload.events) ? payload.events : [payload]
        if (!response.ok && !events.length) {
          throw new Error(payload.message || '로컬 웹 저장소 요청이 실패했습니다.')
        }
        events.forEach((entry) => window.projectStoreReceive(entry))
      }).catch((error) => {
      announce(error.message || '로컬 웹 저장소에 연결하지 못했습니다.')
    })
  }

  Object.assign(studio, {
    announce,
    resetExportConsent,
    openDialog,
    closeDialog,
    projectBridge
  })
}(window.PublicDocumentStudio))
