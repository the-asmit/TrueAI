// Types mirroring the TrueAI API (app/schemas/incident.py and the account routes).
// Timestamps are ISO-8601 strings with an explicit offset.

export type IncidentStatus =
  | 'queued'
  | 'processing'
  | 'pr_open'
  | 'resolved'
  | 'flagged'
  | 'failed'
  | 'ignored'

export type IssueClassification = 'code_bug' | 'config_issue' | 'infrastructure' | 'data_issue' | 'dependency'

export type Severity = 'critical' | 'high' | 'medium' | 'low'

export interface IncidentSummary {
  id: string
  error_type: string | null
  error_message: string | null
  environment: string | null
  level: string | null
  platform: string | null
  status: IncidentStatus
  issue_classification: IssueClassification | null
  severity: Severity | null
  culprit: string | null
  occurrence_count: number
  last_seen_at: string | null
  sentry_project: string | null
  repo_full_name: string | null
  current_step: string | null
  confidence: number | null
  created_at: string
  updated_at: string | null
  completed_at: string | null
}

export interface IncidentList {
  items: IncidentSummary[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface IncidentStats {
  total: number
  by_status: Partial<Record<IncidentStatus, number>>
}

export interface Remediation {
  summary: string
  steps: string[]
  verification?: string
  prevention?: string
  fallback?: boolean
}

export interface Analysis {
  root_cause: string | null
  explanation: string | null
  confidence: number | null
  fix_confidence: number | null
  fix_diff: string | null
  files_changed: string[]
  summary: string | null
  rationale: string | null
  risk: 'low' | 'medium' | 'high' | null
  validation_passed: boolean | null
  review_verdict: 'approve' | 'revise' | 'reject' | null
  review_notes: string | null
  remediation: Remediation | null
  flag_reason: string | null
  policy_violations: string[]
  status: 'pending' | 'applied' | 'failed' | 'rejected' | 'not_applicable' | null
  created_at: string | null
  updated_at: string | null
}

export interface PullRequestInfo {
  pr_url: string
  pr_number: number
  branch_name: string
  repo_full_name: string | null
  title: string | null
  status: 'open' | 'merged' | 'closed'
  merged_at: string | null
  closed_at: string | null
  last_synced_at: string | null
  created_at: string | null
}

export interface StackFrame {
  filename: string | null
  function: string | null
  lineno: number | null
  context_line: string | null
  in_app: boolean | null
}

export interface IncidentDetail extends IncidentSummary {
  sentry_event_id: string | null
  sentry_issue_id: string | null
  sentry_issue_url: string | null
  fingerprint: string | null
  branch: string | null
  pipeline_error: string | null
  stack_trace: StackFrame[] | null
  analysis: Analysis | null
  pull_request: PullRequestInfo | null
}

export interface Me {
  user_id: string
  full_name: string | null
  github_connected: boolean
  github_username: string | null
  github_repo: string | null
  github_branch: string | null
  has_api_key: boolean
  sentry: { org_slug: string | null; has_auth_token: boolean; has_webhook_secret: boolean }
  onboarding_complete: boolean
  auto_pr_threshold: number
}

export interface ApiKey {
  id: string
  name: string | null
  key_prefix: string
  is_active: boolean
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}

export interface CreatedApiKey {
  id: string
  name: string | null
  key_prefix: string
  created_at: string | null
  raw_key: string
  webhook_url: string
  message: string
}

export interface GitHubRepository {
  full_name: string
  private: boolean
  default_branch: string
  can_push: boolean
  pushed_at: string | null
}

export interface RepoMapping {
  id: string
  sentry_project: string | null
  repo_full_name: string
  branch: string | null
  created_at: string
  updated_at: string | null
}

export interface SentrySettings {
  org_slug: string | null
  base_url: string
  has_auth_token: boolean
  has_webhook_secret: boolean
  webhook_base_url: string
  updated_at: string | null
}

/** Result shape returned by every server action: never throws across the boundary. */
export type ActionResult<T = undefined> = { ok: true; data: T } | { ok: false; error: string }
