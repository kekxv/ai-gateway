type Decimal = {
  digits: bigint
  scale: bigint
}

const decimalPattern = /^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?)(\d+))?$/

export function multiplyDecimals(value: string, ...factors: Array<string | number>): string {
  const operands = [value, ...factors.map(String)].map(parseNonnegativeDecimal)
  const product = operands.reduce<Decimal>(
    (total, operand) => ({
      digits: total.digits * operand.digits,
      scale: total.scale + operand.scale,
    }),
    { digits: 1n, scale: 0n },
  )
  return formatEightPlaces(roundHalfUp(product.digits, product.scale, 8n))
}

function parseNonnegativeDecimal(value: string): Decimal {
  const match = decimalPattern.exec(value.trim())
  if (match === null || match[1] === '-') {
    throw new TypeError(`Expected a nonnegative finite decimal: ${value}`)
  }

  const whole = match[2] ?? '0'
  const fraction = match[3] ?? ''
  const exponent = BigInt(match[5] ?? '0')
  const signedExponent = match[4] === '-' ? -exponent : exponent

  return {
    digits: BigInt(`${whole}${fraction}`),
    scale: BigInt(fraction.length) - signedExponent,
  }
}

function roundHalfUp(digits: bigint, scale: bigint, places: bigint): bigint {
  if (scale <= places) return digits * 10n ** (places - scale)

  const divisor = 10n ** (scale - places)
  const quotient = digits / divisor
  const remainder = digits % divisor
  return remainder * 2n >= divisor ? quotient + 1n : quotient
}

function formatEightPlaces(digits: bigint): string {
  const value = digits.toString().padStart(9, '0')
  return `${value.slice(0, -8)}.${value.slice(-8)}`
}
