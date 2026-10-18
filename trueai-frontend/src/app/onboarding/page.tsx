import type { Metadata } from 'next'

import { Wordmark } from '@/components/brand'
import { ButtonLink } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { api, toMessage } from '@/lib/api/client'
import type { Me } from '@/lib/api/types'

import { SetupSteps } from './setup-steps'

export const metadata: Metadata = { title: 'Set up TrueAI' }

const GITHUB_ERRORS: Record<string, string> = {
  access_denied: 'GitHub access was not granted, so nothing changed.',
  invalid_state: 'That GitHub authorisation expired or was already used. Please connect again.',
  complete_failed: 'TrueAI could not finish connecting GitHub. Please try again.',
}

export default async function OnboardingPage({ searchParams }: PageProps<'/onboarding'>) {
  const params = await searchParams
  const githubError = typeof params.github_error === 'string' ? params.github_error : null

  let me: Me | null = null
  let error: string | null = null
  try {
    me = await api.get<Me>('/auth/me')
  } catch (caught) {
    error = toMessage(caught, 'Your account could not be loaded.')
  }

  return (
    <div className="min-h-dvh bg-paper">
      <header className="flex h-14 items-center justify-between border-b border-rule px-4 sm:px-8">
        <Wordmark href="/dashboard" />
        <form action="/auth/signout" method="post">
          <button type="submit" className="text-[0.8125rem] text-ink-2 hover:text-ink hover:underline">
            Sign out
          </button>
        </form>
      </header>
      <main id="main" className="mx-auto max-w-[720px] px-4 pb-20 pt-10 sm:px-8 sm:pt-14">
        <h1 className="text-[1.75rem] font-bold tracking-[-0.02em] text-ink">Set up TrueAI</h1>
        <p className="mt-2 max-w-[60ch] text-[0.9375rem] leading-relaxed text-ink-2">
          Four steps. When they are done, every new error Sentry reports is investigated by TrueAI and fixed with a pull
          request when it is safe to.
        </p>

        <div className="mt-8 space-y-4">
          {githubError && (
            <Notice kind="error" title="GitHub was not connected">
              {GITHUB_ERRORS[githubError] ?? 'GitHub reported an error. Please try again.'}
            </Notice>
          )}
          {params.github === 'connected' && <Notice kind="success" title="GitHub connected" />}
          {error && (
            <Notice kind="error" title="Setup could not be loaded" action={<ButtonLink href="/onboarding" variant="secondary" size="sm">Try again</ButtonLink>}>
              {error}
            </Notice>
          )}
          {me && <SetupSteps me={me} />}
        </div>
      </main>
    </div>
  )
}
