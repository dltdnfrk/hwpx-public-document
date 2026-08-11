export const CHART_MAX_WIDTH_PX = 640
const textSpec = (value: unknown) => ['span', {}, typeof value === 'string' ? value : '']
export const drawChartSvg = (): void => undefined
export const renderChartSpec = (value: unknown) => textSpec(value)
export const renderFieldSpec = (value: unknown) => textSpec(value)
export const renderFormulaSpec = (value: unknown) => textSpec(value)
export const renderTableSpec = (value: unknown) => textSpec(value)
export const renderTextboxSpec = (value: unknown) => textSpec(value)
export const textboxBoxStyle = (): string => ''
export const wireChartEditing = (): null => null
