import 'server-only'

import { createClient } from '@/lib/supabase/server'

/**
 * Server-side client for the TrueAI API.
 *
 * Runs only on the server (Server Components, Server Actions, Route Handlers):
 * the user's Supabase access token is read from the session cookie and sent as
 * a Bearer token; it never reaches browser JavaScript through this module.
 *
 * - Every request has a timeout, so a slow or down API degrades one panel
 *   instead of hanging the whole page.
 * - Responses are never cached (incident data is live and per-user).
 * - Errors surface as ApiError with the HTTP status and the API's own message.
 */

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

const DEFAULT_TIMEOUT_MS = 15_000

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  get isNotFound() {
    return this.status === 404
  }

  get isUnauthorized() {
    return this.status === 401
  }
}

function apiBaseUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL
  if (!base) throw new ApiError('The TrueAI API URL is not configured (NEXT_PUBLIC_API_BASE_URL).', 500)
  return base.replace(/\/+$/, '')
}

async function accessToken(): Promise<string | null> {
  const supabase = await createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()
  return session?.access_token ?? null
}

async function request<T>(
  method: HttpMethod,
  path: string,
  body?: unknown,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const token = await accessToken()
  if (!token) throw new ApiError('Your session has expired. Please sign in again.', 401)

  let response: Response
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: 'no-store',
      signal: AbortSignal.timeout(timeoutMs),
    })
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === 'TimeoutError'
    throw new ApiError(
      timedOut ? 'TrueAI took too long to respond. Please try again.' : 'Cannot reach the TrueAI API right now.',
      503,
    )
  }

  if (response.status === 204) return undefined as T

  let payload: unknown = null
  const text = await response.text()
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    throw new ApiError(errorMessage(payload, response.status), response.status)
  }
  return payload as T
}

function errorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string; loc?: unknown[] }
      const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : ''
      const msg = (first.msg ?? 'Invalid value').replace(/^Value error, /, '')
      return field && field !== 'body' ? `${field.replace(/_/g, ' ')}: ${msg}` : msg
    }
  }
  if (status === 429) return 'Too many requests. Please wait a moment and try again.'
  if (status >= 500) return 'TrueAI hit an unexpected problem. Please try again.'
  return `Request failed (${status}).`
}

export const api = {
  get: <T>(path: string, timeoutMs?: number) => request<T>('GET', path, undefined, timeoutMs),
  post: <T>(path: string, body?: unknown, timeoutMs?: number) => request<T>('POST', path, body ?? {}, timeoutMs),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body ?? {}),
  delete: <T = void>(path: string) => request<T>('DELETE', path),
}

/** Turn any thrown error into a message safe to show in the UI. */
export function toMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (error instanceof ApiError) return error.message
  return fallback
}
