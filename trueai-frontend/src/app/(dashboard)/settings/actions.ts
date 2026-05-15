'use server'

import { apiClient } from '@/lib/api/client'

export async function generateNewApiKey() {
  try {
    return await apiClient.post<{ id: string; raw_key: string; key_prefix: string; message: string }>('/auth/api-keys')
  } catch (error: any) {
    throw new Error(error.message || 'Failed to generate API key')
  }
}

export async function getGithubAuthUrl() {
  try {
    const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'
    const redirectUri = `${appUrl}/dashboard/settings`
    return await apiClient.get<{ auth_url: string }>(
      `/auth/github/authorize?redirect_uri=${encodeURIComponent(redirectUri)}`
    )
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Failed to get GitHub auth URL'
    throw new Error(message)
  }
}

export async function updateGithubRepo(repoName: string) {
  try {
    return await apiClient.post<{ success: boolean; message?: string }>('/auth/github/repo', { repo_name: repoName })
  } catch (error: any) {
    throw new Error(error.message || 'Failed to set repository')
  }
}

export async function deleteAccount() {
  try {
    await apiClient.delete('/auth/account')
  } catch (error: any) {
    throw new Error(error.message || 'Failed to delete account')
  }
}

export async function updateUserProfile(fullName: string) {
  try {
    return await apiClient.post<{ status: string; full_name: string }>('/auth/profile', { full_name: fullName })
  } catch (error: any) {
    throw new Error(error.message || 'Failed to update profile')
  }
}