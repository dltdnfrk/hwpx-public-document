(function (studio) {
  const store = studio.state
  const { byokSettings } = studio.dom
  const announce = (...args) => studio.announce(...args)
  const projectBridge = (...args) => studio.projectBridge(...args)
  const isLocalWeb = (...args) => studio.isLocalWeb(...args)
  const openDialog = (...args) => studio.openDialog(...args)
  const closeDialog = (...args) => studio.closeDialog(...args)

  const aiRequestDetails = () => {
    const active = store.aiSettingsSnapshot.providers.find((item) => item.provider === store.aiSettingsSnapshot.activeProvider)
    const payloadScope = document.querySelector('[data-ai-payload-scope]').value
    const instruction = document.querySelector('[data-ai-free-form]').value.trim()
    return {
      provider: active?.provider || '',
      payloadScope, instruction,
      operation: instruction ? 'free-form' : store.selectedAIOperation,
    }
  }

  const activeAISetting = () => (
    store.aiSettingsSnapshot.providers.find((item) => item.provider === store.aiSettingsSnapshot.activeProvider) || null
  )

  const providerPolicy = (provider) => (
    store.aiSettingsSnapshot.catalog.find((item) => item.provider === provider) || null
  )

  const setBYOKStatus = (state, message) => {
    const status = document.querySelector('[data-byok-status]')
    status.dataset.state = state
    status.textContent = message
  }

  const updateBYOKDestination = () => {
    const provider = document.querySelector('[data-byok-provider]').value
    const endpoint = document.querySelector('[data-byok-endpoint]').value.trim()
    const output = document.querySelector('[data-byok-destination]')
    try {
      const url = new URL(endpoint)
      const policy = providerPolicy(provider)
      const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
      if (policy?.endpointReadOnly) {
        output.textContent = `전송 대상: ${url.host} · HTTPS만 허용`
      } else if (url.protocol === 'https:') {
        output.textContent = `전송 대상: ${url.host} · 사용자 지정 HTTPS 호스트`
      } else if (url.protocol === 'http:' && loopback) {
        output.textContent = `전송 대상: ${url.host} · 사용자 지정 로컬 HTTP 호스트`
      } else {
        output.textContent = '허용되지 않는 전송 대상입니다.'
      }
    } catch {
      output.textContent = '전송 대상을 확인할 수 없습니다.'
    }
  }

  const applyProviderDefaults = (provider) => {
    const defaults = providerPolicy(provider)
    if (!defaults) return
    const endpoint = document.querySelector('[data-byok-endpoint]')
    const model = document.querySelector('[data-byok-model]')
    endpoint.value = defaults.endpointIdentity
    endpoint.readOnly = defaults.endpointReadOnly
    model.value = defaults.defaultModel
    document.querySelector('[data-byok-secret]').value = ''
    setBYOKStatus('draft', '자격 증명을 입력한 뒤 저장하세요.')
    updateBYOKDestination()
  }

  const renderAISettings = (snapshot, state = 'loaded') => {
    store.aiSettingsSnapshot = snapshot || { activeProvider: null, providers: [], catalog: [] }
    const active = activeAISetting()
    document.querySelector('[data-ai-active-provider]').textContent = active?.provider || '-'
    document.querySelector('[data-ai-active-endpoint]').textContent = active?.endpointIdentity || '-'
    document.querySelector('[data-ai-active-model]').textContent = active?.model || '-'
    document.querySelector('[data-ai-active-status]').textContent = active?.hasSecret
      ? `${active.provider} · 키체인 저장됨`
      : '저장된 제공자가 없습니다.'
    document.querySelector('[data-ai-request]').disabled = !active?.hasSecret
    const providerControl = document.querySelector('[data-byok-provider]')
    providerControl.replaceChildren(...store.aiSettingsSnapshot.catalog.map((policy) => {
      const option = document.createElement('option')
      option.value = policy.provider
      option.textContent = policy.displayName
      return option
    }))
    const selected = active?.provider || store.aiSettingsSnapshot.catalog[0]?.provider || ''
    providerControl.value = selected
    if (active) {
      document.querySelector('[data-byok-endpoint]').value = active.endpointIdentity
      document.querySelector('[data-byok-endpoint]').readOnly = providerPolicy(selected)?.endpointReadOnly ?? false
      document.querySelector('[data-byok-model]').value = active.model
    } else {
      applyProviderDefaults(selected)
    }
    const policyList = document.querySelector('[data-byok-policy-list]')
    policyList.replaceChildren(...store.aiSettingsSnapshot.catalog.map((policy) => {
      const item = document.createElement('li')
      const hosts = policy.endpointReadOnly
        ? policy.allowedHosts.join(', ')
        : '사용자 지정 HTTPS 또는 loopback HTTP'
      item.textContent = `${policy.displayName} · ${hosts}`
      return item
    }))
    const accounts = document.querySelector('[data-byok-accounts]')
    accounts.replaceChildren(...store.aiSettingsSnapshot.providers.map((item) => {
      const entry = document.createElement('li')
      const button = document.createElement('button')
      button.type = 'button'
      button.dataset.provider = item.provider
      button.setAttribute('aria-pressed', String(item.provider === store.aiSettingsSnapshot.activeProvider))
      button.textContent = `${item.provider} · ${item.hostDisclosure} · ${item.model}`
      button.addEventListener('click', () => {
        projectBridge('configureAISettings', null, {
          provider: item.provider,
          endpointIdentity: item.endpointIdentity,
          model: item.model,
        })
        document.querySelector('[data-ai-consent]').checked = false
      })
      entry.append(button)
      return entry
    }))
    document.querySelector('[data-byok-delete]').disabled = !active
    document.querySelector('[data-byok-test]').disabled = !active?.hasSecret
    if (state === 'saved') setBYOKStatus('saved', '자격 증명을 macOS 키체인에 저장했습니다.')
    else if (state === 'tested') setBYOKStatus('test-ok', '연결에 성공했습니다. 문서 대신 연결 확인용 테스트 요청만 전송했습니다.')
    else if (state === 'deleted') setBYOKStatus('deleted', '이 제공자의 자격 증명을 삭제했습니다.')
    else setBYOKStatus(active?.hasSecret ? 'saved' : 'unset', active?.hasSecret ? '자격 증명이 저장되어 있습니다.' : '저장된 제공자가 없습니다.')
    updateBYOKDestination()
  }

  document.querySelectorAll('[data-action="open-settings"]').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelector('[data-byok-host]').textContent = isLocalWeb()
        ? '로컬 웹 호스트입니다. 자격 증명은 세션 인증된 로컬 bridge를 통해 이 Mac의 키체인에 저장되며 디스크에는 기록하지 않습니다.'
        : '자격 증명은 이 Mac의 키체인에만 저장됩니다. 문서 파일에는 키가 들어가지 않습니다.'
      openDialog(byokSettings, button)
      projectBridge('loadAISettings')
    })
  })
  document.querySelectorAll('[data-action="close-settings"]').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelector('[data-byok-secret]').value = ''
      closeDialog(byokSettings)
    })
  })
  byokSettings.addEventListener('cancel', () => {
    document.querySelector('[data-byok-secret]').value = ''
  })
  document.querySelector('[data-byok-provider]').addEventListener('change', (event) => {
    applyProviderDefaults(event.target.value)
    document.querySelector('[data-ai-consent]').checked = false
  })
  document.querySelectorAll('[data-byok-endpoint], [data-byok-model]').forEach((input) => {
    input.addEventListener('input', () => {
      setBYOKStatus('draft', '설정을 저장하거나 연결을 확인하세요.')
      updateBYOKDestination()
      document.querySelector('[data-ai-consent]').checked = false
    })
  })
  document.querySelector('[data-byok-save]').addEventListener('click', () => {
    const provider = document.querySelector('[data-byok-provider]').value
    const endpointIdentity = document.querySelector('[data-byok-endpoint]').value.trim()
    const model = document.querySelector('[data-byok-model]').value.trim()
    const secretControl = document.querySelector('[data-byok-secret]')
    const secret = secretControl.value
    setBYOKStatus('saving', '키체인에 저장하는 중입니다.')
    projectBridge('configureAISettings', null, {
      provider, endpointIdentity, model,
      ...(secret ? { secret } : {}),
    })
    secretControl.value = ''
  })
  document.querySelector('[data-byok-test]').addEventListener('click', () => {
    setBYOKStatus('testing', '연결을 확인하는 중입니다. 문서 내용은 전송하지 않습니다.')
    projectBridge('testAISettings', null, { provider: document.querySelector('[data-byok-provider]').value })
  })
  document.querySelector('[data-byok-delete]').addEventListener('click', () => {
    projectBridge('deleteAISettings', null, { provider: document.querySelector('[data-byok-provider]').value })
  })

  Object.assign(studio, {
    aiRequestDetails,
    activeAISetting,
    providerPolicy,
    setBYOKStatus,
    updateBYOKDestination,
    applyProviderDefaults,
    renderAISettings
  })
}(window.PublicDocumentStudio))
