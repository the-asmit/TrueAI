'use client'

import { RefreshCw, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { deleteIncident, reanalyzeIncident, setIncidentStatus, syncIncidentPullRequest } from '@/app/actions/incidents'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import type { IncidentStatus } from '@/lib/api/types'

type Busy = null | 'resolve' | 'ignore' | 'reopen' | 'rerun'

export function IncidentActions({ id, status, prOpen }: { id: string; status: IncidentStatus; prOpen: boolean }) {
  const [busy, setBusy] = useState<Busy>(null)
  const [error, setError] = useState<string | null>(null)
  const synced = useRef(false)

  // Pull request state is refreshed from GitHub once per visit while it is open.
  useEffect(() => {
    if (!prOpen || synced.current) return
    synced.current = true
    void syncIncidentPullRequest(id)
  }, [id, prOpen])

  const working = status === 'queued' || status === 'processing'

  // Successful actions refresh the page from the server themselves (refresh() in the action).
  async function run(kind: Exclude<Busy, null>, work: () => Promise<{ ok: boolean; error?: string }>) {
    setBusy(kind)
    setError(null)
    const result = await work()
    if (!result.ok) setError(result.error ?? 'Something went wrong.')
    setBusy(null)
  }

  if (working) {
    return <p className="text-[0.8125rem] text-ink-3">Actions are available once the analysis finishes.</p>
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {status !== 'resolved' && (
          <Button variant="secondary" size="sm" loading={busy === 'resolve'} disabled={busy !== null} onClick={() => run('resolve', () => setIncidentStatus(id, 'resolved'))}>
            Mark resolved
          </Button>
        )}
        {status !== 'ignored' && status !== 'resolved' && (
          <Button variant="ghost" size="sm" loading={busy === 'ignore'} disabled={busy !== null} onClick={() => run('ignore', () => setIncidentStatus(id, 'ignored'))}>
            Ignore
          </Button>
        )}
        {(status === 'resolved' || status === 'ignored') && (
          <Button variant="secondary" size="sm" loading={busy === 'reopen'} disabled={busy !== null} onClick={() => run('reopen', () => setIncidentStatus(id, 'flagged'))}>
            Reopen
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          icon={<RefreshCw />}
          loading={busy === 'rerun'}
          disabled={busy !== null}
          onClick={() => run('rerun', () => reanalyzeIncident(id))}
        >
          Run analysis again
        </Button>
        <ConfirmDialog
          trigger={
            <Button variant="ghost" size="sm" icon={<Trash2 />} disabled={busy !== null} className="text-ink-3 hover:text-failure">
              Delete
            </Button>
          }
          title="Delete this incident?"
          description="The incident, its analysis and its timeline are deleted. Any pull request already opened on GitHub stays there."
          confirmLabel="Delete incident"
          destructive
          onConfirm={async () => {
            // On success the action redirects to the incident list.
            const result = await deleteIncident(id)
            return result && !result.ok ? result.error : null
          }}
        />
      </div>
      {error && (
        <p role="alert" className="text-[0.8125rem] text-failure">
          {error}
        </p>
      )}
    </div>
  )
}
