import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { pageMetadata } from '@/lib/metadata'

// The page is a client component, so its metadata lives here.
export const metadata: Metadata = pageMetadata({
  title: 'Reset your password',
  socialTitle: 'Reset your TrueAI password',
  description: 'Enter your email and TrueAI sends you a link to choose a new password.',
  noindex: true,
})

export default function ForgotPasswordLayout({ children }: { children: ReactNode }) {
  return children
}
