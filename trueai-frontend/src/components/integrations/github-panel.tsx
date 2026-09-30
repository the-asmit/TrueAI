'use client'

import { useState } from 'react'

import { disconnectGitHub, setDefaultRepository, startGitHubConnect } from '@/app/actions/integrations'
import { GitHubMark } from '@/components/brand'
import { BranchSelect } from '@/components/integrations/branch-select'
import { RepoPicker } from '@/components/integrations/repo-picker'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Field } from '@/components/ui/field'
import { Notice } from '@/components/ui/notice'
import type { GitHubRepository } from '@/lib/api/types'

type ReturnPath = '/onboarding' | '/integrations' | '/settings'

export function ConnectGitHubButton({ returnTo, label = 'Connect GitHub', variant = 'primary' }: { returnTo: ReturnPath; label?: string; variant?: 'primary' | 'secondary' }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function connect() {
    setPending(true)
    setError(null)
    const result = await startGitHubConnect(returnTo)
    if (!result.ok) {
      setError(result.error)
      setPending(false)
      return
    }
    window.location.assign(result.data.auth_url)
  }

  return (
    <div className="space-y-2">
      <Button variant={variant} onClick={connect} loading={pending} icon={<GitHubMark />}>
        {label}
      </Button>
      {error && (
        <p role="alert" className="text-[0.8125rem] text-failure">
          {error}
        </p>
      )}
    </div>
  )
}

export function DefaultRepositoryForm({
  initialRepo,
  initialBranch,
  onSaved,
  submitLabel = 'Save repository',
}: {
  initialRepo: string | null
  initialBranch: string | null
  onSaved?: (repo: string, branch: string) => void
  submitLabel?: string
}) {
  const [repo, setRepo] = useState(initialRepo ?? '')
  const [picked, setPicked] = useState<GitHubRepository | null>(null)
  const [branch, setBranch] = useState(initialBranch ?? '')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<{ canPush: boolean } | null>(null)

  const unchanged = repo === (initialRepo ?? '') && branch === (initialBranch ?? '')

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    setSaved(null)
    const result = await setDefaultRepository(repo, branch || undefined)
    setPending(false)
    if (!result.ok) {
      setError(result.error)
      return
    }
    setSaved({ canPush: result.data.can_push })
    onSaved?.(result.data.repo_name, result.data.branch_name)
  }

  return (
    <form onSubmit={save} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-[1fr_14rem]">
        <Field id="default-repo" label="Repository" error={error} hint="TrueAI reads this code and opens fix pull requests on it.">
          <RepoPicker
            id="default-repo"
            value={repo}
            invalid={Boolean(error)}
            describedBy={error ? 'default-repo-error' : 'default-repo-hint'}
            onChange={(next, typed) => {
              setPicked(next)
              setRepo(typed)
              setSaved(null)
            }}
          />
        </Field>
        <Field id="default-branch" label="Branch" hint="Usually your production branch.">
          <BranchSelect id="default-branch" repo={repo} value={branch} onChange={setBranch} />
        </Field>
      </div>
      {picked && !picked.can_push && (
        <Notice kind="warning" title="This account can read but not push to this repository">
          TrueAI will still diagnose incidents, but it cannot open pull requests until the connected GitHub account has write access.
        </Notice>
      )}
      <div className="flex items-center gap-3">
        <Button type="submit" loading={pending} disabled={!repo || unchanged}>
          {submitLabel}
        </Button>
        {saved && (
          <span role="status" className="text-[0.8125rem] text-fixed">
            Saved{saved.canPush ? '' : ' — read-only access, so no pull requests yet'}.
          </span>
        )}
      </div>
    </form>
  )
}

export function DisconnectGitHubButton() {
  return (
    <ConfirmDialog
      trigger={<Button variant="ghost" size="sm" className="text-ink-3 hover:text-failure">Disconnect</Button>}
      title="Disconnect GitHub?"
      description="TrueAI stops reading your code and cannot open pull requests. Its access is revoked on GitHub too. Your repository settings are kept for when you reconnect."
      confirmLabel="Disconnect GitHub"
      destructive
      onConfirm={async () => {
        const result = await disconnectGitHub()
        return result.ok ? null : result.error
      }}
    />
  )
}
