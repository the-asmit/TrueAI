'use server'

import { refresh } from 'next/cache'

import { api, toMessage } from '@/lib/api/client'
import type { ActionResult, GitHubRepository, RepoMapping, SentrySettings } from '@/lib/api/types'

const REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/

async function run<T>(work: () => Promise<T>, refreshAfter = true): Promise<ActionResult<T>> {
  try {
    const data = await work()
    if (refreshAfter) refresh()
    return { ok: true, data }
  } catch (error) {
    return { ok: false, error: toMessage(error) }
  }
}

// ---- GitHub connection ---------------------------------------------------

export async function startGitHubConnect(returnTo: '/onboarding' | '/integrations' | '/settings'): Promise<ActionResult<{ auth_url: string }>> {
  return run(() => api.get<{ auth_url: string }>(`/auth/github/authorize?return_to=${encodeURIComponent(returnTo)}`), false)
}

export async function disconnectGitHub(): Promise<ActionResult> {
  return run(() => api.delete('/auth/github'))
}

export async function searchRepositories(query: string): Promise<ActionResult<GitHubRepository[]>> {
  return run(async () => {
    const result = await api.get<{ repositories: GitHubRepository[] }>(`/auth/github/repos?q=${encodeURIComponent(query.slice(0, 100))}`)
    return result.repositories
  }, false)
}

export async function listBranches(repo: string): Promise<ActionResult<{ default_branch: string; branches: string[] }>> {
  if (!REPO.test(repo)) return { ok: false, error: 'Choose a repository first.' }
  return run(() => api.get<{ default_branch: string; branches: string[] }>(`/auth/github/branches?repo=${encodeURIComponent(repo)}`), false)
}

export async function setDefaultRepository(
  repo: string,
  branch?: string,
): Promise<ActionResult<{ repo_name: string; branch_name: string; can_push: boolean }>> {
  if (!REPO.test(repo)) return { ok: false, error: 'Repository must look like owner/repo.' }
  return run(() => api.post('/auth/github/repo', { repo_name: repo, branch_name: branch || null }))
}

// ---- Repository mappings ---------------------------------------------------

export async function saveRepositoryMapping(sentryProject: string, repo: string, branch?: string): Promise<ActionResult<RepoMapping>> {
  if (!sentryProject.trim()) return { ok: false, error: 'Enter the Sentry project slug.' }
  if (!REPO.test(repo)) return { ok: false, error: 'Repository must look like owner/repo.' }
  return run(() =>
    api.post<RepoMapping>('/integrations/repositories', {
      sentry_project: sentryProject.trim().toLowerCase(),
      repo_full_name: repo,
      branch: branch || null,
    }),
  )
}

export async function deleteRepositoryMapping(id: string): Promise<ActionResult> {
  if (!/^[0-9a-f-]{36}$/i.test(id)) return { ok: false, error: 'This mapping reference is not valid.' }
  return run(() => api.delete(`/integrations/repositories/${id}`))
}

// ---- Sentry ------------------------------------------------------------------

export async function saveSentrySettings(input: {
  org_slug?: string
  auth_token?: string
  webhook_secret?: string
}): Promise<ActionResult<SentrySettings>> {
  const body: Record<string, string> = {}
  if (input.org_slug !== undefined) body.org_slug = input.org_slug.trim().toLowerCase()
  if (input.auth_token) body.auth_token = input.auth_token.trim()
  if (input.webhook_secret) body.webhook_secret = input.webhook_secret.trim()
  return run(() => api.put<SentrySettings>('/integrations/sentry', body))
}

export async function clearSentrySecret(which: 'auth_token' | 'webhook_secret'): Promise<ActionResult<SentrySettings>> {
  return run(() => api.put<SentrySettings>('/integrations/sentry', { [which]: '' }))
}
