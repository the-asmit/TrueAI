'use client'

import { useState } from 'react'
import { GitBranch, Webhook, Check, Copy, Loader2 } from 'lucide-react'
import { getGithubAuthUrl, updateGithubRepo } from './actions'

interface IntegrationsData {
  github_connected: boolean
  github_username?: string
  github_repo?: string
  github_branch?: string
  webhook_url: string
  key_prefix: string
}

export default function IntegrationsClient({ initialData }: { initialData: IntegrationsData }) {
  const [data, setData] = useState(initialData)

  // Repo state
  const [repoInput, setRepoInput] = useState(initialData.github_repo || '')
  const [isUpdatingRepo, setIsUpdatingRepo] = useState(false)
  const [repoError, setRepoError] = useState<string | null>(null)
  const [repoSuccess, setRepoSuccess] = useState(false)

  // GitHub connect state
  const [isConnecting, setIsConnecting] = useState(false)

  // Webhook state
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [webhookCopied, setWebhookCopied] = useState(false)

  const constructedWebhookUrl = apiKeyInput.trim().startsWith('tai_') && apiKeyInput.trim().length >= 20
    ? `${data.webhook_url.split('?')[0]}?key=${apiKeyInput.trim()}`
    : null

  // --- Handlers ---

  const handleUpdateRepo = async () => {
    if (!repoInput.trim()) return

    // Validate format owner/repo
    const repoRegex = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/
    if (!repoRegex.test(repoInput)) {
      setRepoError('Repository must be in "owner/repo" format')
      return
    }

    setIsUpdatingRepo(true)
    setRepoError(null)
    setRepoSuccess(false)

    try {
      await updateGithubRepo(repoInput)
      setData(prev => ({ ...prev, github_repo: repoInput }))
      setRepoSuccess(true)
      setTimeout(() => setRepoSuccess(false), 3000)
    } catch (err: any) {
      setRepoError(err.message || 'Failed to update repository')
    } finally {
      setIsUpdatingRepo(false)
    }
  }

  const handleConnectGithub = async () => {
    setIsConnecting(true)
    try {
      const { auth_url } = await getGithubAuthUrl()
      window.location.href = auth_url
    } catch (err: any) {
      alert(err.message || 'Failed to initiate GitHub connection')
      setIsConnecting(false)
    }
  }


  return (
    <div className="space-y-6 max-w-2xl">

      {/* ── ERROR TRACKING ── */}
      <div>
        <p className="text-[11px] font-semibold text-[#62666d] uppercase tracking-widest mb-3">
          Error Tracking
        </p>

        <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-6 hover:border-[#34343a] transition-colors">
          {/* Card header */}
          <div className="flex items-center justify-between gap-3 mb-1">
            <div className="flex items-center gap-2.5">
              <Webhook size={15} className="text-[#8a8f98]" strokeWidth={1.5} />
              <span className="text-[14px] font-semibold text-[#f7f8f8]">Sentry</span>
            </div>
            <span className="flex items-center gap-1.5 text-[12px] text-[#22c55e]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e]" />
              Connected
            </span>
          </div>
          <p className="text-[13px] text-[#8a8f98] mb-5 leading-relaxed">
            Forward error events from Sentry to TrueAI automatically
          </p>

          <div className="mt-4 space-y-3">
            {/* Step instructions */}
            <div className="space-y-2">
              <p className="text-[12px] text-[#62666d] leading-relaxed">
                To get your webhook URL:
              </p>
              <ol className="space-y-1.5 text-[12px] text-[#62666d]">
                <li className="flex gap-2">
                  <span className="text-[#ededed] font-mono shrink-0">1.</span>
                  Go to <span className="text-[#f7f8f8]">Settings → API Keys</span> and generate an API key
                </li>
                <li className="flex gap-2">
                  <span className="text-[#ededed] font-mono shrink-0">2.</span>
                  Paste your full API key below to generate the webhook URL
                </li>
                <li className="flex gap-2">
                  <span className="text-[#ededed] font-mono shrink-0">3.</span>
                  Copy the URL and paste it into <span className="text-[#f7f8f8]">Sentry → Project Settings → Integrations → Webhooks</span>
                </li>
              </ol>
            </div>

            {/* API key input */}
            <div>
              <label className="text-[12px] text-[#62666d] block mb-1.5">Your API key</label>
              <input
                type="password"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder="tai_..."
                className="w-full h-10 px-3 bg-[#070708] border border-[#23252a] rounded-lg text-[13px] text-[#f7f8f8] placeholder-[#62666d] font-mono focus:outline-none focus:ring-2 focus:ring-[#ededed]/30 focus:border-[#34343a] transition-colors"
              />
              <p className="text-[11px] text-[#62666d] mt-1.5">
                Your API key is never sent to our servers — the URL is constructed entirely in your browser.
              </p>
              {apiKeyInput.trim().length > 0 && !constructedWebhookUrl && (
                <p className="text-[11px] text-[#ef4444] mt-1">
                  Invalid API key format. Keys start with <span className="font-mono">tai_</span> and are at least 20 characters.
                </p>
              )}
            </div>

            {/* Constructed URL */}
            {constructedWebhookUrl && (
              <div>
                <label className="text-[12px] text-[#62666d] block mb-1.5">Webhook URL</label>
                <div className="flex gap-2">
                  <div className="flex-1 h-10 px-3 bg-[#070708] border border-[#23252a] rounded-lg text-[13px] text-[#f7f8f8] font-mono flex items-center overflow-hidden">
                    <span className="truncate">{constructedWebhookUrl}</span>
                  </div>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(constructedWebhookUrl)
                      setWebhookCopied(true)
                      setTimeout(() => setWebhookCopied(false), 2000)
                    }}
                    className="shrink-0 flex items-center gap-1.5 h-10 px-3 bg-[#0f1011] border border-[#23252a] hover:border-[#34343a] text-[#f7f8f8] text-[12px] font-medium rounded-lg transition-colors"
                  >
                    {webhookCopied ? <Check size={13} className="text-[#22c55e]" /> : <Copy size={13} />}
                    {webhookCopied ? 'Copied!' : 'Copy'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── CODEBASE ── */}
      <div>
        <p className="text-[11px] font-semibold text-[#62666d] uppercase tracking-widest mb-3">
          Codebase
        </p>

        <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-6 hover:border-[#34343a] transition-colors">
          {/* Card header */}
          <div className="flex items-center justify-between gap-3 mb-1">
            <div className="flex items-center gap-2.5">
              <GitBranch size={15} className="text-[#8a8f98]" strokeWidth={1.5} />
              <span className="text-[14px] font-semibold text-[#f7f8f8]">GitHub</span>
            </div>
            {data.github_connected ? (
              <span className="flex items-center gap-1.5 text-[12px] text-[#22c55e]">
                <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e]" />
                Connected as @{data.github_username}
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-[12px] text-[#62666d]">
                <span className="w-1.5 h-1.5 rounded-full bg-[#62666d]" />
                Not connected
              </span>
            )}
          </div>
          <p className="text-[13px] text-[#8a8f98] mb-5 leading-relaxed">
            Connect your repository so TrueAI can analyze code and open fix PRs
          </p>

          {data.github_connected ? (
            <div className="space-y-4">
              {/* Repository input */}
              <div className="space-y-1.5">
                <label className="text-[12px] text-[#62666d]">Repository</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={repoInput}
                    onChange={(e) => setRepoInput(e.target.value)}
                    placeholder="owner/repo"
                    className="bg-[#070708] border border-[#23252a] rounded-lg h-10 px-3 text-[13px] text-[#f7f8f8] font-mono focus:outline-none focus:ring-2 focus:ring-[#ededed]/30 w-full transition-colors"
                  />
                  <button
                    onClick={handleUpdateRepo}
                    disabled={isUpdatingRepo || repoInput === data.github_repo}
                    className="bg-[#0f1011] border border-[#23252a] hover:border-[#34343a] text-[#f7f8f8] text-[13px] px-4 h-10 rounded-lg transition-colors disabled:opacity-40 shrink-0 flex items-center gap-2"
                  >
                    {isUpdatingRepo && <Loader2 size={13} className="animate-spin" />}
                    Save
                  </button>
                </div>
                {repoError && <p className="text-[12px] text-[#ef4444]">{repoError}</p>}
                {repoSuccess && <p className="text-[12px] text-[#22c55e]">✓ Saved</p>}
              </div>

              {/* Branch (display only) */}
              <div className="space-y-1.5">
                <label className="text-[12px] text-[#62666d]">Branch</label>
                <p className="text-[13px] text-[#f7f8f8] font-mono">
                  {data.github_branch || 'main'}
                </p>
              </div>

              {/* Reconnect */}
              <button
                onClick={handleConnectGithub}
                disabled={isConnecting}
                className="flex items-center gap-2 bg-[#0f1011] border border-[#23252a] hover:border-[#34343a] text-[#f7f8f8] text-[13px] px-4 h-9 rounded-lg transition-colors disabled:opacity-40"
              >
                {isConnecting && <Loader2 size={13} className="animate-spin" />}
                Reconnect GitHub
              </button>
            </div>
          ) : (
            <button
              onClick={handleConnectGithub}
              disabled={isConnecting}
              className="flex items-center gap-2 bg-[#ededed] text-[#010102] text-[13px] font-medium px-4 h-9 rounded-lg transition-colors hover:bg-white disabled:opacity-40"
            >
              {isConnecting && <Loader2 size={13} className="animate-spin" />}
              Connect GitHub
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
