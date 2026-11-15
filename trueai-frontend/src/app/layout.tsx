import type { Metadata, Viewport } from 'next'
import { JetBrains_Mono, Public_Sans } from 'next/font/google'
import { cookies } from 'next/headers'

import { APP_URL } from '@/lib/site'
import './globals.css'

const publicSans = Public_Sans({ variable: '--font-public-sans', subsets: ['latin'], display: 'swap' })
const jetbrainsMono = JetBrains_Mono({ variable: '--font-jetbrains-mono', subsets: ['latin'], display: 'swap' })

export const metadata: Metadata = {
  metadataBase: new URL(APP_URL),
  title: {
    default: 'TrueAI: AI that turns Sentry errors into GitHub pull requests',
    template: '%s · TrueAI',
  },
  description:
    'TrueAI reads each Sentry error, finds the root cause in your code and opens a reviewed fix as a GitHub pull request. Nothing merges without you.',
  // './' resolves against each page's own path, so every page is its own canonical URL.
  alternates: { canonical: './' },
  openGraph: {
    title: 'TrueAI: AI that turns Sentry errors into GitHub pull requests',
    description: 'Every Sentry error becomes a reviewed fix, opened as a pull request. Nothing merges without you.',
    type: 'website',
    siteName: 'TrueAI',
  },
  twitter: { card: 'summary_large_image' },
  robots: { index: true, follow: true },
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f8f8f5' },
    { media: '(prefers-color-scheme: dark)', color: '#0e1012' },
  ],
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const theme = (await cookies()).get('theme')?.value
  const dataTheme = theme === 'light' || theme === 'dark' ? theme : undefined

  return (
    <html lang="en" data-theme={dataTheme} className={`${publicSans.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-paper text-ink">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-sheet focus:px-3 focus:py-2 focus:text-sm focus:shadow-[var(--shadow-pop)]"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  )
}
