import type { IncidentStatus, IssueClassification, Severity, StepStatus } from '@/lib/api/types'

/**
 * The single vocabulary for incident state. Every status has exactly one
 * label, one colour role and one description — the dashboard, the report
 * and the landing page all read from here.
 */
export type Tone = 'fixed' | 'review' | 'human' | 'failure' | 'working' | 'muted'

export const STATUS: Record<IncidentStatus, { label: string; tone: Tone; description: string }> = {
  queued: { label: 'Queued', tone: 'working', description: 'Received from Sentry and waiting for an analysis worker.' },
  processing: { label: 'Analysing', tone: 'working', description: 'The agents are working on this incident now.' },
  pr_open: { label: 'Pull request open', tone: 'review', description: 'A reviewed fix is waiting for your approval on GitHub.' },
  resolved: { label: 'Resolved', tone: 'fixed', description: 'The fix was merged, or someone marked the incident resolved.' },
  flagged: { label: 'Needs you', tone: 'human', description: 'TrueAI diagnosed it but a human must act; next steps are attached.' },
  failed: { label: 'Analysis failed', tone: 'failure', description: 'The analysis could not finish. You can run it again.' },
  ignored: { label: 'Ignored', tone: 'muted', description: 'Dismissed by a user.' },
}

export const STATUS_ORDER: IncidentStatus[] = ['flagged', 'pr_open', 'processing', 'queued', 'failed', 'resolved', 'ignored']

export const TONE_TEXT: Record<Tone, string> = {
  fixed: 'text-fixed',
  review: 'text-review',
  human: 'text-human',
  failure: 'text-failure',
  working: 'text-ink-2',
  muted: 'text-ink-3',
}

export const TONE_DOT: Record<Tone, string> = {
  fixed: 'bg-fixed',
  review: 'bg-review',
  human: 'bg-human',
  failure: 'bg-failure',
  working: 'bg-ink-3',
  muted: 'bg-rule-strong',
}

export const TONE_TINT: Record<Tone, string> = {
  fixed: 'bg-fixed-tint',
  review: 'bg-review-tint',
  human: 'bg-human-tint',
  failure: 'bg-failure-tint',
  working: 'bg-sunken',
  muted: 'bg-sunken',
}

export const CLASSIFICATION: Record<IssueClassification, string> = {
  code_bug: 'Code bug',
  config_issue: 'Configuration',
  infrastructure: 'Infrastructure',
  data_issue: 'Data',
  dependency: 'Dependency',
}

export const SEVERITY: Record<Severity, { label: string; rank: number }> = {
  critical: { label: 'Critical', rank: 4 },
  high: { label: 'High', rank: 3 },
  medium: { label: 'Medium', rank: 2 },
  low: { label: 'Low', rank: 1 },
}

export const STEP_LABEL: Record<string, string> = {
  parse: 'Read the Sentry event',
  triage: 'Triage Agent',
  context: 'Read the source',
  investigator: 'Investigator Agent',
  fix_engineer: 'Fix Engineer Agent',
  patch: 'Applied and checked the patch',
  reviewer: 'Reviewer Agent',
  decision: 'Decision',
  publish: 'Opened the pull request',
  remediation: 'Remediation Agent',
  complete: 'Outcome',
}

export const STEP_STATUS_TONE: Record<StepStatus, Tone> = {
  running: 'working',
  ok: 'fixed',
  warning: 'human',
  error: 'failure',
  skipped: 'muted',
}

export const AGENT_LABEL: Record<string, string> = {
  triage: 'Triage',
  investigator: 'Investigator',
  fix_engineer: 'Fix Engineer',
  reviewer: 'Reviewer',
  remediation: 'Remediation',
}

export function isActive(status: IncidentStatus) {
  return status === 'queued' || status === 'processing'
}
