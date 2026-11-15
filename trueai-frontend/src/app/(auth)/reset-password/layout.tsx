import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { pageMetadata } from '@/lib/metadata'

// The page is a client component, so its metadata lives here.
export const metadata: Metadata = pageMetadata({
  title: 'Choose a new password',
  socialTitle: 'Choose a new TrueAI password',
  description: 'Set a new password for your TrueAI account.',
  noindex: true,
})

export default function ResetPasswordLayout({ children }: { children: ReactNode }) {
  return children
}
