'use client'

import { useState } from 'react'

import { createApiKey } from '@/app/actions/account'
import { Button } from '@/components/ui/button'
import { CopyButton } from '@/components/ui/copy-button'
import { Notice } from '@/components/ui/notice'
import type { CreatedApiKey } from '@/lib/api/types'

/**
 * Creates a webhook key and shows the complete, working webhook URL exactly
 * once (the key is stored only as a hash, so it can never be shown again).
 */
export function WebhookCreator({ hasActiveKey, onCreated }: { hasActiveKey: boolean; onCreated?: (key: CreatedApiKey) => void }) {
  const [created, setCreated] = useState<CreatedApiKey | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function create() {
    setPending(true)
    setError(null)
    const result = await createApiKey('Sentry webhook')
    setPending(false)
    if (!result.ok) {
      setError(result.error)
      return
    }
    setCreated(result.data)
    onCreated?.(result.data)
  }

  if (created) {
    return (
      <div className="space-y-3">
        <Notice kind="warning" title="Copy this URL now">
          It contains a secret key and will not be shown again. If you lose it, create a new one and revoke the old key in Settings.
        </Notice>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <code className="block min-w-0 flex-1 select-all break-all rounded-md border border-rule bg-sunken px-3 py-2.5 text-[0.8125rem] text-ink">
            {created.webhook_url}
          </code>
          <CopyButton value={created.webhook_url} label="Copy URL" size="md" />
        </div>
        <SentryInstructions />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="max-w-[65ch] text-[0.8125rem] leading-relaxed text-ink-2">
        {hasActiveKey
          ? 'A webhook key already exists. Its URL was shown when it was created; if you no longer have it, create a new one.'
          : 'Create the URL Sentry will send errors to. It includes a secret key that identifies your account.'}
      </p>
      <Button onClick={create} loading={pending} variant={hasActiveKey ? 'secondary' : 'primary'}>
        {hasActiveKey ? 'Create a new webhook URL' : 'Create webhook URL'}
      </Button>
      {error && (
        <p role="alert" className="text-[0.8125rem] text-failure">
          {error}
        </p>
      )}
    </div>
  )
}

export function SentryInstructions() {
  const strong = 'font-medium text-ink'
  return (
    <div className="space-y-2">
      <ol className="max-w-[70ch] list-decimal space-y-1.5 pl-5 text-[0.8125rem] leading-relaxed text-ink-2 marker:text-ink-3">
        <li>
          In Sentry, open <span className={strong}>Settings → Developer Settings → Custom Integrations</span> and create an{' '}
          <span className={strong}>Internal Integration</span>.
        </li>
        <li>
          Paste the URL into <span className={strong}>Webhook URL</span>, turn on <span className={strong}>Alert Rule Action</span>, and give{' '}
          <span className={strong}>Issue &amp; Event</span> read access.
        </li>
        <li>
          Add an alert rule to your project: <span className={strong}>A new issue is created</span> → <span className={strong}>Send a notification via</span> your integration.
        </li>
        <li>
          Optional: copy the integration’s <span className={strong}>Client Secret</span> into “Signing secret” so TrueAI verifies every delivery.
        </li>
      </ol>
      <p className="max-w-[70ch] text-[0.75rem] text-ink-3">
        Using Sentry’s older WebHooks plugin instead? Paste the URL under Project Settings → Legacy Integrations → WebHooks.
      </p>
    </div>
  )
}
