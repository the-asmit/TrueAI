import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import type { ReactNode } from 'react'

import { AppShell } from '@/components/app-shell'
import { api } from '@/lib/api/client'
import type { IncidentStats, Me } from '@/lib/api/types'
import { createClient } from '@/lib/supabase/server'

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  // Both are best-effort: the pages show their own error states if the API is down.
  const [me, stats] = await Promise.all([
    api.get<Me>('/auth/me').catch(() => null),
    api.get<IncidentStats>('/incidents/stats').catch(() => null),
  ])

  const theme = (await cookies()).get('theme')?.value
  const displayName = me?.full_name?.trim() || user.email?.split('@')[0] || 'Your account'

  return (
    <AppShell
      displayName={displayName}
      email={user.email ?? null}
      needsYou={stats?.by_status.flagged ?? 0}
      theme={theme === 'light' || theme === 'dark' ? theme : 'system'}
    >
      {children}
    </AppShell>
  )
}
