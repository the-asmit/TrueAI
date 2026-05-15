'use client'

import { useState, useEffect, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { Zap, GitBranch, Webhook, Key, ArrowRight, Check, Copy, AlertCircle, Loader2, User, GitCommit } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import {
  generateApiKey,
  getGithubAuthUrl,
  getAuthMe,
  setGithubRepo,
  getWebhookUrl,
  updateProfile,
  setGithubBranch
} from './actions'

export default function OnboardingPage() {
  const router = useRouter()
  const supabase = createClient()

  const [loadingInit, setLoadingInit] = useState(true)
  const [activeStep, setActiveStep] = useState(1)

  // Step 1 - Profile (NEW)
  const [fullName, setFullName] = useState('')
  const [savedFullName, setSavedFullName] = useState<string | null>(null)
  const [savingProfile, setSavingProfile] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)

  // API Key State (Preserved but not rendered in 5-step flow)
  const [apiKey, setApiKey] = useState<string | null>(null)
  const [keyPrefix, setKeyPrefix] = useState<string | null>(null)
  const [copiedKey, setCopiedKey] = useState(false)
  const [generatingKey, setGeneratingKey] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)

  // Step 2 - GitHub State
  const [githubConnected, setGithubConnected] = useState(false)
  const [githubUsername, setGithubUsername] = useState<string | null>(null)
  const [connectingGithub, setConnectingGithub] = useState(false)
  const [githubError, setGithubError] = useState<string | null>(null)

  // Step 3 - Repo State
  const [repoInput, setRepoInput] = useState('')
  const [githubRepo, setGithubRepoState] = useState<string | null>(null)
  const [settingRepo, setSettingRepo] = useState(false)
  const [repoError, setRepoError] = useState<string | null>(null)

  // Step 4 - Branch State (NEW)
  const [branchInput, setBranchInput] = useState('main')
  const [savedBranch, setSavedBranch] = useState<string | null>(null)
  const [settingBranch, setSettingBranch] = useState(false)
  const [branchError, setBranchError] = useState<string | null>(null)

  // Step 5 - Webhook State
  const [webhookUrl, setWebhookUrlState] = useState<string | null>(null)
  const [copiedWebhook, setCopiedWebhook] = useState(false)
  const [gettingWebhook, setGettingWebhook] = useState(false)
  const [webhookError, setWebhookError] = useState<string | null>(null)

  useEffect(() => {
    async function init() {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        router.push('/login')
        return
      }

      const isGithubRedirect = typeof window !== 'undefined' && window.location.search.includes('github_connected=true')

      try {
        const me = await getAuthMe()
        setGithubConnected(me.github_connected)
        setGithubUsername(me.github_username || null)
        setGithubRepoState(me.github_repo || null)
        setSavedBranch(me.github_branch || null)
        setSavedFullName(me.full_name || null)

        if (me.full_name && me.github_connected && me.github_repo && me.github_branch) {
          setActiveStep(5) // webhook step
        } else if (me.full_name && me.github_connected && me.github_repo) {
          setActiveStep(4) // branch step
        } else if (me.full_name && me.github_connected) {
          setActiveStep(3) // repo step
        } else if (me.full_name) {
          setActiveStep(2) // github step
        } else {
          setActiveStep(1) // profile step
        }
      } catch (err: any) {
        setActiveStep(1)
      } finally {
        setLoadingInit(false)
        setConnectingGithub(false)
        if (typeof window !== 'undefined' && window.history.replaceState) {
          window.history.replaceState({}, document.title, window.location.pathname)
        }
      }
    }

    init()
  }, [router, supabase.auth])

  const handleSaveProfile = async (e: FormEvent) => {
    e.preventDefault()
    setProfileError(null)
    const trimmed = fullName.trim()
    if (!trimmed) {
      setProfileError('Please enter your full name')
      return
    }
    setSavingProfile(true)
    try {
      await updateProfile(trimmed)
      setSavedFullName(trimmed)
      setActiveStep(2)
    } catch (err: any) {
      setProfileError(err.message)
    } finally {
      setSavingProfile(false)
    }
  }

  const handleGenerateKey = async () => {
    setGeneratingKey(true)
    setKeyError(null)
    try {
      const res = await generateApiKey()
      setApiKey(res.raw_key)
      setKeyPrefix(res.key_prefix)
      // Preserved old step logic just in case, but unused in 5-step flow
      setActiveStep(2)
    } catch (err: any) {
      setKeyError(err.message)
    } finally {
      setGeneratingKey(false)
    }
  }

  const handleConnectGithub = async () => {
    setConnectingGithub(true)
    setGithubError(null)
    try {
      const res = await getGithubAuthUrl()
      window.location.href = res.auth_url
    } catch (err: any) {
      setGithubError(err.message)
      setConnectingGithub(false)
    }
  }

  const handleSetRepo = async (e: FormEvent) => {
    e.preventDefault()
    setRepoError(null)
    
    const trimmed = repoInput.trim()
    if (!trimmed.match(/^[\w.-]+\/[\w.-]+$/)) {
      setRepoError('Invalid format. Must be owner/repo (e.g. acme/backend)')
      return
    }

    setSettingRepo(true)
    try {
      await setGithubRepo(trimmed)
      setGithubRepoState(trimmed)
      setActiveStep(4)
    } catch (err: any) {
      setRepoError(err.message)
    } finally {
      setSettingRepo(false)
    }
  }

  const handleSetBranch = async (e: FormEvent) => {
    e.preventDefault()
    setBranchError(null)
    const trimmed = branchInput.trim()
    if (!trimmed) {
      setBranchError('Please enter a branch name')
      return
    }
    setSettingBranch(true)
    try {
      await setGithubBranch(trimmed)
      setSavedBranch(trimmed)
      setActiveStep(5)
    } catch (err: any) {
      setBranchError(err.message)
    } finally {
      setSettingBranch(false)
    }
  }

  const handleGetWebhook = async () => {
    setGettingWebhook(true)
    setWebhookError(null)
    try {
      const res = await getWebhookUrl()
      setWebhookUrlState(res.webhook_url)
    } catch (err: any) {
      setWebhookError(err.message)
    } finally {
      setGettingWebhook(false)
    }
  }

  const copyToClipboard = (text: string, type: 'key' | 'webhook') => {
    navigator.clipboard.writeText(text)
    if (type === 'key') {
      setCopiedKey(true)
      setTimeout(() => setCopiedKey(false), 2000)
    } else {
      setCopiedWebhook(true)
      setTimeout(() => setCopiedWebhook(false), 2000)
    }
  }

  if (loadingInit) {
    return (
      <div className="min-h-screen bg-[#010102] flex items-center justify-center font-sans">
        <Loader2 className="animate-spin text-[#ededed]" size={20} />
      </div>
    )
  }

  const getPageHeading = () => {
    switch (activeStep) {
      case 1:
        return { title: 'Create Your Profile', sub: "Let's start by setting up your profile" }
      case 2:
        return { title: 'Connect GitHub', sub: 'Authorize TrueAI to access your repositories' }
      case 3:
        return { title: 'Select Repository', sub: 'Choose the repo TrueAI should monitor and fix' }
      case 4:
        return { title: 'Production Branch', sub: 'Confirm the branch TrueAI will always work from' }
      case 5:
        return { title: 'Add Sentry Webhook', sub: 'Forward error events to TrueAI automatically' }
      default:
        return { title: '', sub: '' }
    }
  }

  const { title: headingTitle, sub: headingSub } = getPageHeading()

  return (
    <div className="min-h-screen bg-[#010102] flex flex-col font-sans">
      {/* Top Bar */}
      <div className="fixed top-0 left-0 right-0 h-14 bg-[#010102] border-b border-[#23252a] z-50 flex flex-col justify-center px-6">
        <div className="flex items-center justify-between w-full relative">
          {/* Left: Logo */}
          <div className="flex items-center gap-2">
            <Zap size={20} className="text-[#f7f8f8]" fill="currentColor" />
            <span className="text-[18px] font-bold tracking-tight text-[#f7f8f8]">
              TrueAI
            </span>
          </div>

          {/* Center: Progress Bar */}
          <div className="absolute left-1/2 -translate-x-1/2 w-full max-w-[320px]">
            <div className="relative h-2 w-full bg-[#1a1b1e] rounded-full overflow-hidden">
              <div 
                className="absolute top-0 left-0 h-full bg-[#ededed] transition-all duration-500 ease-in-out rounded-full" 
                style={{ width: `${(activeStep / 5) * 100}%`, minWidth: "4px" }}
              />
            </div>
          </div>

          {/* Right: Step Counter */}
          <div className="text-[12px] font-medium text-[#62666d]">
            Step {activeStep} of 5
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col items-center pt-24 pb-12 px-6 w-full">
        <div className="w-full max-w-[560px] flex flex-col gap-3">
          
          <div className="mb-4">
            <h1 className="text-[28px] font-semibold text-[#f7f8f8] tracking-[-0.6px] text-center mb-2">
              {headingTitle}
            </h1>
            <p className="text-[14px] text-[#8a8f98] text-center">
              {headingSub}
            </p>
          </div>

          {/* STEP 1 Summary */}
          {activeStep > 1 && (
            <div className="bg-[#0a0b0d] border border-[#1e2024] rounded-lg px-4 py-3 flex items-center gap-3">
              <div className="flex items-center justify-center w-5 h-5 rounded-full bg-[#ededed] shrink-0">
                <Check size={12} className="text-[#010102]" strokeWidth={3} />
              </div>
              <div className="flex-1 min-w-0 flex items-center justify-between text-[13px]">
                <span className="font-medium text-[#f7f8f8]">Create Your Profile</span>
                <span className="text-[#62666d] font-mono truncate ml-4">{savedFullName}</span>
              </div>
            </div>
          )}

          {/* STEP 1 Active */}
          {activeStep === 1 && (
            <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-8 shadow-[0_0_0_1px_#23252a,0_8px_32px_rgba(0,0,0,0.4)]">
              <form onSubmit={handleSaveProfile} className="space-y-4">
                <div className="space-y-1">
                  <label className="text-[13px] font-medium text-[#f7f8f8]">Full name</label>
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Your full name"
                    className="w-full h-10 px-3 bg-[#070708] border border-[#23252a] rounded-lg text-[13px] text-[#f7f8f8] placeholder-[#62666d] focus:outline-none focus:ring-2 focus:ring-[#ededed]/30 focus:border-[#34343a] transition-colors"
                  />
                </div>
                <button
                  type="submit"
                  disabled={savingProfile}
                  className="w-full flex items-center justify-center gap-2 bg-[#ededed] hover:bg-[#ffffff] text-[#010102] text-[13px] font-medium h-[42px] rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed mt-2"
                >
                  {savingProfile && <Loader2 size={16} className="animate-spin" />}
                  Continue
                </button>
                {profileError && <p className="text-[13px] text-[#ef4444] mt-2">{profileError}</p>}
              </form>
            </div>
          )}

          {/* STEP 2 Summary */}
          {activeStep > 2 && (
            <div className="bg-[#0a0b0d] border border-[#1e2024] rounded-lg px-4 py-3 flex items-center gap-3">
              <div className="flex items-center justify-center w-5 h-5 rounded-full bg-[#ededed] shrink-0">
                <Check size={12} className="text-[#010102]" strokeWidth={3} />
              </div>
              <div className="flex-1 min-w-0 flex items-center justify-between text-[13px]">
                <span className="font-medium text-[#f7f8f8]">Connect GitHub</span>
                <span className="text-[#62666d] font-mono truncate ml-4">@{githubUsername}</span>
              </div>
            </div>
          )}

          {/* STEP 2 Active */}
          {activeStep === 2 && (
            <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-8 shadow-[0_0_0_1px_#23252a,0_8px_32px_rgba(0,0,0,0.4)]">
              {githubConnected ? (
                <div className="space-y-4">
                  <div className="inline-flex items-center gap-2 text-[13px] font-medium text-[#22c55e] bg-[#22c55e]/10 border border-[#22c55e]/20 px-3 py-2 rounded-lg">
                    <Check size={14} />
                    Connected as @{githubUsername}
                  </div>
                  <button
                    onClick={() => setActiveStep(3)}
                    className="w-full flex items-center justify-center gap-2 bg-[#ededed] hover:bg-[#ffffff] text-[#010102] text-[13px] font-medium h-[42px] rounded-lg transition-colors"
                  >
                    Continue
                  </button>
                </div>
              ) : (
                <div>
                  <button
                    onClick={handleConnectGithub}
                    disabled={connectingGithub}
                    className="w-full flex items-center justify-center gap-2 bg-[#ededed] disabled:bg-[#ededed] hover:bg-[#ffffff] text-[#010102] disabled:text-[#010102] text-[13px] font-medium h-[42px] rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {connectingGithub && <Loader2 size={16} className="animate-spin" />}
                    {connectingGithub && typeof window !== 'undefined' && window.location.search.includes('github_connected=true') 
                      ? 'Checking connection...' 
                      : 'Connect GitHub'}
                  </button>
                  {githubError && <p className="text-[13px] text-[#ef4444] mt-3">{githubError}</p>}
                </div>
              )}
            </div>
          )}

          {/* STEP 3 Summary */}
          {activeStep > 3 && (
            <div className="bg-[#0a0b0d] border border-[#1e2024] rounded-lg px-4 py-3 flex items-center gap-3">
              <div className="flex items-center justify-center w-5 h-5 rounded-full bg-[#ededed] shrink-0">
                <Check size={12} className="text-[#010102]" strokeWidth={3} />
              </div>
              <div className="flex-1 min-w-0 flex items-center justify-between text-[13px]">
                <span className="font-medium text-[#f7f8f8]">Select Repository</span>
                <span className="text-[#62666d] font-mono truncate ml-4">{githubRepo}</span>
              </div>
            </div>
          )}

          {/* STEP 3 Active */}
          {activeStep === 3 && (
            <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-8 shadow-[0_0_0_1px_#23252a,0_8px_32px_rgba(0,0,0,0.4)]">
              {githubRepo ? (
                <div className="space-y-4">
                  <div className="inline-flex items-center gap-2 text-[13px] font-medium text-[#22c55e] bg-[#22c55e]/10 border border-[#22c55e]/20 px-3 py-2 rounded-lg">
                    <Check size={14} />
                    Repository set to <span className="font-mono">{githubRepo}</span>
                  </div>
                  <button
                    onClick={() => setActiveStep(4)}
                    className="w-full flex items-center justify-center gap-2 bg-[#ededed] hover:bg-[#ffffff] text-[#010102] text-[13px] font-medium h-[42px] rounded-lg transition-colors"
                  >
                    Continue
                  </button>
                </div>
              ) : (
                <form onSubmit={handleSetRepo} className="space-y-4">
                  <div className="space-y-1">
                    <label className="text-[13px] font-medium text-[#f7f8f8]">Repository</label>
                    <input
                      type="text"
                      value={repoInput}
                      onChange={(e) => setRepoInput(e.target.value)}
                      placeholder="owner/repo"
                      className="w-full h-10 px-3 bg-[#070708] border border-[#23252a] rounded-lg text-[13px] text-[#f7f8f8] placeholder-[#62666d] font-mono focus:outline-none focus:ring-2 focus:ring-[#ededed]/30 focus:border-[#34343a] transition-colors"
                    />
                    <p className="text-[12px] text-[#8a8f98] pt-1">Enter the repository TrueAI should monitor</p>
                  </div>
                  <button
                    type="submit"
                    disabled={settingRepo || !repoInput.trim()}
                    className="w-full flex items-center justify-center gap-2 bg-[#ededed] disabled:bg-[#ededed] hover:bg-[#ffffff] text-[#010102] disabled:text-[#010102] text-[13px] font-medium h-[42px] rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed mt-2"
                  >
                    {settingRepo && <Loader2 size={16} className="animate-spin" />}
                    Set Repository
                  </button>
                  {repoError && <p className="text-[13px] text-[#ef4444] mt-2">{repoError}</p>}
                </form>
              )}
            </div>
          )}

          {/* STEP 4 Summary */}
          {activeStep > 4 && (
            <div className="bg-[#0a0b0d] border border-[#1e2024] rounded-lg px-4 py-3 flex items-center gap-3">
              <div className="flex items-center justify-center w-5 h-5 rounded-full bg-[#ededed] shrink-0">
                <Check size={12} className="text-[#010102]" strokeWidth={3} />
              </div>
              <div className="flex-1 min-w-0 flex items-center justify-between text-[13px]">
                <span className="font-medium text-[#f7f8f8]">Production Branch</span>
                <span className="text-[#62666d] font-mono truncate ml-4">{savedBranch}</span>
              </div>
            </div>
          )}

          {/* STEP 4 Active */}
          {activeStep === 4 && (
            <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-8 shadow-[0_0_0_1px_#23252a,0_8px_32px_rgba(0,0,0,0.4)]">
              {savedBranch ? (
                <div className="space-y-4">
                  <div className="inline-flex items-center gap-2 text-[13px] font-medium text-[#22c55e] bg-[#22c55e]/10 border border-[#22c55e]/20 px-3 py-2 rounded-lg">
                    <Check size={14} />
                    Branch set to <span className="font-mono">{savedBranch}</span>
                  </div>
                  <button
                    onClick={() => setActiveStep(5)}
                    className="w-full flex items-center justify-center gap-2 bg-[#ededed] hover:bg-[#ffffff] text-[#010102] text-[13px] font-medium h-[42px] rounded-lg transition-colors"
                  >
                    Continue
                  </button>
                </div>
              ) : (
                <form onSubmit={handleSetBranch} className="space-y-4">
                  <div className="space-y-1">
                    <label className="text-[13px] font-medium text-[#f7f8f8]">Branch name</label>
                    <input
                      type="text"
                      value={branchInput}
                      onChange={(e) => setBranchInput(e.target.value)}
                      placeholder="main"
                      className="w-full h-10 px-3 bg-[#070708] border border-[#23252a] rounded-lg text-[13px] text-[#f7f8f8] placeholder-[#62666d] font-mono focus:outline-none focus:ring-2 focus:ring-[#ededed]/30 focus:border-[#34343a] transition-colors"
                    />
                    <p className="text-[12px] text-[#8a8f98] pt-1">TrueAI will always work from this branch</p>
                  </div>
                  <button
                    type="submit"
                    disabled={settingBranch || !branchInput.trim()}
                    className="w-full flex items-center justify-center gap-2 bg-[#ededed] disabled:bg-[#ededed] hover:bg-[#ffffff] text-[#010102] disabled:text-[#010102] text-[13px] font-medium h-[42px] rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed mt-2"
                  >
                    {settingBranch && <Loader2 size={16} className="animate-spin" />}
                    Confirm Branch
                  </button>
                  {branchError && <p className="text-[13px] text-[#ef4444] mt-2">{branchError}</p>}
                </form>
              )}
            </div>
          )}

          {/* STEP 5 Active */}
          {activeStep === 5 && (
            <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-8 shadow-[0_0_0_1px_#23252a,0_8px_32px_rgba(0,0,0,0.4)]">
              {webhookUrl ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 bg-[#070708] border border-[#23252a] rounded-lg p-3 w-full">
                    <div className="flex-1 overflow-x-auto no-scrollbar">
                      <code className="text-[13px] text-[#f7f8f8] font-mono whitespace-nowrap px-1">
                        {webhookUrl}
                      </code>
                    </div>
                    <button
                      onClick={() => copyToClipboard(webhookUrl, 'webhook')}
                      className="shrink-0 flex items-center justify-center h-8 px-3 text-[12px] font-medium text-[#f7f8f8] bg-[#0f1011] border border-[#23252a] hover:border-[#34343a] rounded-md transition-colors"
                    >
                      {copiedWebhook ? <span className="text-[#22c55e] flex items-center gap-1"><Check size={12}/> Copied!</span> : <span className="flex items-center gap-1"><Copy size={12}/> Copy</span>}
                    </button>
                  </div>
                  <p className="text-[12px] text-[#8a8f98]">
                    Paste this URL in Sentry → Project Settings → Integrations → Webhooks
                  </p>
                  <button
                    onClick={() => router.push('/dashboard')}
                    className="w-full flex items-center justify-center gap-2 bg-[#ededed] hover:bg-[#ffffff] text-[#010102] text-[13px] font-medium h-[42px] rounded-lg transition-colors mt-6"
                  >
                    Go to Dashboard
                  </button>
                </div>
              ) : (
                <div>
                  <button
                    onClick={handleGetWebhook}
                    disabled={gettingWebhook}
                    className="w-full flex items-center justify-center gap-2 bg-[#ededed] disabled:bg-[#ededed] hover:bg-[#ffffff] text-[#010102] disabled:text-[#010102] text-[13px] font-medium h-[42px] rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {gettingWebhook && <Loader2 size={16} className="animate-spin" />}
                    Get Webhook URL
                  </button>
                  {webhookError && <p className="text-[13px] text-[#ef4444] mt-3">{webhookError}</p>}
                </div>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
