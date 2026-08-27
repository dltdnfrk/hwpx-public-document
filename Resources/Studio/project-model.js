(function (studio) {
  const store = studio.state
  const { titleInput, editor, page } = studio.dom
  const revisionTimestamp = (...args) => studio.revisionTimestamp(...args)
  const officialTitleFor = (...args) => studio.officialTitleFor(...args)
  const fallbackProjectElements = (...args) => studio.fallbackProjectElements(...args)
  const projectElements = (...args) => studio.projectElements(...args)
  const isTitleElement = (...args) => studio.isTitleElement(...args)

  const newRevision = (project, kind) => {
    const revisionID = `revision-${crypto.randomUUID()}`
    const createdAt = revisionTimestamp()
    const title = titleInput.value.trim() || '[확인 필요]'
    const elements = (projectElements() || []).map((element) => (
      isTitleElement(element) ? { ...element, text: title, contentHTML: title } : element
    ))
    if (!elements.length) return project
    return {
      ...project,
      title,
      currentRevisionID: revisionID,
      elements,
      revisions: [...project.revisions, {
        revisionID,
        parentRevisionID: project.currentRevisionID,
        createdAt,
        summary: kind,
        elementIDs: elements.map((element) => element.elementID),
        snapshotElements: elements,
      }],
      history: [...project.history, {
        eventID: `history-${crypto.randomUUID()}`,
        kind,
        revisionID,
        createdAt,
      }],
    }
  }

  const initialProject = () => {
    const documentID = `document-${crypto.randomUUID()}`
    const revisionID = `revision-${crypto.randomUUID()}`
    const createdAt = revisionTimestamp()
    const plan = store.currentTemplateCatalog?.entries.find((entry) => entry.templateID === 'public-plan')
    const title = plan ? officialTitleFor(plan) : '추진계획서'
    const elements = plan ? elementsFromTemplate(plan, title) : fallbackProjectElements()
    titleInput.value = title
    return {
      schemaVersion: 1,
      documentID,
      locale: 'ko-KR',
      title,
      currentRevisionID: revisionID,
      elements,
      assets: [],
      styles: officialProjectStyles(),
      templateBinding: {
        templateID: 'public-plan',
        version: plan?.version || '3.2',
        publishingAuthority: plan?.publishingAuthority || '기관 표준',
        requiredSections: plan?.requiredSections || ['개요', '추진 배경', '세부 추진계획', '예산 및 일정', '검토 및 결재'],
        checklistResults: plan
          ? Object.fromEntries((plan.checklist || []).map((item) => [item, false]))
          : { '목적과 대상': true, '추진 근거': true, '담당 부서': true, '시행 일정': true, '소요 예산': false, '결재선': false },
      },
      evidenceLinks: [],
      revisions: [{ revisionID, createdAt, summary: 'created', elementIDs: elements.map((element) => element.elementID) }],
      history: [{ eventID: `history-${crypto.randomUUID()}`, kind: 'created', revisionID, createdAt }],
      aiProposalHistory: [],
      providerConfigurations: [],
      consentGrants: [],
      redoRevisionIDs: [],
    }
  }

  const officialProjectStyles = () => ([
    { styleID: 'style-title', name: '문서 제목', properties: { level: '1', preset: 'title', font: '헤드라인', macFont: 'Apple SD Gothic Neo', pointSize: '16', align: 'center' } },
    { styleID: 'style-section-heading', name: '□ 소제목', properties: { level: '2', preset: 'section-heading', font: '헤드라인', macFont: 'Apple SD Gothic Neo', pointSize: '16', marker: '□ ' } },
    { styleID: 'style-body', name: '○ 주요내용', properties: { preset: 'body', font: '휴먼명조', macFont: 'AppleMyungjo', pointSize: '15', marker: '○' } },
    { styleID: 'style-body-detail', name: '- 세부내용', properties: { preset: 'body-detail', font: '휴먼명조', macFont: 'AppleMyungjo', pointSize: '15', marker: '-' } },
    { styleID: 'style-reference-note', name: '※ 참고내용', properties: { preset: 'reference', font: '맑은고딕', macFont: 'Apple SD Gothic Neo', pointSize: '12', marker: '※' } },
    { styleID: 'style-annotation', name: '* 주석내용', properties: { preset: 'annotation', font: '맑은고딕', macFont: 'Apple SD Gothic Neo', pointSize: '12', marker: '*' } },
    { styleID: 'style-reference', name: '참고 글상자', properties: { preset: 'reference-box', font: '맑은고딕', macFont: 'Apple SD Gothic Neo', pointSize: '12' } },
    { styleID: 'style-table', name: '표', properties: { preset: 'public-table' } },
    { styleID: 'style-metadata', name: '문서 정보', properties: { preset: 'metadata' } },
    { styleID: 'style-review', name: '확인 필요', properties: { preset: 'review-required' } },
  ])

  const elementsFromTemplate = (entry, title) => {
    const documentTitle = title || entry.documentType
    const elements = [{
      elementID: 'element-title',
      kind: 'heading',
      order: 0,
      text: documentTitle,
      styleID: 'style-title',
      evidenceIDs: [],
    }]
    entry.requiredSections.forEach((section, index) => {
      const slug = `section-${index + 1}`
      elements.push({
        elementID: `element-${slug}-heading`,
        kind: 'heading',
        order: elements.length,
        text: entry.templateID === 'public-draft' ? `${index + 1}. ${section}` : `□ ${section}`,
        styleID: 'style-section-heading',
        evidenceIDs: [],
      })
      elements.push({
        elementID: `element-${slug}-body`,
        kind: 'paragraph',
        order: elements.length,
        text: entry.templateID === 'public-draft' ? `가. ${section}` : `○ ${section}`,
        styleID: 'style-body',
        evidenceIDs: [],
      })
    })
    return elements
  }

  const applyPageMarginStyles = (margins) => {
    const box = margins || { top: 20, right: 20, bottom: 20, left: 20 }
    const targets = [document.documentElement, editor, page].filter(Boolean)
    targets.forEach((target) => {
      target.style.setProperty('--easy-page-pad-top', `${box.top}mm`)
      target.style.setProperty('--easy-page-pad-right', `${box.right}mm`)
      target.style.setProperty('--easy-page-pad-bottom', `${box.bottom}mm`)
      target.style.setProperty('--easy-page-pad-left', `${box.left}mm`)
    })
  }

  Object.assign(studio, {
    newRevision,
    initialProject,
    officialProjectStyles,
    elementsFromTemplate,
    applyPageMarginStyles
  })
}(window.PublicDocumentStudio))
