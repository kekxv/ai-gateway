const redirectBase = 'https://gateway.invalid'

export function resolveLoginRedirect(redirect: unknown): string {
  if (typeof redirect !== 'string') return '/'

  let decoded = redirect
  for (let attempt = 0; attempt < 8; attempt += 1) {
    if (!decoded.startsWith('/') || decoded.startsWith('//') || decoded.includes('\\')) return '/'
    try {
      const next = decodeURIComponent(decoded)
      if (next === decoded) break
      if (attempt === 7) return '/'
      decoded = next
    } catch {
      return '/'
    }
  }

  try {
    if (new URL(decoded, redirectBase).origin !== redirectBase) return '/'
  } catch {
    return '/'
  }
  return redirect
}
