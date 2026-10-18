import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import type { Metadata } from 'next'
import Link from 'next/link'

import { AutoRefresh } from '@/components/auto-refresh'
import { ButtonLink } from '@/components/ui/button'
import { Input } from '@/components/ui/field'
import { EmptyState } from '@/components/ui/misc'
import { Notice } from '@/components/ui/notice'
import { SeverityMark, StatusMark } from '@/components/ui/status'
import { api, toMessage } from '@/lib/api/client'
import type { IncidentList, IncidentStats, IncidentStatus, Me } from '@/lib/api/types'
import { formatCount, formatRelative, shortId } from '@/lib/format'
import { CLASSIFICATION, isActive, STATUS } from '@/lib/incidents'
import { cn } from '@/lib/utils'

export const metadata: Metadata = { title: 'Incidents' }

const TABS: { key: IncidentStatus | 'all'; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'flagged', label: 'Needs you' },
  { key: 'pr_open', label: 'Pull request open' },
  { key: 'processing', label: 'Analysing' },
  { key: 'queued', label: 'Queued' },
  { key: 'failed', label: 'Failed' },
  { key: 'resolved', label: 'Resolved' },
  { key: 'ignored', label: 'Ignored' },
]

const PAGE_SIZE = 25

export default async function IncidentsPage({ searchParams }: PageProps<'/dashboard'>) {
  const params = await searchParams
  const status = typeof params.status === 'string' && params.status in STATUS ? (params.status as IncidentStatus) : null
  const q = typeof params.q === 'string' ? params.q.slice(0, 100) : ''
  const page = Math.max(1, Number.parseInt(typeof params.page === 'string' ? params.page : '1', 10) || 1)

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
  if (status) query.set('status', status)
  if (q) query.set('q', q)

  const [listResult, stats, me] = await Promise.all([
    api.get<IncidentList>(`/incidents?${query}`).then(
      (data) => ({ data, error: null as string | null }),
      (error) => ({ data: null, error: toMessage(error, 'Could not load incidents.') }),
    ),
    api.get<IncidentStats>('/incidents/stats').catch(() => null),
    api.get<Me>('/auth/me').catch(() => null),
  ])

  const list = listResult.data
  // Server component: it renders once per request, so "3 minutes ago" is relative to when the data was fetched.
  // eslint-disable-next-line react-hooks/purity -- never re-rendered on the client
  const renderedAt = Date.now()
  const counts = stats?.by_status ?? {}
  const anyActive = Boolean(list?.items.some((incident) => isActive(incident.status))) || (counts.queued ?? 0) + (counts.processing ?? 0) > 0

  const hrefFor = (next: { status?: string | null; q?: string; page?: number }) => {
    const search = new URLSearchParams()
    const nextStatus = next.status === undefined ? status : next.status
    const nextQ = next.q === undefined ? q : next.q
    if (nextStatus) search.set('status', nextStatus)
    if (nextQ) search.set('q', nextQ)
    if (next.page && next.page > 1) search.set('page', String(next.page))
    const text = search.toString()
    return text ? `/dashboard?${text}` : '/dashboard'
  }

  return (
    <div className="mx-auto max-w-[1180px] px-4 pb-16 pt-6 sm:px-8 sm:pt-10">
      <AutoRefresh active={anyActive} />

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-[-0.02em] text-ink">Incidents</h1>
          <p className="mt-1 text-sm text-ink-2">
            {stats ? (
              <>
                {formatCount(stats.total)} recorded
                {(counts.flagged ?? 0) > 0 && <> · <span className="font-medium text-human">{formatCount(counts.flagged)} need you</span></>}
                {(counts.pr_open ?? 0) > 0 && <> · {formatCount(counts.pr_open)} pull requests waiting for review</>}
              </>
            ) : (
              'Errors from Sentry, investigated by TrueAI.'
            )}
          </p>
        </div>
        <form action="/dashboard" method="get" role="search" className="relative w-full sm:w-72">
          {status && <input type="hidden" name="status" value={status} />}
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
          <label htmlFor="incident-search" className="sr-only">
            Search incidents
          </label>
          <Input id="incident-search" name="q" type="search" defaultValue={q} placeholder="Search error, message or file" className="pl-9" />
        </form>
      </header>

      {me && !me.onboarding_complete && <SetupNotice me={me} />}

      <nav aria-label="Filter by status" className="-mx-4 mt-6 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <ul className="flex min-w-max gap-1 border-b border-rule">
          {TABS.map((tab) => {
            const selected = (tab.key === 'all' && !status) || tab.key === status
            const count = tab.key === 'all' ? stats?.total : counts[tab.key]
            return (
              <li key={tab.key}>
                <Link
                  href={hrefFor({ status: tab.key === 'all' ? null : tab.key, page: 1 })}
                  aria-current={selected ? 'page' : undefined}
                  className={cn(
                    '-mb-px flex h-10 items-center gap-2 border-b-2 px-3 text-sm transition-colors',
                    selected ? 'border-ink font-medium text-ink' : 'border-transparent text-ink-2 hover:text-ink',
                  )}
                >
                  {tab.label}
                  {count !== undefined && count > 0 && <span className="tabular text-[0.75rem] text-ink-3">{formatCount(count)}</span>}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="mt-4">
        {listResult.error ? (
          <Notice kind="error" title="Incidents could not be loaded" action={<ButtonLink href={hrefFor({})} variant="secondary" size="sm">Try again</ButtonLink>}>
            {listResult.error}
          </Notice>
        ) : !list || list.items.length === 0 ? (
          <EmptyResult status={status} q={q} total={stats?.total ?? 0} clearHref={hrefFor({ status: null, q: '', page: 1 })} />
        ) : (
          <>
            <IncidentTable list={list} now={renderedAt} />
            <Pagination list={list} hrefFor={hrefFor} />
          </>
        )}
      </div>
    </div>
  )
}

function IncidentTable({ list, now }: { list: IncidentList; now: number }) {
  return (
    <div className="overflow-hidden rounded-lg border border-rule bg-sheet">
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">Incidents, most recently seen first</caption>
        <thead className="border-b border-rule bg-sunken/60 text-[0.75rem] text-ink-3">
          <tr>
            <th scope="col" className="px-4 py-2.5 font-medium">Incident</th>
            <th scope="col" className="hidden px-4 py-2.5 font-medium md:table-cell">Status</th>
            <th scope="col" className="hidden px-4 py-2.5 font-medium lg:table-cell">Severity</th>
            <th scope="col" className="hidden px-4 py-2.5 text-right font-medium sm:table-cell">Seen</th>
          </tr>
        </thead>
        <tbody>
          {list.items.map((incident) => (
            <tr key={incident.id} className="group relative border-b border-rule last:border-b-0 hover:bg-sunken/50 focus-within:bg-sunken/50">
              <td className="px-4 py-3 align-top">
                <div className="flex items-baseline gap-2">
                  <Link
                    href={`/dashboard/incidents/${incident.id}`}
                    className="min-w-0 truncate font-mono text-[0.8125rem] font-semibold text-ink after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
                  >
                    {incident.error_type || 'Unknown error'}
                  </Link>
                  <span className="shrink-0 font-mono text-[0.75rem] text-ink-3">{shortId(incident.id)}</span>
                </div>
                {incident.error_message && <p className="mt-0.5 line-clamp-1 max-w-[62ch] text-[0.8125rem] text-ink-2">{incident.error_message}</p>}
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.75rem] text-ink-3">
                  <span className="md:hidden">
                    <StatusMark status={incident.status} className="text-[0.75rem]" />
                  </span>
                  <span className="sm:hidden">{formatRelative(incident.last_seen_at ?? incident.created_at, now)}</span>
                  {incident.issue_classification && <span>{CLASSIFICATION[incident.issue_classification]}</span>}
                  {incident.environment && <span>{incident.environment}</span>}
                  {incident.repo_full_name && <span className="font-mono">{incident.repo_full_name}</span>}
                  {incident.culprit && <span className="hidden max-w-[40ch] truncate font-mono xl:inline">{incident.culprit}</span>}
                </p>
                {(incident.status === 'processing' || incident.status === 'queued') && incident.current_step && (
                  <p className="mt-1 text-[0.75rem] text-ink-2">{incident.current_step}…</p>
                )}
              </td>
              <td className="hidden whitespace-nowrap px-4 py-3 align-top md:table-cell">
                <StatusMark status={incident.status} />
              </td>
              <td className="hidden px-4 py-3 align-top lg:table-cell">
                <SeverityMark severity={incident.severity} />
              </td>
              <td className="hidden whitespace-nowrap px-4 py-3 text-right align-top text-[0.8125rem] sm:table-cell">
                <span className="text-ink-2">{formatRelative(incident.last_seen_at ?? incident.created_at, now)}</span>
                {incident.occurrence_count > 1 && (
                  <span className="tabular block text-[0.75rem] text-ink-3">{formatCount(incident.occurrence_count)} times</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Pagination({ list, hrefFor }: { list: IncidentList; hrefFor: (next: { page?: number }) => string }) {
  if (list.total_pages <= 1) return null
  const first = (list.page - 1) * list.page_size + 1
  const last = Math.min(list.total, list.page * list.page_size)
  return (
    <nav aria-label="Pagination" className="mt-4 flex items-center justify-between text-[0.8125rem] text-ink-2">
      <span className="tabular">
        {formatCount(first)}–{formatCount(last)} of {formatCount(list.total)}
      </span>
      <div className="flex gap-2">
        <ButtonLink
          href={hrefFor({ page: list.page - 1 })}
          variant="secondary"
          size="sm"
          icon={<ChevronLeft />}
          aria-disabled={list.page <= 1}
          tabIndex={list.page <= 1 ? -1 : undefined}
        >
          Newer
        </ButtonLink>
        <ButtonLink
          href={hrefFor({ page: list.page + 1 })}
          variant="secondary"
          size="sm"
          iconEnd={<ChevronRight />}
          aria-disabled={list.page >= list.total_pages}
          tabIndex={list.page >= list.total_pages ? -1 : undefined}
        >
          Older
        </ButtonLink>
      </div>
    </nav>
  )
}

function EmptyResult({ status, q, total, clearHref }: { status: IncidentStatus | null; q: string; total: number; clearHref: string }) {
  if (total === 0 && !status && !q) {
    return (
      <EmptyState
        title="No incidents yet"
        action={
          <>
            <ButtonLink href="/integrations">Set up Sentry</ButtonLink>
            <ButtonLink href="/onboarding" variant="secondary">Setup checklist</ButtonLink>
          </>
        }
      >
        When Sentry reports an error through your webhook, it appears here within seconds and TrueAI starts
        investigating. Nothing to do until then.
      </EmptyState>
    )
  }
  return (
    <EmptyState title={q ? `Nothing matches “${q}”` : `No ${STATUS[status ?? 'queued'].label.toLowerCase()} incidents`} action={<ButtonLink href={clearHref} variant="secondary">Show all incidents</ButtonLink>}>
      {q ? 'Search looks at the error type, the message and the file that raised it.' : STATUS[status ?? 'queued'].description}
    </EmptyState>
  )
}

function SetupNotice({ me }: { me: Me }) {
  const missing = [
    !me.github_connected && 'connect GitHub',
    me.github_connected && !me.github_repo && 'choose a repository',
    !me.has_api_key && 'create your Sentry webhook',
  ].filter(Boolean) as string[]
  if (missing.length === 0) return null

  // Without a webhook nothing arrives; without a repository incidents arrive but can't be fixed in code.
  const receiving = me.has_api_key
  return (
    <Notice
      kind="warning"
      title={receiving ? 'Connect a repository so TrueAI can open fixes' : 'Finish setting up to receive incidents'}
      className="mt-6"
      action={<ButtonLink href="/onboarding" size="sm">Continue setup</ButtonLink>}
    >
      {receiving && 'Incidents are being analysed, but TrueAI can’t read your code or open pull requests yet. '}
      Still to do: {missing.join(', ')}.
    </Notice>
  )
}
