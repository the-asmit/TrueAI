import type { Metadata } from 'next'
import { apiClient } from '@/lib/api/client'
import IntegrationsClient from './IntegrationsClient'

export const metadata: Metadata = {
  title: 'Integrations — TrueAI',
  description: 'Connect your tools and services to TrueAI',
}

export default async function IntegrationsPage() {
  let initialData = {
    github_connected: false,
    github_username: undefined as string | undefined,
    github_repo: undefined as string | undefined,
    github_branch: undefined as string | undefined,
    webhook_url: '',
    key_prefix: ''
  }

  try {
    const [authMe, webhookRes] = await Promise.all([
      apiClient.get<{
        github_connected: boolean
        github_username?: string
        github_repo?: string
        github_branch?: string
      }>('/auth/me'),
      apiClient.get<{ webhook_url: string; key_prefix: string }>('/auth/user/webhook-url')
    ])

    initialData = {
      github_connected: authMe.github_connected,
      github_username: authMe.github_username,
      github_repo: authMe.github_repo,
      github_branch: authMe.github_branch,
      webhook_url: webhookRes.webhook_url,
      key_prefix: webhookRes.key_prefix
    }
  } catch (error) {
    console.error('Failed to fetch integrations data:', error)
  }

  return (
    <div className="p-6 max-w-2xl">
      <div className="mb-8">
        <h1 className="text-[22px] font-semibold text-[#f7f8f8] tracking-[-0.4px]">
          Integrations
        </h1>
        <p className="text-[13px] text-[#8a8f98] mt-1">
          Connect your tools so TrueAI fits seamlessly into your workflow
        </p>
      </div>
      <IntegrationsClient initialData={initialData} />
    </div>
  )
}
