const integerFormatter = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 0,
})

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  hour12: false,
})

export function formatMoney(value: string): string {
  const match = /^([+-]?)(\d+)(?:\.(\d*))?$/.exec(value.trim())
  if (match === null) return `¥${value}`

  const sign = match[1] ?? ''
  const whole = match[2] ?? '0'
  const fraction = match[3] ?? ''
  const exactFraction = fraction.length >= 8 ? fraction : fraction.padEnd(8, '0')
  return `¥${sign}${whole}.${exactFraction}`
}

export function formatInteger(value: number): string {
  return integerFormatter.format(value)
}

export function formatDateTime(value: string | null): string {
  if (value === null) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : dateTimeFormatter.format(date)
}

export function formatDuration(value: number | null): string {
  return value === null ? '—' : `${formatInteger(Math.round(value))} 毫秒`
}

export function formatPercent(numerator: number, denominator: number): string {
  if (denominator === 0) return '0.0%'
  return `${((numerator / denominator) * 100).toFixed(1)}%`
}
