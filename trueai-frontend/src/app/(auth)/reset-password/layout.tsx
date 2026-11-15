import type { Metadata } from 'next'
import type { ReactNode } from 'react'

// The page is a client component, so its metadata lives here.
export const metadata: Metadata = {
  title: 'Choose a new password',
  robots: { index: false, follow: false },
}

export default function ResetPasswordLayout({ children }: { children: ReactNode }) {
  return children
}
