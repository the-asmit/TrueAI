import type { Metadata } from 'next'
import Link from 'next/link'

import { GitHubMark } from '@/components/brand'
import { ConnectGitHubButton, DefaultRepositoryForm, DisconnectGitHubButton } from '@/components/integrations/github-panel'
import { RepoMappings } from '@/components/integrations/repo-mappings'
import { SentryApiForm, SigningSecretForm } from '@/components/integrations/sentry-settings'
import { SentryInstructions, WebhookCreator } from '@/components/integrations/webhook-creator'
import { ButtonLink } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { ToneMark } from '@/components/ui/status'
import { api, toMessage } from '@/lib/api/client'
import type { Me, RepoMapping, SentrySettings } from '@/lib/api/types'

export const metadata: Metadata = { title: 'Integrations' }

const GITHUB_ERRORS: Record<string, string> = {
  access_denied: 'GitHub access was not granted, so nothing changed.',
  invalid_state: 'That GitHub authorisation expired or was already used. Please connect again.',
  exchange_failed: 'GitHub did not accept the authorisation. Please try again.',
  profile_failed: 'GitHub did not return your profile. Please try again.',
  unavailable: 'TrueAI could not finish connecting GitHub right now. Please try again.',
  complete_failed: 'TrueAI could not finish connecting GitHub.',
  github_error: 'GitHub reported an error. Please try again.',
}

export default async function IntegrationsPage({ searchParams }: PageProps<'/integrations'>) {
  const params = await searchParams
  const githubError = typeof params.github_error === 'string' ? params.github_error : null
  const githubMessage = typeof params.message === 'string' ? params.message : null
  const justConnected = params.github === 'connected'

  let me: Me | null = null
  let sentry: SentrySettings | null = null
  let mappings: RepoMapping[] = []
  let loadError: string | null = null
  try {
    ;[me, sentry, mappings] = await Promise.all([
      api.get<Me>('/auth/me'),
      api.get<SentrySettings>('/integrations/sentry'),
      api.get<RepoMapping[]>('/integrations/repositories'),
    ])
  } catch (error) {
    loadError = toMessage(error, 'Integrations could not be loaded.')
  }

  return (
    <div className="mx-auto max-w-[860px] px-4 pb-20 pt-6 sm:px-8 sm:pt-10">
      <h1 className="text-2xl font-bold tracking-[-0.02em] text-ink">Integrations</h1>
      <p className="mt-1 max-w-[65ch] text-sm text-ink-2">Sentry sends errors in; GitHub is where TrueAI reads your code and opens fixes.</p>

      <div className="mt-6 space-y-3">
        {justConnected && <Notice kind="success" title="GitHub connected">Choose the repository TrueAI should work on below.</Notice>}
        {githubError && (
          <Notice kind="error" title="GitHub was not connected">
            {GITHUB_ERRORS[githubError] ?? GITHUB_ERRORS.github_error} {githubError === 'complete_failed' && githubMessage}
          </Notice>
        )}
        {loadError && (
          <Notice kind="error" title="Integrations could not be loaded" action={<ButtonLink href="/integrations" variant="secondary" size="sm">Try again</ButtonLink>}>
            {loadError}
          </Notice>
        )}
      </div>

      {me && sentry && (
        <div className="mt-8 space-y-12">
          {/* ---- GitHub ---- */}
          <section aria-labelledby="github-title" className="space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-rule pb-4">
              <div>
                <h2 id="github-title" className="flex items-center gap-2 text-lg font-semibold text-ink">
                  <GitHubMark className="size-5" /> GitHub
                </h2>
                <p className="mt-1 text-[0.8125rem] text-ink-2">
                  {me.github_connected ? (
                    <>
                      Connected as <span className="font-mono text-ink">@{me.github_username}</span>
                    </>
                  ) : (
                    'Not connected'
                  )}
                </p>
              </div>
              {me.github_connected ? (
                <div className="flex items-center gap-1">
                  <ConnectGitHubButton returnTo="/integrations" label="Reconnect" variant="secondary" />
                  <DisconnectGitHubButton />
                </div>
              ) : null}
            </div>
            {me.github_connected ? (
              <DefaultRepositoryForm initialRepo={me.github_repo} initialBranch={me.github_branch} />
            ) : (
              <div className="space-y-3">
                <p className="max-w-[65ch] text-sm leading-relaxed text-ink-2">
                  TrueAI asks for access to your repositories so the agents can read the code behind each error and open pull
                  requests. It never pushes to your branches directly and never merges.
                </p>
                <ConnectGitHubButton returnTo="/integrations" />
              </div>
            )}
          </section>

          {/* ---- Sentry ---- */}
          <section aria-labelledby="sentry-title" className="space-y-6">
            <div className="border-b border-rule pb-4">
              <h2 id="sentry-title" className="text-lg font-semibold text-ink">Sentry</h2>
              <p className="mt-1 text-[0.8125rem] text-ink-2">
                {me.has_api_key ? <ToneMark tone="fixed" label="Webhook key active" /> : <ToneMark tone="human" label="No webhook yet" />}
              </p>
            </div>

            <div className="space-y-3">
              <h3 className="text-[0.8125rem] font-medium text-ink">Webhook URL</h3>
              <WebhookCreator hasActiveKey={me.has_api_key} />
              {me.has_api_key && (
                <details className="group">
                  <summary className="cursor-pointer text-[0.8125rem] text-ink-2 hover:text-ink">How to add it to Sentry</summary>
                  <div className="mt-3">
                    <SentryInstructions />
                  </div>
                </details>
              )}
              <p className="text-[0.75rem] text-ink-3">
                Manage or revoke keys in <Link href="/settings#api-keys" className="underline hover:text-ink">Settings</Link>.
              </p>
            </div>

            <div className="grid gap-8 rounded-lg border border-rule bg-sheet p-5">
              <SigningSecretForm settings={sentry} />
              <div className="border-t border-rule pt-6">
                <SentryApiForm settings={sentry} />
                <p className="mt-3 max-w-[65ch] text-[0.75rem] text-ink-3">
                  Optional. Some Sentry webhooks (like “issue created”) carry no stack trace; with API access TrueAI fetches the full event.
                </p>
              </div>
            </div>
          </section>

          {/* ---- Routing ---- */}
          {me.github_connected && (
            <section aria-labelledby="routing-title" className="space-y-4">
              <div className="border-b border-rule pb-4">
                <h2 id="routing-title" className="text-lg font-semibold text-ink">Project routing</h2>
                <p className="mt-1 max-w-[65ch] text-[0.8125rem] text-ink-2">
                  Send incidents from specific Sentry projects to their own repositories. Everything else goes to your default repository.
                </p>
              </div>
              <RepoMappings mappings={mappings} defaultRepo={me.github_repo} />
            </section>
          )}
        </div>
      )}
    </div>
  )
}
