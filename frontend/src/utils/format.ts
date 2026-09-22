const integerFormatter = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 0,
})

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  hour12: false,
})

export function formatMoney(value: string): string {
  const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?)(\d+))?$/.exec(value.trim())
  if (match === null) return `¥${value}`

  const rawSign = match[1] ?? ''
  const sourceWhole = match[2] ?? '0'
  const sourceFraction = match[3] ?? ''
  const exponentSign = match[4]?.startsWith('-') === true ? '-' : '+'
  let exponent = (match[5] ?? '0').replace(/^0+/, '') || '0'
  let digits = `${sourceWhole}${sourceFraction}`
  let decimalPosition = sourceWhole.length

  while (exponent !== '0') {
    if (exponentSign === '+') {
      if (decimalPosition === digits.length) digits += '0'
      decimalPosition += 1
    } else if (decimalPosition === 0) {
      digits = `0${digits}`
    } else {
      decimalPosition -= 1
    }
    exponent = decrementDecimalString(exponent)
  }

  const whole = decimalPosition === 0 ? '0' : digits.slice(0, decimalPosition)
  const fraction = decimalPosition === 0 ? digits : digits.slice(decimalPosition)
  const exactFraction = fraction.length >= 8 ? fraction : fraction.padEnd(8, '0')
  const sign = rawSign === '-' && !/[1-9]/.test(digits) ? '' : rawSign
  return `¥${sign}${whole}.${exactFraction}`
}

const previousDigit: Record<string, string> = {
  '1': '0',
  '2': '1',
  '3': '2',
  '4': '3',
  '5': '4',
  '6': '5',
  '7': '6',
  '8': '7',
  '9': '8',
}

function decrementDecimalString(value: string): string {
  const digits = value.split('')
  let index = digits.length - 1
  while (index >= 0) {
    const digit = digits[index] ?? '0'
    if (digit === '0') {
      digits[index] = '9'
      index -= 1
      continue
    }
    digits[index] = previousDigit[digit] ?? '0'
    break
  }
  return digits.join('').replace(/^0+/, '') || '0'
}

export function formatInteger(value: number): string {
  return integerFormatter.format(value)
}

export function formatDateTime(value: string | null): string {
  if (value === null) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : dateTimeFormatter.format(date)
}

const shortDateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const shortDateTimeWithYearFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

/** Compact local timestamp for dense tables: `09-22 13:33`, with the year only when it differs. */
export function formatDateTimeShort(value: string | null): string {
  if (value === null) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const formatter =
    date.getFullYear() === new Date().getFullYear()
      ? shortDateTimeFormatter
      : shortDateTimeWithYearFormatter
  return formatter.format(date).replace(/\//g, '-')
}

export function formatDuration(value: number | null): string {
  return value === null ? '—' : `${formatInteger(Math.round(value))} 毫秒`
}

export function formatPercent(numerator: number, denominator: number): string {
  if (denominator === 0) return '0.0%'
  return `${((numerator / denominator) * 100).toFixed(1)}%`
}

export function formatCompactInteger(value: number): string {
  if (value < 1000) return formatInteger(value)
  if (value < 1_000_000) return `${(value / 1000).toFixed(1)}K`
  if (value < 1_000_000_000) return `${(value / 1_000_000).toFixed(2)}M`
  return `${(value / 1_000_000_000).toFixed(2)}B`
}

export function formatMoneyCompact(value: string): string {
  const num = parseFloat(value)
  if (Number.isNaN(num)) return `¥${value}`
  if (num < 0.01 && num > 0) return `<¥0.01`
  if (num < 1000) return `¥${num.toFixed(2)}`
  if (num < 1_000_000) return `¥${(num / 1000).toFixed(2)}K`
  return `¥${(num / 1_000_000).toFixed(2)}M`
}

export function formatBalanceAmount(amount: string | null, currency: string | null): string {
  if (amount === null) return '—'
  const value = Number.parseFloat(amount)
  if (Number.isNaN(value)) return currency === null ? amount : `${amount} ${currency}`
  const rendered = value.toFixed(4).replace(/\.?0+$/, '')
  return currency === null ? rendered : `${rendered} ${currency}`
}

/**
 * Renders a stored price (decimal string, per million tokens) without trailing zeros.
 *
 * Upstream prices arrive as eight-decimal strings such as ``2.50000000``; the
 * dialog that compares them with local prices needs the short form, and an
 * unset price must stay visibly empty rather than turning into ``0``.
 */
export function formatPrice(value: string | null): string {
  if (value === null) return '—'
  const numeric = Number.parseFloat(value)
  if (Number.isNaN(numeric)) return value
  if (numeric === 0) return '0'
  if (Math.abs(numeric) < 0.000001) return numeric.toExponential(2)
  return String(Number(numeric.toFixed(6)))
}
