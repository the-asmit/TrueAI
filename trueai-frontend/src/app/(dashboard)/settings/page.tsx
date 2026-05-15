import type { Metadata } from 'next'
import { createClient } from '@/lib/supabase/server'
import { apiClient } from '@/lib/api/client'
import SettingsClient from './SettingsClient'

export const metadata: Metadata = {
  title: 'Settings — TrueAI',
  description: 'Manage your account and API keys',
}

export default async function SettingsPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  let keyPrefix = ''
  let fullName = ''
  let incidentCount = 0

  try {
    const [webhookRes, meRes, incidentsRes] = await Promise.all([
      apiClient.get<{ webhook_url: string; key_prefix: string }>('/auth/user/webhook-url'),
      apiClient.get<{ full_name?: string }>('/auth/me'),
      apiClient.get<{ total: number }>('/incidents'),
    ])
    keyPrefix = webhookRes.key_prefix
    fullName = meRes.full_name || ''
    incidentCount = incidentsRes.total
  } catch (error) {
    console.error('Failed to fetch settings data:', error)
  }

  return (
    <div className="p-6 max-w-2xl">
      <div className="mb-8">
        <h1 className="text-[22px] font-semibold text-[#f7f8f8] tracking-[-0.4px]">
          Settings
        </h1>
        <p className="text-[13px] text-[#8a8f98] mt-1">
          Manage your account and API keys
        </p>
      </div>
      <SettingsClient
        keyPrefix={keyPrefix}
        userEmail={user?.email || ''}
        fullName={fullName}
        incidentCount={incidentCount}
      />
    </div>
  )
}
