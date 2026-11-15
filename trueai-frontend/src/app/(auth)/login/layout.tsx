import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { pageMetadata } from '@/lib/metadata'

// The page is a client component, so its metadata lives here.
export const metadata: Metadata = pageMetadata({
  title: 'Sign in',
  socialTitle: 'Sign in to TrueAI',
  description:
    'Sign in to TrueAI to follow your incidents, read root-cause reports and review the fix pull requests on your repositories.',
})

export default function LoginLayout({ children }: { children: ReactNode }) {
  return children
}
