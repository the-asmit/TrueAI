'use client'

import { Check } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useState, type ReactNode } from 'react'

import { saveProfile } from '@/app/actions/account'
import { ConnectGitHubButton, DefaultRepositoryForm } from '@/components/integrations/github-panel'
import { SentryInstructions, WebhookCreator } from '@/components/integrations/webhook-creator'
import { Button, ButtonLink } from '@/components/ui/button'
import { describedBy, Field, Input } from '@/components/ui/field'
import type { Me } from '@/lib/api/types'
import { cn } from '@/lib/utils'

type StepKey = 'profile' | 'github' | 'repository' | 'webhook'

export function SetupSteps({ me }: { me: Me }) {
  const router = useRouter()
  const [name, setName] = useState(me.full_name ?? '')
  const [repo, setRepo] = useState(me.github_repo ? `${me.github_repo}${me.github_branch ? `@${me.github_branch}` : ''}` : '')
  const [webhookCreated, setWebhookCreated] = useState(false)

  const done: Record<StepKey, boolean> = {
    profile: Boolean(me.full_name),
    github: me.github_connected,
    repository: Boolean(me.github_repo),
    webhook: me.has_api_key || webhookCreated,
  }
  const firstOpen = (['profile', 'github', 'repository', 'webhook'] as StepKey[]).find((key) => !done[key]) ?? null
  const [editing, setEditing] = useState<StepKey | null>(null)
  const open = editing ?? firstOpen
  const complete = Object.values(done).every(Boolean)

  const refresh = () => {
    setEditing(null)
    router.refresh()
  }

  return (
    <div className="space-y-3">
      <Step
        number={1}
        title="Your name"
        done={done.profile}
        open={open === 'profile'}
        summary={me.full_name ?? name}
        onEdit={() => setEditing('profile')}
      >
        <ProfileStep name={name} setName={setName} onSaved={refresh} />
      </Step>

      <Step
        number={2}
        title="Connect GitHub"
        done={done.github}
        open={open === 'github'}
        summary={me.github_username ? `@${me.github_username}` : undefined}
        onEdit={() => setEditing('github')}
      >
        <div className="space-y-3">
          <p className="max-w-[60ch] text-[0.8125rem] leading-relaxed text-ink-2">
            TrueAI reads the code behind each error and opens fixes as pull requests. TrueAI never pushes to your branches
            and never merges.
          </p>
          <ConnectGitHubButton returnTo="/onboarding" label={me.github_connected ? 'Reconnect GitHub' : 'Connect GitHub'} />
        </div>
      </Step>

      <Step
        number={3}
        title="Choose the repository"
        done={done.repository}
        open={open === 'repository'}
        locked={!done.github}
        summary={repo || undefined}
        onEdit={() => setEditing('repository')}
      >
        <DefaultRepositoryForm
          initialRepo={me.github_repo}
          initialBranch={me.github_branch}
          submitLabel="Use this repository"
          onSaved={(savedRepo, branch) => {
            setRepo(`${savedRepo}@${branch}`)
            refresh()
          }}
        />
      </Step>

      <Step
        number={4}
        title="Send errors from Sentry"
        done={done.webhook}
        open={open === 'webhook'}
        summary={done.webhook ? 'Webhook URL created' : undefined}
        onEdit={() => setEditing('webhook')}
      >
        <div className="space-y-4">
          <WebhookCreator hasActiveKey={me.has_api_key} onCreated={() => setWebhookCreated(true)} />
          {!webhookCreated && <SentryInstructions />}
        </div>
      </Step>

      <div className="flex flex-wrap items-center justify-between gap-3 pt-4">
        <p className="text-[0.8125rem] text-ink-3">{complete ? 'Setup complete. New errors will appear on the Incidents page.' : 'You can finish these steps later from Integrations.'}</p>
        <ButtonLink href="/dashboard" variant={complete ? 'primary' : 'secondary'}>
          {complete ? 'Go to incidents' : 'Skip to the dashboard'}
        </ButtonLink>
      </div>
    </div>
  )
}

function Step({
  number,
  title,
  done,
  open,
  locked = false,
  summary,
  onEdit,
  children,
}: {
  number: number
  title: string
  done: boolean
  open: boolean
  locked?: boolean
  summary?: string
  onEdit: () => void
  children: ReactNode
}) {
  return (
    <section
      aria-labelledby={`step-${number}`}
      className={cn('rounded-lg border bg-sheet transition-colors', open ? 'border-rule-strong' : 'border-rule')}
      aria-current={open ? 'step' : undefined}
    >
      <div className="flex items-center gap-4 px-5 py-4">
        <span
          aria-hidden
          className={cn(
            'tabular flex size-7 shrink-0 items-center justify-center rounded-full border text-[0.8125rem] font-semibold',
            done ? 'border-fixed bg-fixed text-sheet' : open ? 'border-ink text-ink' : 'border-rule-strong text-ink-3',
          )}
        >
          {done ? <Check className="size-4" strokeWidth={2.5} /> : number}
        </span>
        <div className="min-w-0 flex-1">
          <h2 id={`step-${number}`} className={cn('text-[0.9375rem] font-semibold', done || open ? 'text-ink' : 'text-ink-2')}>
            {title}
            {done && <span className="sr-only"> (done)</span>}
          </h2>
          {!open && summary && <p className="truncate font-mono text-[0.8125rem] text-ink-3">{summary}</p>}
          {!open && locked && <p className="text-[0.8125rem] text-ink-3">Connect GitHub first.</p>}
        </div>
        {!open && !locked && (
          <Button variant="ghost" size="sm" onClick={onEdit}>
            {done ? 'Edit' : 'Set up'}
          </Button>
        )}
      </div>
      {open && !locked && <div className="border-t border-rule px-5 pb-5 pt-4">{children}</div>}
    </section>
  )
}

function ProfileStep({ name, setName, onSaved }: { name: string; setName: (value: string) => void; onSaved: () => void }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    const result = await saveProfile(name)
    setPending(false)
    if (!result.ok) {
      setError(result.error)
      return
    }
    onSaved()
  }

  return (
    <form onSubmit={save}>
      <Field id="onboarding-name" label="Name" hint="Shown in the dashboard." error={error}>
        <div className="flex gap-2">
          <Input
            id="onboarding-name"
            autoComplete="name"
            autoFocus
            maxLength={100}
            value={name}
            onChange={(event) => setName(event.target.value)}
            aria-describedby={describedBy('onboarding-name', error)}
            aria-invalid={Boolean(error) || undefined}
            className="min-w-0 flex-1"
          />
          <Button type="submit" loading={pending} disabled={!name.trim()}>
            Continue
          </Button>
        </div>
      </Field>
    </form>
  )
}
