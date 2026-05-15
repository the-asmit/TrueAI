// ─── Status Enums ────────────────────────────────────────────────────────────

export type IncidentStatus = 'processing' | 'resolved' | 'flagged' | 'failed' | 'duplicate'
export type FixStatus = 'pending' | 'applied' | 'failed'
export type PRStatus = 'open' | 'merged' | 'closed'

// ─── Core Domain Models ───────────────────────────────────────────────────────

export interface Incident {
  id: string
  user_id: string
  sentry_event_id: string
  error_type: string
  error_message: string
  stack_trace: unknown
  environment: string
  status: IncidentStatus
  created_at: string
}

export interface Fix {
  id: string
  incident_id: string
  root_cause: string
  explanation: string
  fix_diff: string
  confidence: number
  status: FixStatus
  created_at: string
}

export interface PullRequest {
  id: string
  fix_id: string
  pr_url: string
  pr_number: number
  branch_name: string
  status: PRStatus
  created_at: string
}

// ─── Integration Models ───────────────────────────────────────────────────────

export interface ApiKey {
  id: string
  user_id: string
  key_prefix: string
  is_active: boolean
  created_at: string
}

export interface GithubToken {
  id: string
  user_id: string
  github_username: string
  repo_name: string
  created_at: string
}

// ─── API Envelope ─────────────────────────────────────────────────────────────

export interface ApiResponse<T> {
  data: T
  error?: string
}
