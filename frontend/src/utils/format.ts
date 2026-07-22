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

export function formatDuration(value: number | null): string {
  return value === null ? '—' : `${formatInteger(Math.round(value))} 毫秒`
}

export function formatPercent(numerator: number, denominator: number): string {
  if (denominator === 0) return '0.0%'
  return `${((numerator / denominator) * 100).toFixed(1)}%`
}
