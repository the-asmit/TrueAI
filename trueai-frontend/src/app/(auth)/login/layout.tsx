import type { Metadata } from 'next'
import type { ReactNode } from 'react'

// The page is a client component, so its metadata lives here.
export const metadata: Metadata = {
  title: 'Sign in',
  description:
    'Sign in to TrueAI to follow your incidents, read root-cause reports and review the fix pull requests on your repositories.',
}

export default function LoginLayout({ children }: { children: ReactNode }) {
  return children
}
