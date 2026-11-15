import type { NextConfig } from 'next'
import { PHASE_PRODUCTION_BUILD } from 'next/constants'

// Security headers for every response (the per-request CSP is set in src/proxy.ts).
const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), payment=(), usb=()' },
  { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
  ...(process.env.NODE_ENV === 'production'
    ? [{ key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' }]
    : []),
]

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  output: 'standalone',
  // Development only: hosts allowed to load the dev server's scripts, so the app can be opened on a phone through
  // an ngrok tunnel. Without this the page loads but never becomes interactive.
  allowedDevOrigins: ['*.ngrok-free.dev', '*.ngrok-free.app', '*.ngrok.app', '*.ngrok.io'],
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }]
  },
}

/**
 * Canonical URLs, the sitemap, robots.txt and structured data are all built from
 * NEXT_PUBLIC_APP_URL. A production build without it (or still pointing at
 * localhost) would publish localhost links, so say so loudly without failing
 * the build: local production builds are still useful for testing.
 */
function warnAboutAppUrl() {
  const appUrl = process.env.NEXT_PUBLIC_APP_URL
  const problem = !appUrl
    ? 'NEXT_PUBLIC_APP_URL is not set, so it falls back to http://localhost:3000.'
    : /localhost|127\.0\.0\.1|0\.0\.0\.0/.test(appUrl)
      ? `NEXT_PUBLIC_APP_URL is ${appUrl}.`
      : null
  // The build loads this config in its worker processes too; they inherit the flag, so the warning shows once.
  if (problem && !process.env.TRUEAI_APP_URL_WARNED) {
    process.env.TRUEAI_APP_URL_WARNED = '1'
    console.warn(
      `\n⚠ ${problem}\n  Canonical URLs, the sitemap, robots.txt and structured data in this build will point at localhost.\n  Set NEXT_PUBLIC_APP_URL to the public https:// address before deploying.\n`,
    )
  }
}

export default function config(phase: string): NextConfig {
  if (phase === PHASE_PRODUCTION_BUILD) warnAboutAppUrl()
  return nextConfig
}
