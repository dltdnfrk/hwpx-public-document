import { useCallback } from 'react'

export type StringKey = string
export type TFunc = (key: StringKey, params?: Readonly<Record<string, string | number>>) => string

const labels: Readonly<Record<string, string>> = {
  appNavTitle: '문서 개요',
  appNavNoHeadings: '제목이 없습니다',
  editorPageBreak: '페이지 나누기',
}

export const getLang = (): 'ko' => 'ko'
export const setModuleLang = (): void => undefined
export const t: TFunc = (key) => labels[key] ?? key
export const DATE_LOCALES = { ko: 'ko-KR' } as const

export function useI18n() {
  const translate = useCallback<TFunc>((key) => t(key), [])
  return { lang: 'ko' as const, t: translate, dateLocale: 'ko-KR' }
}
