/**
 * Accept only same-site relative paths inside the app for post-login
 * redirects (prevents open redirects via ?next=).
 */
const ALLOWED_PREFIXES = ['/dashboard', '/integrations', '/settings', '/onboarding', '/reset-password']

export function safeNextPath(value: string | null | undefined, fallback = '/dashboard'): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return fallback
  const path = value.split('#')[0]
  const base = path.split('?')[0]
  return ALLOWED_PREFIXES.some((prefix) => base === prefix || base.startsWith(`${prefix}/`)) ? path : fallback
}
