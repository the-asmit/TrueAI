import { ArrowLeft, ExternalLink, GitPullRequest } from 'lucide-react'
import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import type { ReactNode } from 'react'

import { AutoRefresh } from '@/components/auto-refresh'
import { DiffView } from '@/components/report/diff-view'
import { IncidentActions } from '@/components/report/incident-actions'
import { Prose } from '@/components/report/prose'
import { ButtonLink } from '@/components/ui/button'
import { Meta, ReportSection } from '@/components/ui/misc'
import { Notice } from '@/components/ui/notice'
import { SeverityMark, StatusMark } from '@/components/ui/status'
import { api, ApiError, toMessage } from '@/lib/api/client'
import type { Analysis, IncidentDetail, PullRequestInfo } from '@/lib/api/types'
import { formatCount, formatPercent, formatRelative, formatUtc, shortId } from '@/lib/format'
import { CLASSIFICATION, isActive } from '@/lib/incidents'
import { cn } from '@/lib/utils'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

async function loadIncident(id: string): Promise<{ incident: IncidentDetail | null; error: string | null }> {
  if (!UUID.test(id)) return { incident: null, error: null }
  try {
    return { incident: await api.get<IncidentDetail>(`/incidents/${id}`), error: null }
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) return { incident: null, error: null }
    return { incident: null, error: toMessage(error, 'The incident could not be loaded.') }
  }
}

export async function generateMetadata({ params }: PageProps<'/dashboard/incidents/[id]'>): Promise<Metadata> {
  const { id } = await params
  return { title: `Incident ${shortId(id)}` }
}

export default async function IncidentReportPage({ params }: PageProps<'/dashboard/incidents/[id]'>) {
  const { id } = await params
  const { incident, error } = await loadIncident(id)

  if (error) {
    return (
      <div className="mx-auto max-w-[980px] px-4 py-10 sm:px-8">
        <BackLink />
        <Notice kind="error" title="This incident could not be loaded" className="mt-6" action={<ButtonLink href={`/dashboard/incidents/${id}`} variant="secondary" size="sm">Try again</ButtonLink>}>
          {error}
        </Notice>
      </div>
    )
  }
  if (!incident) notFound()

  const active = isActive(incident.status)
  // A finished incident without a report was handled by an earlier version of TrueAI.
  const legacy = !active && incident.status !== 'failed' && !incident.analysis
  const pr = incident.pull_request
  const sections = buildSections(incident)

  return (
    <div className="mx-auto max-w-[980px] px-4 pb-20 pt-6 sm:px-8 sm:pt-8">
      <AutoRefresh active={active} fastMs={3000} slowMs={60000} />
      <BackLink />

      {/* ---- Report header ---- */}
      <header className="mt-5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <StatusMark status={incident.status} />
          <span className="font-mono text-[0.75rem] text-ink-3">Incident {shortId(incident.id)}</span>
        </div>
        <h1 className="mt-3 break-words font-mono text-[1.625rem] font-semibold leading-tight tracking-[-0.02em] text-ink sm:text-[2rem]">
          {incident.error_type || 'Unknown error'}
        </h1>
        {incident.error_message && <p className="mt-2 max-w-[75ch] break-words text-[0.9375rem] leading-relaxed text-ink-2">{incident.error_message}</p>}

        <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 rounded-lg border border-rule bg-sheet px-5 py-4 sm:grid-cols-4">
          <Meta label="Severity">
            <SeverityMark severity={incident.severity} />
          </Meta>
          <Meta label="Classification">{incident.issue_classification ? CLASSIFICATION[incident.issue_classification] : '—'}</Meta>
          <Meta label="Environment">{incident.environment || '—'}</Meta>
          <Meta label="Occurrences">
            <span className="tabular">{formatCount(incident.occurrence_count)}</span>
          </Meta>
          <Meta label="First seen">
            <time dateTime={incident.created_at} title={formatUtc(incident.created_at)}>
              {formatRelative(incident.created_at)}
            </time>
          </Meta>
          <Meta label="Last seen">
            <time dateTime={incident.last_seen_at ?? incident.created_at} title={formatUtc(incident.last_seen_at ?? incident.created_at)}>
              {formatRelative(incident.last_seen_at ?? incident.created_at)}
            </time>
          </Meta>
          <Meta label="Repository" className="col-span-2">
            {incident.repo_full_name ? (
              <span className="font-mono">
                {incident.repo_full_name}
                {incident.branch && <span className="text-ink-3">@{incident.branch}</span>}
              </span>
            ) : (
              <span className="text-ink-3">{active ? 'Not resolved yet' : 'None — no repository was available'}</span>
            )}
          </Meta>
          {incident.culprit && (
            <Meta label="Raised in" className="col-span-2 sm:col-span-4">
              <span className="font-mono">{incident.culprit}</span>
            </Meta>
          )}
        </dl>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <IncidentActions id={incident.id} status={incident.status} prOpen={pr?.status === 'open'} />
          {incident.sentry_issue_url && (
            <a href={incident.sentry_issue_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-[0.8125rem] text-ink-2 underline hover:text-ink">
              Open in Sentry <ExternalLink className="size-3.5" aria-hidden />
            </a>
          )}
        </div>
      </header>

      {/* ---- Body ---- */}
      <div className="mt-10 space-y-10">
        {active && (
          <Notice kind="info" title={incident.status === 'queued' ? 'Waiting to be analysed' : 'TrueAI is working on this incident'}>
            {incident.current_step ? `${incident.current_step}. ` : ''}This page updates by itself; most incidents finish in under a minute.
          </Notice>
        )}
        {incident.status === 'failed' && (
          <Notice kind="error" title="The analysis could not finish">
            {incident.pipeline_error || 'An unexpected error stopped the analysis.'} Use “Run analysis again” once the cause is fixed.
          </Notice>
        )}
        {legacy && (
          <Notice kind="info" title="Analysed by an earlier version of TrueAI">
            This incident has no report. Use “Run analysis again” for a full report.
          </Notice>
        )}

        {sections.map((section, index) => (
          <ReportSection key={section.id} id={section.id} number={`${index + 1}`} title={section.title} aside={section.aside}>
            {section.body}
          </ReportSection>
        ))}

        {(incident.completed_at || incident.sentry_event_id) && (
          <p className="tabular border-t border-rule pt-4 text-[0.75rem] text-ink-3">
            {incident.completed_at && <>Analysed {formatUtc(incident.completed_at)}</>}
            {incident.completed_at && incident.sentry_event_id && ' · '}
            {incident.sentry_event_id && <>Sentry event <span className="font-mono">{incident.sentry_event_id}</span></>}
          </p>
        )}
      </div>
    </div>
  )
}

// ================================================================== //
// Sections, ordered by what the reader needs for this outcome           //
// ================================================================== //

interface Section {
  id: string
  title: string
  aside?: ReactNode
  body: ReactNode
}

function buildSections(incident: IncidentDetail): Section[] {
  const analysis = incident.analysis
  const pr = incident.pull_request
  const sections: Section[] = []

  if (analysis?.root_cause) {
    sections.push({
      id: 'summary',
      title: 'Summary',
      aside: <Confidence analysis={analysis} />,
      body: <Summary incident={incident} analysis={analysis} />,
    })
  }

  const steps = analysis?.remediation?.steps ?? []
  const nextSteps: Section | null =
    steps.length > 0
      ? {
          id: 'next-steps',
          title: 'What to do next',
          body: <NextSteps analysis={analysis!} />,
        }
      : null
  const fix: Section | null =
    analysis?.fix_diff
      ? {
          id: 'fix',
          title: pr ? 'The fix' : 'Suggested patch',
          aside: analysis.risk ? <span className="text-[0.8125rem] text-ink-3">Risk: {analysis.risk}</span> : undefined,
          body: <Fix analysis={analysis} pr={pr} />,
        }
      : null

  if (incident.status === 'flagged') {
    if (nextSteps) sections.push(nextSteps)
    if (fix) sections.push(fix)
  } else {
    if (fix) sections.push(fix)
    if (nextSteps) sections.push(nextSteps)
  }

  if (analysis?.review_verdict || (analysis?.policy_violations?.length ?? 0) > 0) {
    sections.push({ id: 'review', title: 'Review', body: <Review analysis={analysis!} /> })
  }
  if (analysis?.explanation) {
    sections.push({
      id: 'explanation',
      title: 'How it happened',
      body: (
        <p className="max-w-[75ch] whitespace-pre-line text-[0.9375rem] leading-[1.7] text-ink-2">
          <Prose text={analysis.explanation} />
        </p>
      ),
    })
  }
  if (incident.stack_trace && incident.stack_trace.length > 0) {
    sections.push({ id: 'stack', title: 'Stack trace', aside: <span className="text-[0.75rem] text-ink-3">Application frames, crash site last</span>, body: <StackTrace incident={incident} /> })
  }
  return sections
}

function Summary({ incident, analysis }: { incident: IncidentDetail; analysis: Analysis }) {
  return (
    <div className="space-y-4">
      <p className="max-w-[70ch] text-[1.0625rem] font-medium leading-[1.6] text-ink">
        <Prose text={analysis.root_cause ?? ''} />
      </p>
      {incident.status === 'flagged' && analysis.flag_reason && (
        <Notice kind="warning" title="Why a human is needed">
          <Prose text={analysis.flag_reason} />
        </Notice>
      )}
    </div>
  )
}

function Confidence({ analysis }: { analysis: Analysis }) {
  return (
    <dl className="flex gap-5 text-right">
      <div>
        <dt className="text-[0.75rem] text-ink-3">Root cause</dt>
        <dd className="tabular text-[0.9375rem] font-semibold text-ink">{formatPercent(analysis.confidence)}</dd>
      </div>
      {analysis.fix_confidence !== null && (
        <div>
          <dt className="text-[0.75rem] text-ink-3">Review</dt>
          <dd className="tabular text-[0.9375rem] font-semibold text-ink">{formatPercent(analysis.fix_confidence)}</dd>
        </div>
      )}
    </dl>
  )
}

function Fix({ analysis, pr }: { analysis: Analysis; pr: PullRequestInfo | null }) {
  return (
    <div className="space-y-5">
      {pr ? (
        <PullRequestCard pr={pr} />
      ) : (
        <p className="max-w-[75ch] text-[0.8125rem] text-ink-2">
          This patch was written and checked but not opened as a pull request. Apply it yourself if it looks right.
        </p>
      )}
      {analysis.summary && (
        <p className="text-[0.9375rem] font-semibold text-ink">
          <Prose text={analysis.summary} />
        </p>
      )}
      {analysis.rationale && (
        <p className="max-w-[75ch] text-[0.9375rem] leading-[1.7] text-ink-2">
          <Prose text={analysis.rationale} />
        </p>
      )}
      <DiffView diff={analysis.fix_diff ?? ''} caption={`Figure: ${analysis.files_changed.length === 1 ? 'the change' : `${analysis.files_changed.length} files changed`}, exactly as committed.`} />
    </div>
  )
}

function PullRequestCard({ pr }: { pr: PullRequestInfo }) {
  const tone = pr.status === 'merged' ? 'text-fixed' : pr.status === 'closed' ? 'text-ink-3' : 'text-review'
  const label = pr.status === 'merged' ? 'Merged' : pr.status === 'closed' ? 'Closed without merging' : 'Open, awaiting review'
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-rule bg-sheet px-4 py-3.5">
      <div className="flex min-w-0 items-start gap-3">
        <GitPullRequest className={cn('mt-0.5 size-4 shrink-0', tone)} aria-hidden />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">
            {pr.title || 'Fix pull request'} <span className="font-normal text-ink-3">#{pr.pr_number}</span>
          </p>
          <p className="mt-0.5 text-[0.8125rem] text-ink-2">
            <span className={tone}>{label}</span>
            {pr.repo_full_name && <> · <span className="font-mono">{pr.repo_full_name}</span></>} · <span className="font-mono">{pr.branch_name}</span>
          </p>
        </div>
      </div>
      <a href={pr.pr_url} target="_blank" rel="noopener noreferrer" className="inline-flex h-8 items-center gap-2 rounded-md bg-action px-3 text-[0.8125rem] font-medium text-on-action hover:bg-action-hover">
        {pr.status === 'open' ? 'Review on GitHub' : 'View on GitHub'} <ExternalLink className="size-3.5" aria-hidden />
      </a>
    </div>
  )
}

function NextSteps({ analysis }: { analysis: Analysis }) {
  const remediation = analysis.remediation!
  return (
    <div className="space-y-5">
      {remediation.summary && (
        <p className="max-w-[75ch] text-[0.9375rem] leading-[1.7] text-ink">
          <Prose text={remediation.summary} />
        </p>
      )}
      <ol className="max-w-[75ch] space-y-3">
        {remediation.steps.map((step, index) => (
          <li key={index} className="grid grid-cols-[1.75rem_1fr] text-[0.9375rem] leading-[1.65] text-ink-2">
            <span className="tabular text-[0.8125rem] leading-[1.9] text-ink-3">{index + 1}.</span>
            <span className="min-w-0 whitespace-pre-line break-words">
              <Prose text={step} />
            </span>
          </li>
        ))}
      </ol>
      {(remediation.verification || remediation.prevention) && (
        <dl className="grid max-w-[75ch] gap-4 sm:grid-cols-2">
          {remediation.verification && (
            <div>
              <dt className="text-[0.8125rem] font-semibold text-ink">Confirm it is fixed</dt>
              <dd className="mt-1 text-[0.8125rem] leading-relaxed text-ink-2">
                <Prose text={remediation.verification} />
              </dd>
            </div>
          )}
          {remediation.prevention && (
            <div>
              <dt className="text-[0.8125rem] font-semibold text-ink">Prevent a repeat</dt>
              <dd className="mt-1 text-[0.8125rem] leading-relaxed text-ink-2">
                <Prose text={remediation.prevention} />
              </dd>
            </div>
          )}
        </dl>
      )}
      {remediation.fallback && <p className="text-[0.75rem] text-ink-3">A standard checklist: tailored steps could not be written for this run.</p>}
    </div>
  )
}

function Review({ analysis }: { analysis: Analysis }) {
  const verdict = analysis.review_verdict
  const verdictText =
    verdict === 'approve' ? 'Approved in review' : verdict === 'reject' ? 'Rejected in review' : verdict === 'revise' ? 'Changes requested in review' : null
  return (
    <div className="space-y-4">
      {verdictText && (
        <p className={cn('text-[0.9375rem] font-semibold', verdict === 'approve' ? 'text-fixed' : verdict === 'reject' ? 'text-failure' : 'text-human')}>{verdictText}</p>
      )}
      {analysis.review_notes && (
        <p className="max-w-[75ch] whitespace-pre-line text-[0.9375rem] leading-[1.7] text-ink-2">
          <Prose text={analysis.review_notes} />
        </p>
      )}
      {analysis.policy_violations.length > 0 && (
        <Notice kind="warning" title="Blocked by the safety policy">
          <ul className="list-disc space-y-1 pl-4">
            {analysis.policy_violations.map((violation) => (
              <li key={violation}>{violation}</li>
            ))}
          </ul>
        </Notice>
      )}
    </div>
  )
}

function StackTrace({ incident }: { incident: IncidentDetail }) {
  const frames = incident.stack_trace ?? []
  return (
    <ol className="overflow-hidden rounded-lg border border-rule bg-sheet font-mono text-[0.8125rem]">
      {frames.map((frame, index) => {
        const crash = index === frames.length - 1
        return (
          <li key={index} className={cn('border-b border-rule px-4 py-2.5 last:border-b-0', crash && 'bg-failure-tint/60')}>
            <p className="break-all text-ink">
              {frame.filename || '?'}
              <span className="text-ink-3">:{frame.lineno ?? '?'}</span> <span className="text-ink-2">in {frame.function || '?'}()</span>
              {crash && <span className="ml-2 font-sans text-[0.75rem] font-semibold text-failure">crash site</span>}
            </p>
            {frame.context_line && <pre className="mt-1 overflow-x-auto whitespace-pre text-[0.75rem] text-ink-2">{frame.context_line.trim()}</pre>}
          </li>
        )
      })}
    </ol>
  )
}

function BackLink() {
  return (
    <Link href="/dashboard" className="inline-flex items-center gap-1.5 text-[0.8125rem] text-ink-2 hover:text-ink">
      <ArrowLeft className="size-4" aria-hidden /> Incidents
    </Link>
  )
}
