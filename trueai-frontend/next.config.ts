import type { NextConfig } from 'next'

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

export default nextConfig
