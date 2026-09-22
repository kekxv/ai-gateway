import { describe, expect, it } from 'vitest'

import { formatDateTimeShort, formatPrice } from '@/utils/format'

describe('formatDateTimeShort', () => {
  it('renders a compact local timestamp without the year for the current year', () => {
    const thisYear = new Date().getFullYear()
    expect(formatDateTimeShort(`${String(thisYear)}-09-22T05:33:06.593876+00:00`)).toMatch(
      /^09-22 \d{2}:\d{2}$/,
    )
  })

  it('parses microsecond precision timestamps instead of echoing them', () => {
    const rendered = formatDateTimeShort('2026-09-22T05:33:06.593876+00:00')
    expect(rendered).not.toContain('T')
    expect(rendered).not.toContain('+00:00')
  })

  it('keeps the year when it differs from the current year', () => {
    expect(formatDateTimeShort('2001-01-02T03:04:05Z')).toMatch(/^2001-01-02 \d{2}:\d{2}$/)
  })

  it('falls back to a dash for missing or unparseable values', () => {
    expect(formatDateTimeShort(null)).toBe('—')
    expect(formatDateTimeShort('not-a-date')).toBe('—')
  })
})

describe('formatPrice', () => {
  it('trims trailing zeros from stored decimal prices', () => {
    expect(formatPrice('2.50000000')).toBe('2.5')
    expect(formatPrice('10.00000000')).toBe('10')
    expect(formatPrice('0.06660000')).toBe('0.0666')
  })

  it('treats a zero price as zero instead of hiding it', () => {
    expect(formatPrice('0.00000000')).toBe('0')
    expect(formatPrice('0E-8')).toBe('0')
  })

  it('falls back to a dash for missing prices', () => {
    expect(formatPrice(null)).toBe('—')
  })

  it('keeps tiny prices readable', () => {
    expect(formatPrice('0.00000001')).toBe('1.00e-8')
  })
})
