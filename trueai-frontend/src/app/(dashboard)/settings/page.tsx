import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { ApiKeys, AutomaticPullRequests, DeleteAccount, KeyStatus, ProfileForm } from '@/components/settings/settings-forms'
import { ButtonLink } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { api, toMessage } from '@/lib/api/client'
import type { ApiKey, Me } from '@/lib/api/types'
import { createClient } from '@/lib/supabase/server'

export const metadata: Metadata = { title: 'Settings' }

export default async function SettingsPage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  let me: Me | null = null
  let keys: ApiKey[] = []
  let loadError: string | null = null
  try {
    ;[me, keys] = await Promise.all([api.get<Me>('/auth/me'), api.get<ApiKey[]>('/auth/api-keys')])
  } catch (error) {
    loadError = toMessage(error, 'Settings could not be loaded.')
  }

  return (
    <div className="mx-auto max-w-[860px] px-4 pb-20 pt-6 sm:px-8 sm:pt-10">
      <h1 className="text-2xl font-bold tracking-[-0.02em] text-ink">Settings</h1>
      <p className="mt-1 text-sm text-ink-2">{user?.email}</p>

      {loadError && (
        <Notice kind="error" title="Settings could not be loaded" className="mt-6" action={<ButtonLink href="/settings" variant="secondary" size="sm">Try again</ButtonLink>}>
          {loadError}
        </Notice>
      )}

      {me && (
        <div className="mt-8 space-y-12">
          <SettingsSection id="profile" title="Profile">
            <ProfileForm initialName={me.full_name ?? ''} />
          </SettingsSection>

          <SettingsSection id="api-keys" title="API keys" aside={<KeyStatus active={keys.filter((key) => key.is_active).length} />} description="Keys authenticate Sentry’s webhook and scripts calling the TrueAI API. Only a hash is stored.">
            <ApiKeys keys={keys} />
          </SettingsSection>

          <SettingsSection id="pull-requests" title="Automatic pull requests">
            <AutomaticPullRequests threshold={me.auto_pr_threshold} />
          </SettingsSection>

          <SettingsSection id="danger" title="Danger zone">
            <DeleteAccount />
          </SettingsSection>
        </div>
      )}
    </div>
  )
}

function SettingsSection({ id, title, description, aside, children }: { id: string; title: string; description?: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-20 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-rule pb-4">
        <div>
          <h2 id={`${id}-title`} className="text-lg font-semibold text-ink">
            {title}
          </h2>
          {description && <p className="mt-1 max-w-[65ch] text-[0.8125rem] text-ink-2">{description}</p>}
        </div>
        {aside}
      </div>
      {children}
    </section>
  )
}
