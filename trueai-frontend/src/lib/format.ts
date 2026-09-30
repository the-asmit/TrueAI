// Formatting helpers. Exact times are shown in UTC (incident reports are
// read across time zones); relative times are for scanning lists.

const UTC_FORMAT = new Intl.DateTimeFormat('en-GB', {
  year: 'numeric',
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
  timeZone: 'UTC',
})

const UTC_TIME = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
  timeZone: 'UTC',
})

function parse(value: string | null | undefined): Date | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** "29 Sep 2026, 18:47:35 UTC" */
export function formatUtc(value: string | null | undefined): string {
  const date = parse(value)
  return date ? `${UTC_FORMAT.format(date)} UTC` : '—'
}

/** "18:47:35" */
export function formatUtcTime(value: string | null | undefined): string {
  const date = parse(value)
  return date ? UTC_TIME.format(date) : '—'
}

/** "just now", "4 min ago", "3 h ago", "2 d ago", then a date. */
export function formatRelative(value: string | null | undefined, now: number = Date.now()): string {
  const date = parse(value)
  if (!date) return '—'
  const seconds = Math.max(0, Math.round((now - date.getTime()) / 1000))
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days} d ago`
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date)
}

/** 842 → "842 ms", 3165 → "3.2 s" */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`
}

/** 0.923 → "92%" */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${Math.round(value * 100)}%`
}

export function formatCount(value: number | null | undefined): string {
  return new Intl.NumberFormat('en-GB').format(value ?? 0)
}

/** Short, stable incident reference shown in lists: the first 8 characters of its id. */
export function shortId(id: string): string {
  return id.slice(0, 8)
}

export function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return `${formatCount(count)} ${count === 1 ? singular : plural}`
}
