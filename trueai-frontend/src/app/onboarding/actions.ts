'use server'

import { apiClient } from '@/lib/api/client'


export async function generateApiKey() {
  try {
    return await apiClient.post<{ id: string; raw_key: string; key_prefix: string; message: string }>('/auth/api-keys')
  } catch (error: any) {
    throw new Error(error.message || 'Failed to generate API key')
  }
}

export async function getGithubAuthUrl() {
  try {
    const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'
    const redirectUri = `${appUrl}/onboarding`
    return await apiClient.get<{ auth_url: string }>(
      `/auth/github/authorize?redirect_uri=${encodeURIComponent(redirectUri)}`
    )
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Failed to get GitHub auth URL'
    throw new Error(message)
  }
}

export async function getAuthMe() {
  try {
    return await apiClient.get<{ 
      github_connected: boolean
      github_username?: string
      github_repo?: string
      github_branch?: string
      full_name?: string
    }>('/auth/me')
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Failed to check connection status'
    throw new Error(message)
  }
}

export async function setGithubRepo(repoName: string) {
  try {
    return await apiClient.post<{ success: boolean; message?: string }>('/auth/github/repo', { repo_name: repoName })
  } catch (error: any) {
    throw new Error(error.message || 'Failed to set repository')
  }
}

export async function getWebhookUrl() {
  try {
    return await apiClient.get<{ webhook_url: string; key_prefix: string }>('/auth/user/webhook-url')
  } catch (error: any) {
    throw new Error(error.message || 'Failed to get webhook URL')
  }
}

export async function updateProfile(fullName: string) {
  try {
    return await apiClient.post<{ status: string; full_name: string }>('/auth/profile', { full_name: fullName })
  } catch (error: any) {
    throw new Error(error.message || 'Failed to save profile')
  }
}

export async function setGithubBranch(branchName: string) {
  try {
    return await apiClient.post<{ status: string; branch_name: string }>('/auth/github/branch', { branch_name: branchName })
  } catch (error: any) {
    throw new Error(error.message || 'Failed to save branch')
  }
}