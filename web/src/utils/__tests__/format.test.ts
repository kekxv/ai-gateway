import { describe, it, expect } from 'vitest'

// Utility functions to test (we'll define them inline since they may not exist yet)
const formatCurrency = (num: number): string => {
  return '$' + num.toFixed(4)
}

const formatNumber = (num: number): string => {
  if (num >= 1000000) return (num / 1000000).toFixed(2) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(2) + 'K'
  return num.toString()
}

const formatDate = (date: string | Date): string => {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toISOString().split('T')[0]
}

const validateEmail = (email: string): boolean => {
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return regex.test(email)
}

const validatePassword = (password: string): { valid: boolean; message?: string } => {
  if (!password) return { valid: false, message: 'Password is required' }
  if (password.length < 8) return { valid: false, message: 'Password must be at least 8 characters' }
  return { valid: true }
}

const validateTotpToken = (token: string): boolean => {
  return /^\d{6}$/.test(token)
}

const maskApiKey = (key: string): string => {
  if (!key || key.length < 12) return key
  return key.slice(0, 8) + '...' + key.slice(-4)
}

describe('Format Utilities', () => {
  describe('formatCurrency', () => {
    it('should format zero', () => {
      expect(formatCurrency(0)).toBe('$0.0000')
    })

    it('should format positive number', () => {
      expect(formatCurrency(123.45)).toBe('$123.4500')
    })

    it('should format negative number', () => {
      expect(formatCurrency(-10.5)).toBe('$-10.5000')
    })

    it('should handle very small numbers', () => {
      expect(formatCurrency(0.0001)).toBe('$0.0001')
    })
  })

  describe('formatNumber', () => {
    it('should format small numbers as-is', () => {
      expect(formatNumber(100)).toBe('100')
    })

    it('should format thousands with K suffix', () => {
      expect(formatNumber(1500)).toBe('1.50K')
    })

    it('should format millions with M suffix', () => {
      expect(formatNumber(1500000)).toBe('1.50M')
    })

    it('should format exact thousand', () => {
      expect(formatNumber(1000)).toBe('1.00K')
    })

    it('should format exact million', () => {
      expect(formatNumber(1000000)).toBe('1.00M')
    })
  })

  describe('formatDate', () => {
    it('should format date string', () => {
      expect(formatDate('2024-01-15T10:30:00Z')).toBe('2024-01-15')
    })

    it('should format Date object', () => {
      const date = new Date('2024-06-20')
      expect(formatDate(date)).toBe('2024-06-20')
    })
  })
})

describe('Validation Utilities', () => {
  describe('validateEmail', () => {
    it('should validate correct email', () => {
      expect(validateEmail('test@example.com')).toBe(true)
    })

    it('should validate email with subdomain', () => {
      expect(validateEmail('user@mail.example.com')).toBe(true)
    })

    it('should reject invalid email without @', () => {
      expect(validateEmail('testexample.com')).toBe(false)
    })

    it('should reject invalid email without domain', () => {
      expect(validateEmail('test@')).toBe(false)
    })

    it('should reject empty string', () => {
      expect(validateEmail('')).toBe(false)
    })

    it('should reject email with spaces', () => {
      expect(validateEmail('test @example.com')).toBe(false)
    })
  })

  describe('validatePassword', () => {
    it('should validate correct password', () => {
      expect(validatePassword('password123')).toEqual({ valid: true })
    })

    it('should reject empty password', () => {
      expect(validatePassword('')).toEqual({ valid: false, message: 'Password is required' })
    })

    it('should reject short password', () => {
      expect(validatePassword('short')).toEqual({ valid: false, message: 'Password must be at least 8 characters' })
    })

    it('should accept exactly 8 characters', () => {
      expect(validatePassword('12345678')).toEqual({ valid: true })
    })

    it('should accept long password', () => {
      expect(validatePassword('verylongpassword123')).toEqual({ valid: true })
    })
  })

  describe('validateTotpToken', () => {
    it('should validate correct 6-digit token', () => {
      expect(validateTotpToken('123456')).toBe(true)
    })

    it('should reject 5-digit token', () => {
      expect(validateTotpToken('12345')).toBe(false)
    })

    it('should reject 7-digit token', () => {
      expect(validateTotpToken('1234567')).toBe(false)
    })

    it('should reject token with letters', () => {
      expect(validateTotpToken('abc123')).toBe(false)
    })

    it('should reject empty string', () => {
      expect(validateTotpToken('')).toBe(false)
    })
  })
})

describe('Utility Functions', () => {
  describe('maskApiKey', () => {
    it('should mask long key', () => {
      expect(maskApiKey('sk-1234567890abcdef')).toBe('sk-12345...cdef')
    })

    it('should return short key as-is', () => {
      expect(maskApiKey('short')).toBe('short')
    })

    it('should handle empty string', () => {
      expect(maskApiKey('')).toBe('')
    })

    it('should handle exactly 12 char key', () => {
      expect(maskApiKey('123456789012')).toBe('12345678...9012')
    })
  })
})