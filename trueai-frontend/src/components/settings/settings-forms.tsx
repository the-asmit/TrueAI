'use client'

import { KeyRound } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { createApiKey, deleteAccount, revokeApiKey, saveProfile } from '@/app/actions/account'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { CopyButton } from '@/components/ui/copy-button'
import { describedBy, Field, Input } from '@/components/ui/field'
import { Notice } from '@/components/ui/notice'
import { ToneMark } from '@/components/ui/status'
import type { ApiKey, CreatedApiKey } from '@/lib/api/types'
import { formatRelative, formatUtc } from '@/lib/format'

export function ProfileForm({ initialName }: { initialName: string }) {
  const [name, setName] = useState(initialName)
  const [state, setState] = useState<{ pending: boolean; error: string | null; saved: boolean }>({ pending: false, error: null, saved: false })

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setState({ pending: true, error: null, saved: false })
    const result = await saveProfile(name)
    setState({ pending: false, error: result.ok ? null : result.error, saved: result.ok })
  }

  return (
    <form onSubmit={save}>
      <Field id="full-name" label="Name" error={state.error}>
        <div className="flex items-center gap-2">
          <Input
            id="full-name"
            autoComplete="name"
            maxLength={100}
            value={name}
            onChange={(event) => {
              setName(event.target.value)
              setState((current) => ({ ...current, saved: false }))
            }}
            aria-describedby={describedBy('full-name', state.error)}
            aria-invalid={Boolean(state.error) || undefined}
            className="min-w-0 flex-1"
          />
          <Button type="submit" loading={state.pending} disabled={!name.trim() || name.trim() === initialName}>
            Save
          </Button>
        </div>
      </Field>
      <p role="status" className="mt-1.5 min-h-5 text-[0.8125rem] text-fixed">
        {state.saved ? 'Saved.' : ''}
      </p>
    </form>
  )
}

export function ApiKeys({ keys }: { keys: ApiKey[] }) {
  const [created, setCreated] = useState<CreatedApiKey | null>(null)
  const [label, setLabel] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function create(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    const result = await createApiKey(label || 'API key')
    setPending(false)
    if (!result.ok) {
      setError(result.error)
      return
    }
    setCreated(result.data)
    setLabel('')
  }

  const active = keys.filter((key) => key.is_active)
  const revoked = keys.filter((key) => !key.is_active)

  return (
    <div className="space-y-5">
      {created && (
        <div className="space-y-3 rounded-lg border border-rule bg-sheet p-4">
          <Notice kind="warning" title={`“${created.name}” created — copy it now`}>
            This is the only time the key is shown. Use the webhook URL in Sentry, or send the key as <code className="font-mono">X-API-Key</code> to call the API.
          </Notice>
          <KeyValue label="Webhook URL" value={created.webhook_url} />
          <KeyValue label="API key" value={created.raw_key} />
          <Button variant="ghost" size="sm" onClick={() => setCreated(null)}>
            I have stored it
          </Button>
        </div>
      )}

      {active.length > 0 ? (
        <ul className="divide-y divide-rule overflow-hidden rounded-lg border border-rule bg-sheet">
          {active.map((key) => (
            <li key={key.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div className="flex min-w-0 items-start gap-3">
                <KeyRound className="mt-0.5 size-4 shrink-0 text-ink-3" aria-hidden />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink">{key.name || 'API key'}</p>
                  <p className="text-[0.75rem] text-ink-3">
                    <span className="font-mono">{key.key_prefix}…</span> · created <time dateTime={key.created_at} title={formatUtc(key.created_at)} suppressHydrationWarning>{formatRelative(key.created_at)}</time> ·{' '}
                    {key.last_used_at ? (
                      <>
                        last used <time dateTime={key.last_used_at} title={formatUtc(key.last_used_at)} suppressHydrationWarning>{formatRelative(key.last_used_at)}</time>
                      </>
                    ) : (
                      'never used'
                    )}
                  </p>
                </div>
              </div>
              <ConfirmDialog
                trigger={<Button variant="ghost" size="sm" className="text-ink-3 hover:text-failure">Revoke</Button>}
                title={`Revoke “${key.name || key.key_prefix}”?`}
                description="Anything using this key stops working immediately — including a Sentry webhook that uses it. This cannot be undone."
                confirmLabel="Revoke key"
                destructive
                onConfirm={async () => {
                  const result = await revokeApiKey(key.id)
                  return result.ok ? null : result.error
                }}
              />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-2">No active keys. Sentry cannot reach TrueAI until you create one.</p>
      )}

      <form onSubmit={create} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <Field id="key-label" label="New key label" error={error} className="flex-1">
          <Input
            id="key-label"
            placeholder="Sentry — production"
            maxLength={60}
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            aria-describedby={describedBy('key-label', error)}
          />
        </Field>
        <Button type="submit" variant="secondary" loading={pending}>
          Create key
        </Button>
      </form>

      {revoked.length > 0 && (
        <details>
          <summary className="cursor-pointer text-[0.8125rem] text-ink-3 hover:text-ink">{revoked.length} revoked</summary>
          <ul className="mt-2 space-y-1 text-[0.75rem] text-ink-3">
            {revoked.map((key) => (
              <li key={key.id}>
                <span className="font-mono">{key.key_prefix}…</span> {key.name} · revoked <time dateTime={key.revoked_at ?? undefined} suppressHydrationWarning>{formatRelative(key.revoked_at)}</time>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1.5">
      <p className="text-[0.75rem] text-ink-3">{label}</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <code className="block min-w-0 flex-1 select-all break-all rounded-md border border-rule bg-sunken px-3 py-2 text-[0.8125rem] text-ink">{value}</code>
        <CopyButton value={value} />
      </div>
    </div>
  )
}

export function AutomaticPullRequests({ threshold }: { threshold: number }) {
  return (
    <p className="max-w-[70ch] text-sm leading-relaxed text-ink-2">
      TrueAI opens a pull request only when it is at least {Math.round(threshold * 100)}% confident in both the root cause and the fix, and the
      change passes its safety checks. Everything else arrives as a diagnosis with next steps. Nothing is ever merged for you.
    </p>
  )
}

export function DeleteAccount() {
  const router = useRouter()
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-failure/30 bg-sheet px-4 py-4">
      <div className="max-w-[60ch]">
        <p className="text-sm font-semibold text-ink">Delete account</p>
        <p className="mt-0.5 text-[0.8125rem] text-ink-2">
          Deletes your incidents, analyses, keys and integrations, and revokes TrueAI’s access to GitHub. Pull requests already on GitHub stay there.
        </p>
      </div>
      <ConfirmDialog
        trigger={<Button variant="danger">Delete account</Button>}
        title="Delete your TrueAI account?"
        description="Everything is deleted permanently. This cannot be undone."
        confirmLabel="Delete everything"
        confirmPhrase="delete my account"
        destructive
        onConfirm={async () => {
          const result = await deleteAccount()
          if (!result.ok) return result.error
          router.replace('/login?error=deleted')
          return null
        }}
      />
    </div>
  )
}

export function KeyStatus({ active }: { active: number }) {
  return active > 0 ? <ToneMark tone="fixed" label={`${active} active`} /> : <ToneMark tone="human" label="None active" />
}
