import { ArrowLeft, GitPullRequest } from 'lucide-react'

import { ToneMark } from '@/components/ui/status'

/*
 * Static figures for the How it works and Security pages. Each one shows a
 * part of the product the landing page doesn't, and is labelled as an example.
 */

const FIGURE = 'overflow-hidden rounded-xl border border-rule bg-sheet shadow-[var(--shadow-sheet)]'
const CAPTION = 'border-t border-rule px-5 py-2.5 text-[0.75rem] text-ink-3 sm:px-7'

const PR_FACTS = [
  ['Error', 'KeyError'],
  ['Environment', 'production'],
  ['Category', 'Code bug · high severity'],
  ['Root-cause confidence', '91%'],
  ['Review confidence', '88%'],
  ['Risk', 'low'],
] as const

const PR_SECTIONS = ['Error message', 'Root cause', 'Explanation', 'What this change does', 'Automated review', 'Files changed']

/** The shape of every pull request TrueAI opens: branch, label and the description's summary and sections. */
export function PullRequestPreview() {
  return (
    <figure aria-labelledby="pr-preview-caption" className={FIGURE}>
      <div className="border-b border-rule px-5 py-5 sm:px-7">
        <p className="flex min-w-0 items-start gap-2.5 text-[1.0625rem] font-semibold leading-snug text-ink">
          <GitPullRequest className="mt-0.5 size-5 shrink-0 text-review" aria-hidden />
          <span>
            Fall back to the account currency on older invoices <span className="font-mono font-normal text-ink-3">#87</span>
          </span>
        </p>
        <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1.5 font-mono text-[0.75rem] text-ink-2">
          <span className="rounded bg-sunken px-1.5 py-0.5">main</span>
          <ArrowLeft className="size-3.5 text-ink-3" aria-label="from" />
          <span className="rounded bg-sunken px-1.5 py-0.5">trueai/fix-3f9a2c1e</span>
          <span className="ml-1 rounded-full border border-rule-strong px-2 py-0.5 font-sans text-[0.6875rem] font-medium text-ink-2">trueai</span>
        </p>
      </div>

      <div className="space-y-5 px-5 py-6 sm:px-7">
        <p className="text-[0.9375rem] font-semibold text-ink">Automated fix proposed by TrueAI</p>
        <p className="rounded-md border-l-2 border-review bg-review-tint px-3 py-2 text-[0.8125rem] leading-relaxed text-ink-2">
          This change was written and reviewed by AI. Review it like any other contribution before merging.
        </p>
        <dl className="divide-y divide-rule rounded-lg border border-rule text-[0.8125rem]">
          {PR_FACTS.map(([label, value]) => (
            <div key={label} className="grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)] gap-3 px-3 py-2">
              <dt className="font-medium text-ink">{label}</dt>
              <dd className="text-ink-2">{value}</dd>
            </div>
          ))}
        </dl>
        <ul className="flex flex-wrap gap-2" aria-label="Sections of the description">
          {PR_SECTIONS.map((section) => (
            <li key={section} className="rounded-md bg-sunken px-2.5 py-1 text-[0.75rem] font-medium text-ink-2">
              {section}
            </li>
          ))}
        </ul>
      </div>

      <figcaption id="pr-preview-caption" className={CAPTION}>
        Example: the layout of every pull request TrueAI opens.
      </figcaption>
    </figure>
  )
}

const NEXT_STEPS = [
  'Renew the TLS certificate for api.payments.example.com.',
  'Install the full certificate chain on the server, not only the leaf certificate.',
  'Retry a refund from the admin panel to confirm the error is gone.',
]

/** An incident TrueAI hands back to you: why there is no pull request, and what to do instead. */
export function NextStepsExample() {
  return (
    <figure aria-labelledby="next-steps-caption" className={FIGURE}>
      <div className="border-b border-rule px-5 py-5 sm:px-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="font-mono text-[1.125rem] font-semibold text-ink">SSLError</p>
          <ToneMark tone="human" label="Needs you" />
        </div>
        <p className="mt-1 text-[0.875rem] leading-relaxed text-ink-2">certificate verify failed: certificate has expired (api.payments.example.com)</p>
      </div>
      <div className="space-y-5 px-5 py-5 sm:px-7">
        <div>
          <p className="text-[0.8125rem] font-semibold text-ink">Why there is no pull request</p>
          <p className="mt-1.5 text-[0.875rem] leading-relaxed text-ink-2">
            The payment provider’s certificate has expired. Your code is correct; the server it talks to needs attention.
          </p>
        </div>
        <div>
          <p className="text-[0.8125rem] font-semibold text-ink">What to do</p>
          <ol className="mt-2 list-decimal space-y-2 pl-5 text-[0.875rem] leading-relaxed text-ink-2 marker:text-ink-3">
            {NEXT_STEPS.map((step) => (
              <li key={step} className="pl-1">{step}</li>
            ))}
          </ol>
        </div>
      </div>
      <figcaption id="next-steps-caption" className={CAPTION}>
        Example: an infrastructure incident, handed back with next steps.
      </figcaption>
    </figure>
  )
}

const REDACTIONS = [
  { field: 'Authorization', sent: 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIi…', kept: '[Filtered]' },
  { field: 'Cookie', sent: 'sessionid=k3j9x2w8q1…', kept: '[Filtered]' },
  { field: 'card_number', sent: '4111 1111 1111 1111', kept: '[Filtered]' },
  { field: 'message', sent: 'Refund failed for priya@example.com', kept: 'Refund failed for [email]' },
  { field: 'url', sent: '/reset?token=9fK2xQ…&lang=en', kept: '/reset?token=[Filtered]&lang=en' },
  { field: 'User-Agent', sent: 'Mozilla/5.0 (Macintosh)', kept: 'Mozilla/5.0 (Macintosh)' },
]

/** Fields of a Sentry event before and after TrueAI removes private data. */
export function RedactionExample() {
  return (
    <figure aria-labelledby="redaction-caption" className={FIGURE}>
      {/* Three columns from sm up; on phones each field stacks, with its own "sent" and "kept" labels. */}
      <p aria-hidden className="hidden grid-cols-[8rem_minmax(0,1fr)_minmax(0,1fr)] gap-4 border-b border-rule px-7 py-3 text-[0.75rem] font-medium text-ink-3 sm:grid">
        <span>Field</span>
        <span>As Sentry sent it</span>
        <span>As TrueAI keeps it</span>
      </p>
      <ul className="divide-y divide-rule font-mono text-[0.75rem]">
        {REDACTIONS.map((row) => (
          <li key={row.field} className="grid gap-1 px-5 py-3 sm:grid-cols-[8rem_minmax(0,1fr)_minmax(0,1fr)] sm:gap-4 sm:px-7 sm:py-2.5">
            <span className="text-ink-3">{row.field}</span>
            <span className="text-ink-2 [overflow-wrap:anywhere]">
              <span className="font-sans text-ink-3 sm:sr-only">Sentry sent: </span>
              {row.sent}
            </span>
            <span className={`[overflow-wrap:anywhere] ${row.kept === row.sent ? 'text-ink-2' : 'font-semibold text-ink'}`}>
              <span className="font-sans font-normal text-ink-3 sm:sr-only">TrueAI keeps: </span>
              {row.kept}
            </span>
          </li>
        ))}
      </ul>
      <figcaption id="redaction-caption" className={CAPTION}>
        Example: how an event’s fields are rewritten before it is stored.
      </figcaption>
    </figure>
  )
}
