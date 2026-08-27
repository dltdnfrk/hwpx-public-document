(function (studio) {
  const verifiedStatuteCitations = [
    '행정업무의 운영 및 혁신에 관한 규정 제5조②',
    '행정업무의 운영 및 혁신에 관한 규정 제7조⑥',
    '행정업무의 운영 및 혁신에 관한 규정 제8조②',
    '행정업무의 운영 및 혁신에 관한 규정 제13조',
    '행정업무의 운영 및 혁신에 관한 규정 시행규칙 제2조①',
    '행정업무의 운영 및 혁신에 관한 규정 시행규칙 제3조',
    '행정업무의 운영 및 혁신에 관한 규정 시행규칙 제4조④',
    '행정업무의 운영 및 혁신에 관한 규정 시행규칙 제4조⑤',
  ]
  const statutePattern = /행정업무의 운영 및 혁신에 관한 규정(?: 시행규칙)? 제\d+조[①②③④⑤⑥⑦⑧⑨⑩]?|공공문서 작성 지침 제\d+조|편람 제\d+조|제\d+조[①②③④⑤⑥⑦⑧⑨⑩]?/g

  const reviewStatuteCitations = (values) => {
    const seen = new Map()
    values.forEach((value) => {
      const matches = String(value || '').match(statutePattern) || []
      matches.forEach((citation) => {
        const verified = verifiedStatuteCitations.includes(citation)
        seen.set(citation, {
          citation,
          verified,
          label: verified ? '확인됨' : '법령 인용 미확인',
        })
      })
    })
    return Array.from(seen.values())
  }

  const renderStatuteWarnings = (proposal) => {
    const box = document.querySelector('[data-ai-proposal-review] [data-statute-warnings]')
    if (!box) return []
    const values = [
      ...(proposal?.commands || []).map((command) => command.value),
      ...(proposal?.diffs || []).map((diff) => diff.after),
      ...(proposal?.diffs || []).map((diff) => diff.before),
    ]
    const reviews = reviewStatuteCitations(values)
    box.replaceChildren(...reviews.map((item) => {
      const row = document.createElement('li')
      row.dataset.statuteVerified = String(item.verified)
      row.textContent = `${item.label} · ${item.citation}`
      return row
    }))
    box.hidden = reviews.length === 0
    return reviews
  }

  Object.assign(studio, {
    verifiedStatuteCitations,
    reviewStatuteCitations,
    renderStatuteWarnings,
  })
}(window.PublicDocumentStudio))
