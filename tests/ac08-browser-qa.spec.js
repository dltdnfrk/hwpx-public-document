import crypto from 'node:crypto'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const testDirectory = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(testDirectory, '..')
const harnessRoot = path.join(root, '.omo', 'ac08-browser')
const requireFromHarness = createRequire(path.join(harnessRoot, 'package.json'))
const { test, expect } = requireFromHarness('@playwright/test')
const AxeBuilder = requireFromHarness('@axe-core/playwright').default
const packageVersion = (name) => JSON.parse(
  fs.readFileSync(path.join(harnessRoot, 'node_modules', name, 'package.json'), 'utf8'),
).version
const playwrightVersion = packageVersion('@playwright/test')
const axeVersion = packageVersion('@axe-core/playwright')
const evidence = path.resolve(root, process.env.AC08_EVIDENCE_ROOT || path.join('output', 'playwright', 'ac08'))
const studioURL = process.env.STUDIO_URL || 'http://127.0.0.1:4173'
const axeResults = []

test.use({ channel: 'chrome' })

const capture = async (page, name) => {
  await page.screenshot({ path: path.join(evidence, `${name}.png`), fullPage: false })
}

const sha256 = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')

const hashArtifacts = (base, names) => Object.fromEntries(
  names.map((name) => [name, sha256(path.join(base, name))]),
)

const audit = async (page, state) => {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()
  axeResults.push({ state, url: result.url, violations: result.violations })
  expect(result.violations, `${state} has automated accessibility violations`).toEqual([])
}

const bootstrap = async (page) => {
  await page.addInitScript(() => {
    window.__bridgeMessages = []
    window.webkit = {
      messageHandlers: {
        projectStore: {
          postMessage(message) {
            window.__bridgeMessages.push(structuredClone(message))
          },
        },
      },
    }
  })
  await page.goto(studioURL)
  await page.getByRole('button', { name: '새 문서' }).click()
}

test.beforeAll(({ browser }) => {
  fs.mkdirSync(evidence, { recursive: true })

  const studioArtifacts = ['index.html', 'styles.css', 'app.js']
  const sourceStudio = path.join(root, 'Resources', 'Studio')
  const packagedApp = path.resolve(root, process.env.AC08_PACKAGED_APP || 'dist/PublicDocument.app')
  const packagedStudio = path.join(packagedApp, 'Contents', 'Resources', 'Studio')
  const packagedExecutable = path.join(packagedApp, 'Contents', 'MacOS', 'PublicDocumentApp')
  const sourceHashes = hashArtifacts(sourceStudio, studioArtifacts)
  const packagedStudioHashes = hashArtifacts(packagedStudio, studioArtifacts)

  fs.writeFileSync(
    path.join(evidence, 'browser-receipt.json'),
    `${JSON.stringify({
      schemaVersion: 1,
      recordedAt: new Date().toISOString(),
      target: {
        url: studioURL,
        servedRoot: 'Resources/Studio',
        evidenceRoot: path.relative(root, evidence),
        viewports: ['375x720', '768x720', '920x640', '1280x820'],
        axeStates: [
          'genoffice-editor',
          'main-editor',
          'ai-consent',
          'ai-proposal-review',
          'single-export-loss-consent',
          'single-export-result',
          'batch-export-progress',
          'project-inspection',
        ],
      },
      runtime: {
        node: process.version,
        chrome: browser.version(),
        playwright: playwrightVersion,
        axePlaywright: axeVersion,
      },
      testedSourceSHA256: sourceHashes,
      packagedStudioSHA256: packagedStudioHashes,
      packagedStudioMatchesTestedSource: Object.fromEntries(
        studioArtifacts.map((name) => [name, packagedStudioHashes[name] === sourceHashes[name]]),
      ),
      observedPreFinalPackage: {
        executable: path.relative(root, packagedExecutable),
        sha256: sha256(packagedExecutable),
        status: process.env.AC08_PACKAGED_APP
          ? 'AC08_PACKAGED_APP_BROWSER_TARGET'
          : 'PRE_FINAL_NOT_BROWSER_TARGET_AC10_REBIND_REQUIRED',
      },
    }, null, 2)}\n`,
  )
})

test('GenOffice editor drives stable project snapshots and Studio controls', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 820 })
  await bootstrap(page)

  const editor = page.locator('public-document-genoffice-editor')
  await expect(editor).toHaveAttribute('data-runtime', 'ready')
  await expect(editor).toBeVisible()
  const initialElements = await editor.evaluate((element) => element.getElements())
  const before = initialElements.map((entry) => entry.id)
  expect(before).toContain('element-title')
  expect(new Set(before).size).toBe(before.length)
  expect(initialElements.find((entry) => entry.id === 'element-evidence-marker').text).toContain('[확인 필요] 최근')
  const koreanPhraseLayout = await editor.evaluate((element) => {
    const paragraph = Array.from(element.shadowRoot.querySelectorAll('p')).find((node) => node.textContent.includes('높이고자'))
    const rectFor = (needle) => {
      const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT)
      let textNode
      while ((textNode = walker.nextNode())) {
        const offset = textNode.textContent.indexOf(needle)
        if (offset >= 0) {
          const range = document.createRange()
          range.setStart(textNode, offset)
          range.setEnd(textNode, offset + needle.length)
          return range.getBoundingClientRect().top
        }
      }
      return null
    }
    return { text: paragraph?.textContent, stemTop: rectFor('높이고자'), endingTop: rectFor('함.') }
  })
  expect(koreanPhraseLayout.text).toContain('높이고자\u00a0함.')
  expect(koreanPhraseLayout.stemTop).toBe(koreanPhraseLayout.endingTop)
  await page.getByRole('button', { name: /1\.?\s*개요/ }).click()

  await page.locator('[data-format="fontName"]').selectOption('serif')
  const fontSize = page.locator('[data-format="fontSize"]')
  await fontSize.selectOption('14')
  await expect(fontSize).toHaveValue('14')
  for (const name of ['굵게', '기울임', '밑줄', '왼쪽 맞춤', '가운데 맞춤', '글머리 기호']) {
    const control = page.getByRole('button', { name })
    await control.focus()
    await page.keyboard.press('Space')
    await expect(control).toBeEnabled()
    if (['굵게', '기울임', '밑줄'].includes(name)) {
      await expect(control).toHaveAttribute('aria-pressed', 'true')
      await page.keyboard.press('Space')
      await expect(control).toHaveAttribute('aria-pressed', 'false')
      await page.keyboard.press('Space')
      await expect(control).toHaveAttribute('aria-pressed', 'true')
    }
  }
  const marker = page.getByRole('button', { name: '확인 필요' })
  await marker.focus()
  await page.keyboard.press('Space')
  await expect(marker).toBeEnabled()
  await page.getByRole('button', { name: '저장' }).click()
  await expect.poll(() => page.evaluate(() => window.__bridgeMessages.at(-1)?.action)).toBe('save')
  const saved = await page.evaluate(() => window.__bridgeMessages.at(-1).project)
  expect(saved.elements.map((entry) => entry.elementID)).toEqual(before)
  const formattedHeading = saved.elements.find((entry) => entry.elementID === 'element-summary-heading')
  expect(formattedHeading).toMatchObject({ kind: 'list-item' })
  expect(formattedHeading.contentHTML).toContain('확인 필요')
  expect(formattedHeading.text).toContain('개요 [확인 필요]')
  expect(formattedHeading.text).not.toContain('개요[확인 필요]')
  expect(formattedHeading.contentHTML).toContain('<strong>')
  expect(formattedHeading.contentHTML).toContain('<em>')
  expect(formattedHeading.contentHTML).toContain('<u>')
  expect(formattedHeading.contentHTML).toContain('data-public-document-align="center"')
  expect(formattedHeading.contentHTML).toContain('font-size: 14pt')
  expect(formattedHeading.contentHTML).toContain('font-family: &quot;serif&quot;')

  await page.getByRole('button', { name: '내보내기', exact: true }).click()
  await page.getByRole('button', { name: '선택 형식 내보내기' }).click()
  await expect.poll(() => page.evaluate(() => window.__bridgeMessages.at(-1)?.action)).toBe('export')
  const exported = await page.evaluate(() => window.__bridgeMessages.at(-1).project)
  expect(exported.elements.map((entry) => entry.elementID)).toEqual(before)

  const inlineIDs = ['inline-alpha', 'inline-bravo', 'inline-charlie']
  const editedSummaryText = '첫 문장 강조 문장 기울임 문장\u00a0편집 [확인 필요]'
  const inlineFixture = await page.evaluate((ids) => {
    const project = structuredClone(window.__bridgeMessages.find((message) => message.action === 'save').project)
    const summary = project.elements.find((element) => element.elementID === 'element-summary-body')
    summary.contentHTML = `<span data-inline-id="${ids[0]}">첫 문장</span> <strong data-inline-id="${ids[1]}">강조 문장</strong> <em data-inline-id="${ids[2]}">기울임 문장</em>`
    summary.text = '첫 문장 강조 문장 기울임 문장'
    summary.inlineIDs = ids
    return project
  }, inlineIDs)
  const inlineAnchors = (html) => page.evaluate((contentHTML) => Array.from(
    new DOMParser().parseFromString(contentHTML, 'text/html').querySelectorAll('[data-inline-id]'),
    (node) => ({ id: node.dataset.inlineId, text: node.textContent }),
  ), html)
  const expectInlineAnchors = async (project) => {
    const summary = project.elements.find((element) => element.elementID === 'element-summary-body')
    const anchors = await inlineAnchors(summary.contentHTML)
    expect(summary.text).toBe(editedSummaryText)
    expect(summary.inlineIDs).toEqual(inlineIDs)
    expect(anchors.map((anchor) => anchor.id)).toEqual(inlineIDs)
    expect(anchors.map((anchor) => anchor.text)).toEqual(expect.arrayContaining(['첫 문장', '강조 문장', '기울임 문장']))
  }
  await page.evaluate((project) => window.projectStoreReceive({ event: 'opened', payload: { project } }), inlineFixture)
  await editor.evaluate((element) => element.focusElement('element-summary-body'))
  await page.getByRole('button', { name: '굵게' }).click()
  await page.locator('[data-format="fontName"]').selectOption('serif')
  expect(await editor.evaluate((element) => element.focusElement('element-summary-body', 'end'))).toBe(true)
  await page.keyboard.type(' 편집')
  await marker.focus()
  await page.keyboard.press('Space')
  await page.getByRole('button', { name: '저장' }).click()
  await expect.poll(() => page.evaluate(() => window.__bridgeMessages.at(-1)?.action)).toBe('save')
  const inlineSaved = await page.evaluate(() => window.__bridgeMessages.at(-1).project)
  await expectInlineAnchors(inlineSaved)

  await page.getByRole('button', { name: '내보내기', exact: true }).click()
  await page.getByRole('button', { name: '선택 형식 내보내기' }).click()
  await expect.poll(() => page.evaluate(() => window.__bridgeMessages.at(-1)?.action)).toBe('export')
  await expectInlineAnchors(await page.evaluate(() => window.__bridgeMessages.at(-1).project))
  await page.evaluate((project) => window.projectStoreReceive({ event: 'opened', payload: { project } }), inlineSaved)
  const reopened = await editor.evaluate((element) => element.getElements().find((entry) => entry.id === 'element-summary-body'))
  const reopenedAnchors = await inlineAnchors(reopened.contentHTML)
  expect(reopened.text).toBe(editedSummaryText)
  expect(reopenedAnchors.map((anchor) => anchor.id)).toEqual(inlineIDs)
  expect(reopenedAnchors.map((anchor) => anchor.text)).toEqual(expect.arrayContaining(['첫 문장', '강조 문장', '기울임 문장']))
  await audit(page, 'genoffice-editor')
  await capture(page, 'genoffice-editor-1280')
})

test('keyboard and screen-reader journeys remain complete', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 820 })
  await bootstrap(page)
  await audit(page, 'main-editor')
  await capture(page, 'studio-1280')
  fs.writeFileSync(
    path.join(evidence, 'aria-main.txt'),
    await page.locator('body').ariaSnapshot(),
  )

  const outlineToggle = page.getByRole('button', { name: '문서 구조' })
  await outlineToggle.focus()
  await page.keyboard.press('Enter')
  await expect(outlineToggle).toHaveAttribute('aria-pressed', 'false')
  await page.keyboard.press('Enter')
  await expect(outlineToggle).toHaveAttribute('aria-pressed', 'true')

  const summaryButton = page.getByRole('button', { name: /1\.?\s*개요/ })
  await summaryButton.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('public-document-genoffice-editor')).toBeFocused()
  await expect(summaryButton).toHaveAttribute('aria-current', 'location')

  const rules = page.getByText('공식 규칙 우선 적용')
  await rules.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.official-rules')).toHaveAttribute('open', '')
  await capture(page, 'template-rules-keyboard-1280')

  const check = page.getByRole('button', { name: '필수항목 점검' })
  await check.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('status').first()).toContainText('필수항목 6개 중 4개')

  const inspect = page.getByRole('button', { name: '프로젝트 검사' })
  await inspect.focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => page.evaluate(() => window.__bridgeMessages.at(-1)?.action)).toBe('inspect')
  await page.evaluate(() => {
    window.projectStoreReceive({
      event: 'inspection',
      payload: {
        project: {
          schemaVersion: '1.0', documentID: 'document-internal', currentRevisionID: 'revision-internal',
          elementCount: 15, assetCount: 0, styleCount: 4, evidenceLinkCount: 1, revisionCount: 2,
          historyEventCount: 2, templateID: 'template-internal', templateVersion: 'v3.2',
        },
      },
    })
  })
  const inspection = page.getByRole('dialog', { name: '프로젝트 검사' })
  await expect(inspection).toContainText('현재 문서')
  await expect(inspection).toContainText('현재 저장본')
  await expect(inspection).not.toContainText('document-internal')
  await expect(inspection).not.toContainText('revision-internal')
  await expect(inspection).not.toContainText('template-internal')
  await audit(page, 'project-inspection')
  await capture(page, 'project-inspection-1280')
  await page.getByRole('button', { name: '프로젝트 검사 닫기' }).focus()
  await page.keyboard.press('Enter')

  const aiOpen = page.getByRole('button', { name: 'AI 제안' })
  await aiOpen.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.ai-workspace')).toHaveAttribute('open', '')
  await audit(page, 'ai-consent')
  await capture(page, 'ai-consent-1280')

  const aiRequest = page.getByRole('button', { name: '제안 요청' })
  await aiRequest.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('[data-ai-consent]')).toBeFocused()
  const scope = page.locator('[data-ai-payload-scope]')
  await scope.focus()
  await scope.selectOption('whole-document')
  await expect(scope).toHaveValue('whole-document')
  const aiConsent = page.locator('[data-ai-consent]')
  await aiConsent.focus()
  await page.keyboard.press('Space')
  await expect(aiConsent).toBeChecked()
  await aiRequest.focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => page.evaluate(() => window.__bridgeMessages.at(-1)?.action)).toBe('requestAIProposal')

  const aiProposalProject = await page.evaluate(() => {
    const project = structuredClone(window.__bridgeMessages.find((message) => message.action === 'save').project)
    const proposal = {
      proposalID: 'proposal-ac08',
      baseRevisionID: project.currentRevisionID,
      state: 'pending',
      commands: [{
        commandID: 'command-ac08',
        targetElementID: 'element-summary-body',
        operation: 'replace-text',
        value: '시민이 체감하는 생활안전 수준을 높이기 위한 근거 기반 추진계획입니다.',
      }],
    }
    project.aiProposalHistory.push(proposal)
    window.projectStoreReceive({ event: 'aiProposal', payload: { project } })
    return project
  })
  await expect(page.getByRole('heading', { name: '적용 전 변경 검토' })).toBeVisible()
  await expect(page.getByRole('button', { name: '선택한 변경 승인' })).toBeFocused()
  await audit(page, 'ai-proposal-review')
  fs.writeFileSync(
    path.join(evidence, 'aria-ai-proposal.txt'),
    await page.locator('.ai-workspace').ariaSnapshot(),
  )
  await capture(page, 'ai-proposal-review-1280')
  const approve = page.getByRole('button', { name: '선택한 변경 승인' })
  await approve.focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => page.evaluate(() => window.__bridgeMessages.at(-1)?.action)).toBe('applyAIProposal')
  await page.evaluate((project) => window.projectStoreReceive({ event: 'aiProposalApplied', payload: { project } }), aiProposalProject)
  await expect(aiRequest).toBeFocused()

  await page.evaluate((project) => {
    const rejected = structuredClone(project)
    rejected.aiProposalHistory.push({
      proposalID: 'proposal-ac08-reject', baseRevisionID: rejected.currentRevisionID, state: 'pending',
      commands: [{ commandID: 'command-ac08-reject', targetElementID: 'element-summary-body', operation: 'replace-text', value: '거절 경로 확인' }],
    })
    window.projectStoreReceive({ event: 'aiProposal', payload: { project: rejected } })
  }, aiProposalProject)
  const reject = page.getByRole('button', { name: '제안 거절' })
  await reject.focus()
  await page.keyboard.press('Space')
  await expect.poll(() => page.evaluate(() => window.__bridgeMessages.at(-1)?.action)).toBe('rejectAIProposal')
  await page.evaluate((project) => window.projectStoreReceive({ event: 'aiProposalRejected', payload: { project } }), aiProposalProject)
  await expect(aiRequest).toBeFocused()
  await page.getByRole('button', { name: 'AI 제안 검토 닫기' }).focus()
  await page.keyboard.press('Enter')
  await expect(aiOpen).toBeFocused()

  const exportOpen = page.getByRole('button', { name: '내보내기', exact: true })
  await exportOpen.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.export-setup')).toHaveAttribute('open', '')
  const markdown = page.getByLabel('Markdown')
  await markdown.focus()
  await page.keyboard.press('Space')
  await expect(markdown).toBeChecked()
  const exportConsent = page.getByLabel('내보내기별 시각 변환 동의')
  await exportConsent.focus()
  await page.keyboard.press('Space')
  await expect(exportConsent).toBeChecked()
  await audit(page, 'single-export-loss-consent')
  await capture(page, 'single-export-loss-consent-1280')
  await page.getByRole('button', { name: '선택 형식 내보내기' }).focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => page.evaluate(() => window.__bridgeMessages.at(-1)?.action)).toBe('export')
  await page.evaluate(() => {
    const request = window.__bridgeMessages.at(-1)
    window.projectStoreReceive({
      event: 'exportCompleted',
      payload: {
        project: {
          publishedFormats: request.formats,
          blockedFormats: [],
          snapshotRevisionID: request.project.currentRevisionID,
          results: request.formats.map((format) => ({ format, fileName: `생활안전-계획.${format === 'markdown' ? 'md' : format}` })),
          lossReports: [{
            format: 'markdown',
            classification: 'visual-only-flattening',
            elementID: 'element-approval',
            elementPath: 'elements/3',
            capability: 'approval-grid',
            fallback: '결재선은 참조 가능한 표로 보존했습니다.',
          }],
          runtimeFailures: [{
            format: 'hwp',
            elementID: 'element-approval',
            elementPath: 'elements/3',
            capability: 'hwp-converter',
            reason: '변환 런타임을 시작하지 못했습니다.',
          }],
        },
      },
    })
  })
  await expect(page.getByRole('heading', { name: '손실 보고서' })).toBeVisible()
  await expect(page.locator('.export-summary')).toContainText('실패 1개')
  const lossReport = page.locator('.loss-report')
  await expect(lossReport).toContainText('요소 ID element-approval')
  await expect(lossReport).toContainText('요소 경로 elements/3')
  await expect(lossReport).toContainText('기능 approval-grid')
  await expect(lossReport).toContainText('실행 실패')
  await expect(lossReport).toContainText('hwp-converter')
  await audit(page, 'single-export-result')
  fs.writeFileSync(
    path.join(evidence, 'aria-loss-report.txt'),
    await page.locator('.export-result').ariaSnapshot(),
  )
  await capture(page, 'single-export-result-1280')
  await page.getByRole('button', { name: '내보내기 결과 닫기' }).focus()
  await page.keyboard.press('Enter')

  await exportOpen.focus()
  await page.keyboard.press('Enter')
  const batchExport = page.getByLabel('여러 문서 일괄 내보내기')
  await batchExport.focus()
  await page.keyboard.press('Space')
  await expect(batchExport).toBeChecked()
  await page.getByRole('button', { name: '선택 형식 내보내기' }).focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => page.evaluate(() => window.__bridgeMessages.at(-1)?.action)).toBe('batchExport')
  await page.evaluate(() => {
    window.projectStoreReceive({ event: 'batchExportStarted', payload: { operationID: 'batch-ac08' } })
    window.projectStoreReceive({
      event: 'batchExportProgress',
      payload: {
        project: {
          operationID: 'batch-ac08',
          state: 'running',
          cleanupState: 'clean',
          items: [
            { documentID: 'document-a', documentDisplayName: '생활안전 추진계획', format: 'hwpx', state: 'published', progressCompleted: 4, progressTotal: 4 },
            { documentID: 'document-b', documentDisplayName: '현장 점검 계획', format: 'docx', state: 'exporting', progressCompleted: 2, progressTotal: 4 },
          ],
        },
      },
    })
  })
  await expect(page.getByRole('button', { name: '일괄 내보내기 취소' })).toBeEnabled()
  const batchItems = page.locator('.batch-export-items')
  await expect(batchItems).toContainText('생활안전 추진계획 · ID document-a · HWPX')
  await expect(batchItems).toContainText('현장 점검 계획 · ID document-b · DOCX')
  await expect(batchItems).not.toContainText('문서 1')
  await audit(page, 'batch-export-progress')
  fs.writeFileSync(
    path.join(evidence, 'aria-batch-progress.txt'),
    await page.locator('.batch-export-progress').ariaSnapshot(),
  )
  await capture(page, 'batch-export-progress-1280')
  fs.writeFileSync(path.join(evidence, 'keyboard-receipt.json'), `${JSON.stringify({
    schemaVersion: 1,
    journeys: [
      'guided-authoring', 'AI-proposal-review', 'AI-consent',
      'official-rule-and-template-guidance', 'loss-resolution', 'single-export', 'batch-export',
    ].map((name) => ({ name, status: 'PASS', criticalActivationInputSource: 'keyboard' })),
    programmaticStates: {
      outlineCurrent: { attribute: 'aria-current', passed: true },
      formatToggles: { attribute: 'aria-pressed', commands: ['bold', 'italic', 'underline'], onAndOffObserved: true, passed: true },
    },
    focusTransitions: {
      aiProposalApproved: { target: '제안 요청', activeElementMatched: true },
      aiProposalRejected: { target: '제안 요청', activeElementMatched: true },
    },
    inlineIdentity: { saveExportReopenExact: true },
    testSource: { path: 'tests/ac08-browser-qa.spec.js', sha256: sha256(path.join(root, 'tests/ac08-browser-qa.spec.js')) },
  }, null, 2)}\n`)
  fs.writeFileSync(path.join(evidence, 'axe-states.json'), `${JSON.stringify(axeResults, null, 2)}\n`)
})

for (const width of [375, 768, 920, 1280]) {
  test(`visual contract at ${width}px`, async ({ page }) => {
    const height = width === 920 ? 640 : width < 920 ? 720 : 820
    await page.setViewportSize({ width, height })
    await bootstrap(page)
    await capture(page, `studio-${width}`)
    await expect(page.locator('.studio-shell')).toHaveCSS('min-width', '920px')
    await expect(page.getByRole('heading', { name: '2026년 생활안전 추진계획', level: 1 })).toBeVisible()
  })
}
