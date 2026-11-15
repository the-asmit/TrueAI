import type { Metadata } from 'next'
import type { ReactNode } from 'react'

// The page is a client component, so its metadata lives here.
export const metadata: Metadata = {
  title: 'Create your account',
  description:
    'Create a free TrueAI account, connect Sentry and GitHub, and get reviewed fixes for production errors as pull requests.',
}

export default function SignUpLayout({ children }: { children: ReactNode }) {
  return children
}
