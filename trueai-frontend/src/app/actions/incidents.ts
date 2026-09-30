'use server'

import { refresh, revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'

import { api, toMessage } from '@/lib/api/client'
import type { ActionResult, IncidentStatus } from '@/lib/api/types'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function checkId(id: string): string | null {
  return UUID.test(id) ? null : 'This incident reference is not valid.'
}

export async function setIncidentStatus(id: string, status: Extract<IncidentStatus, 'resolved' | 'ignored' | 'flagged'>): Promise<ActionResult> {
  const invalid = checkId(id)
  if (invalid) return { ok: false, error: invalid }
  try {
    await api.patch(`/incidents/${id}`, { status })
    refresh()
    return { ok: true, data: undefined }
  } catch (error) {
    return { ok: false, error: toMessage(error) }
  }
}

export async function reanalyzeIncident(id: string): Promise<ActionResult> {
  const invalid = checkId(id)
  if (invalid) return { ok: false, error: invalid }
  try {
    await api.post(`/incidents/${id}/reanalyze`)
    refresh()
    return { ok: true, data: undefined }
  } catch (error) {
    return { ok: false, error: toMessage(error) }
  }
}

export async function syncIncidentPullRequest(id: string): Promise<ActionResult<{ status: string; synced: boolean }>> {
  const invalid = checkId(id)
  if (invalid) return { ok: false, error: invalid }
  try {
    const result = await api.post<{ status: string; synced: boolean }>(`/incidents/${id}/sync-pr`)
    if (result.synced) refresh()
    return { ok: true, data: result }
  } catch (error) {
    return { ok: false, error: toMessage(error) }
  }
}

/** Deletes the incident and goes back to the list; only returns when the delete failed. */
export async function deleteIncident(id: string): Promise<ActionResult> {
  const invalid = checkId(id)
  if (invalid) return { ok: false, error: invalid }
  try {
    await api.delete(`/incidents/${id}`)
  } catch (error) {
    return { ok: false, error: toMessage(error) }
  }
  // 'layout' also refreshes the sidebar's needs-you count, which a plain navigation would leave stale.
  revalidatePath('/dashboard', 'layout')
  redirect('/dashboard')
}
