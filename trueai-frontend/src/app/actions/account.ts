'use server'

import { refresh } from 'next/cache'
import { cookies } from 'next/headers'

import { api, toMessage } from '@/lib/api/client'
import type { ActionResult, CreatedApiKey } from '@/lib/api/types'
import { createClient } from '@/lib/supabase/server'

export async function saveProfile(fullName: string): Promise<ActionResult> {
  const name = fullName.trim()
  if (!name) return { ok: false, error: 'Enter your name.' }
  if (name.length > 100) return { ok: false, error: 'Use 100 characters or fewer.' }
  try {
    await api.post('/auth/profile', { full_name: name })
    refresh()
    return { ok: true, data: undefined }
  } catch (error) {
    return { ok: false, error: toMessage(error) }
  }
}

export async function createApiKey(name: string): Promise<ActionResult<CreatedApiKey>> {
  const label = name.trim().slice(0, 60) || 'Sentry webhook'
  try {
    const key = await api.post<CreatedApiKey>('/auth/api-keys', { name: label })
    refresh()
    return { ok: true, data: key }
  } catch (error) {
    return { ok: false, error: toMessage(error) }
  }
}

export async function revokeApiKey(id: string): Promise<ActionResult> {
  if (!/^[0-9a-f-]{36}$/i.test(id)) return { ok: false, error: 'This key reference is not valid.' }
  try {
    await api.delete(`/auth/api-keys/${id}`)
    refresh()
    return { ok: true, data: undefined }
  } catch (error) {
    return { ok: false, error: toMessage(error) }
  }
}

export async function deleteAccount(): Promise<ActionResult> {
  try {
    await api.delete('/auth/account')
  } catch (error) {
    return { ok: false, error: toMessage(error) }
  }
  const supabase = await createClient()
  await supabase.auth.signOut()
  return { ok: true, data: undefined }
}

export async function setTheme(theme: 'light' | 'dark' | 'system'): Promise<void> {
  const store = await cookies()
  if (theme === 'system') {
    store.delete('theme')
  } else {
    store.set('theme', theme, { path: '/', maxAge: 60 * 60 * 24 * 365, sameSite: 'lax' })
  }
  refresh()
}
