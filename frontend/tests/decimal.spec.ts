import { describe, expect, it } from 'vitest'
import { multiplyDecimals } from '@/utils/decimal'

describe('multiplyDecimals', () => {
  it('multiplies catalog prices and both multipliers without floating-point loss', () => {
    expect(multiplyDecimals('2.00000000', 1.5, 0.8)).toBe('2.40000000')
    expect(multiplyDecimals('9007199254740993.12345678', 1.1)).toBe(
      '9907919180215092.43580246',
    )
  })

  it('accepts scientific catalog values and rounds the combined product once', () => {
    expect(multiplyDecimals('1E-8', '0.5', '0.5')).toBe('0.00000000')
    expect(multiplyDecimals('0.005', 1, 1)).toBe('0.00500000')
  })
})
