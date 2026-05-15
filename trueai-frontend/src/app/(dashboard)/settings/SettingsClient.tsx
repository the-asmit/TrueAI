'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Key, User, Check, Copy, Loader2, LogOut, BarChart2, Trash2 } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { generateNewApiKey, deleteAccount, updateUserProfile } from './actions'

interface SettingsClientProps {
  keyPrefix: string
  userEmail: string
  fullName: string
  incidentCount: number
}

export default function SettingsClient({ keyPrefix, userEmail, fullName, incidentCount }: SettingsClientProps) {
  const router = useRouter()

  const [currentPrefix, setCurrentPrefix] = useState(keyPrefix)

  // API Key state
  const [isGeneratingKey, setIsGeneratingKey] = useState(false)
  const [newKey, setNewKey] = useState<{ raw_key: string; prefix: string } | null>(null)
  const [keyCopied, setKeyCopied] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)

  // Sign out state
  const [isSigningOut, setIsSigningOut] = useState(false)

  // Profile state
  const [nameInput, setNameInput] = useState(fullName)
  const [savingProfile, setSavingProfile] = useState(false)
  const [profileSuccess, setProfileSuccess] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)

  // Delete account state
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deletingAccount, setDeletingAccount] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')

  // --- Handlers ---

  const handleGenerateKey = async () => {
    setIsGeneratingKey(true)
    setKeyError(null)
    setNewKey(null)
    try {
      const result = await generateNewApiKey()
      setNewKey({ raw_key: result.raw_key, prefix: result.key_prefix })
      setCurrentPrefix(result.key_prefix)
    } catch (err: any) {
      setKeyError(err.message || 'Failed to generate key')
    } finally {
      setIsGeneratingKey(false)
    }
  }

  const copyKey = () => {
    if (newKey) {
      navigator.clipboard.writeText(newKey.raw_key)
      setKeyCopied(true)
      setTimeout(() => setKeyCopied(false), 2000)
    }
  }

  const handleSignOut = async () => {
    setIsSigningOut(true)
    const supabase = createClient()
    await supabase.auth.signOut()
    router.push('/login')
  }

  const handleUpdateProfile = async () => {
    if (!nameInput.trim()) return
    setSavingProfile(true)
    setProfileError(null)
    setProfileSuccess(false)
    try {
      await updateUserProfile(nameInput.trim())
      setProfileSuccess(true)
      setTimeout(() => setProfileSuccess(false), 3000)
    } catch (err: any) {
      setProfileError(err.message)
    } finally {
      setSavingProfile(false)
    }
  }

  const handleDeleteAccount = async () => {
    if (deleteConfirmText !== 'delete my account') return
    setDeletingAccount(true)
    setDeleteError(null)
    try {
      await deleteAccount()
      const supabase = createClient()
      await supabase.auth.signOut()
      router.push('/login')
    } catch (err: any) {
      setDeleteError(err.message)
      setDeletingAccount(false)
    }
  }

  return (
    <div className="space-y-6">

      {/* ── PROFILE ── */}
      <div>
        <p className="text-[11px] font-semibold text-[#62666d] uppercase tracking-widest mb-3">
          Profile
        </p>
        <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-6 hover:border-[#34343a] transition-colors">
          <div className="flex items-center gap-2.5 mb-1">
            <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[#ededed]/8 shrink-0">
              <User size={13} className="text-[#8a8f98]" strokeWidth={1.5} />
            </div>
            <span className="text-[14px] font-semibold text-[#f7f8f8]">Profile</span>
          </div>
          <p className="text-[13px] text-[#8a8f98] mb-5 leading-relaxed">
            Update your display name
          </p>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-[12px] text-[#62666d]">Full name</label>
              <input
                type="text"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                placeholder="Your name"
                className="bg-[#070708] border border-[#23252a] rounded-lg h-10 px-3 text-[13px] text-[#f7f8f8] focus:outline-none focus:ring-2 focus:ring-[#ededed]/30 w-full transition-colors"
              />
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleUpdateProfile}
                disabled={savingProfile || nameInput === fullName}
                className="flex items-center gap-2 bg-[#ededed] text-[#010102] text-[13px] font-medium px-4 h-10 rounded-lg hover:bg-white transition-colors disabled:opacity-40"
              >
                {savingProfile && <Loader2 size={13} className="animate-spin" />}
                Save
              </button>
              {profileSuccess && (
                <span className="text-[12px] text-[#22c55e]">✓ Profile updated</span>
              )}
              {profileError && (
                <span className="text-[12px] text-[#ef4444]">{profileError}</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── API KEYS ── */}
      <div>
        <p className="text-[11px] font-semibold text-[#62666d] uppercase tracking-widest mb-3">
          API Keys
        </p>
        <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-6 hover:border-[#34343a] transition-colors">
          <div className="flex items-center gap-2.5 mb-1">
            <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[#ededed]/8 shrink-0">
              <Key size={13} className="text-[#8a8f98]" strokeWidth={1.5} />
            </div>
            <span className="text-[14px] font-semibold text-[#f7f8f8]">API Keys</span>
          </div>
          <p className="text-[13px] text-[#8a8f98] mb-5 leading-relaxed">
            Generate and manage API keys to authenticate with the TrueAI backend from your own tooling or CI pipeline.
          </p>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <span className="text-[12px] text-[#62666d]">Current prefix</span>
              <span className="text-[13px] font-mono text-[#f7f8f8] bg-[#070708] border border-[#23252a] px-2.5 py-1 rounded-lg">
                {currentPrefix || 'None'}
              </span>
            </div>
            <div>
              <button
                onClick={handleGenerateKey}
                disabled={isGeneratingKey}
                className="flex items-center gap-2 bg-[#ededed] text-[#010102] text-[13px] font-medium px-4 h-9 rounded-lg transition-colors hover:bg-white disabled:opacity-40"
              >
                {isGeneratingKey && <Loader2 size={13} className="animate-spin" />}
                Generate New Key
              </button>
              {keyError && <p className="text-[12px] text-[#ef4444] mt-2">{keyError}</p>}
            </div>
          </div>
        </div>
      </div>

      {/* ── USAGE ── */}
      <div>
        <p className="text-[11px] font-semibold text-[#62666d] uppercase tracking-widest mb-3">
          Usage
        </p>
        <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-6 hover:border-[#34343a] transition-colors">
          <div className="flex items-center gap-2.5 mb-1">
            <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[#ededed]/8 shrink-0">
              <BarChart2 size={13} className="text-[#8a8f98]" strokeWidth={1.5} />
            </div>
            <span className="text-[14px] font-semibold text-[#f7f8f8]">Usage</span>
          </div>
          <p className="text-[13px] text-[#8a8f98] mb-5 leading-relaxed">
            Incidents analyzed with TrueAI
          </p>
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[13px] text-[#8a8f98]">Incidents analyzed</span>
              <span className="text-[13px] font-medium text-[#f7f8f8] font-mono">{incidentCount}</span>
            </div>
            <div className="h-1.5 bg-[#23252a] rounded-full overflow-hidden">
              <div
                className="h-full bg-[#ededed] rounded-full transition-all"
                style={{ width: `${Math.min((incidentCount / 50) * 100, 100)}%` }}
              />
            </div>
            <p className="text-[12px] text-[#62666d] mt-2">Free plan · 50 incidents included</p>
          </div>
        </div>
      </div>

      {/* ── ACCOUNT ── */}
      <div>
        <p className="text-[11px] font-semibold text-[#62666d] uppercase tracking-widest mb-3">
          Account
        </p>
        <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-6 hover:border-[#34343a] transition-colors">
          <div className="flex items-center gap-2.5 mb-1">
            <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[#ededed]/8 shrink-0">
              <User size={13} className="text-[#8a8f98]" strokeWidth={1.5} />
            </div>
            <span className="text-[14px] font-semibold text-[#f7f8f8]">Account</span>
          </div>
          <p className="text-[13px] text-[#8a8f98] mb-5 leading-relaxed">
            Your account details and session management.
          </p>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <span className="text-[12px] text-[#62666d]">Email</span>
              <span className="text-[13px] text-[#f7f8f8] font-mono">{userEmail || '—'}</span>
            </div>
            <button
              onClick={handleSignOut}
              disabled={isSigningOut}
              className="flex items-center gap-2 bg-[#0f1011] border border-[#23252a] hover:border-[#ef4444]/40 hover:text-[#ef4444] text-[#8a8f98] text-[13px] px-4 h-9 rounded-lg transition-colors disabled:opacity-40"
            >
              {isSigningOut ? <Loader2 size={13} className="animate-spin" /> : <LogOut size={13} />}
              Sign out
            </button>
          </div>
        </div>
      </div>

      {/* ── DANGER ZONE ── */}
      <div>
        <div className="bg-[#0f1011] border border-[#ef4444]/20 rounded-xl p-6 hover:border-[#ef4444]/40 transition-colors">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[14px] font-semibold text-[#f7f8f8] mb-1">Delete Account</p>
              <p className="text-[13px] text-[#8a8f98] leading-relaxed max-w-sm">
                Permanently delete your account and all associated data. This action cannot be undone.
              </p>
            </div>
            <button
              onClick={() => setShowDeleteModal(true)}
              className="flex items-center gap-2 shrink-0 bg-transparent border border-[#ef4444]/40 text-[#ef4444] hover:bg-[#ef4444]/10 text-[13px] font-medium px-4 h-10 rounded-lg transition-colors"
            >
              <Trash2 size={13} />
              Delete account
            </button>
          </div>
        </div>
      </div>

      {/* ── NEW API KEY MODAL ── */}
      {newKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
            <h3 className="text-[15px] font-semibold text-[#f7f8f8] mb-1">Save your API key</h3>
            <p className="text-[13px] text-[#8a8f98] mb-5">
              Copy and store this key securely.{' '}
              <strong className="text-[#ef4444] font-medium">It won't be shown again.</strong>
            </p>
            <div className="flex items-center gap-2 mb-6">
              <code className="flex-1 bg-[#070708] border border-[#23252a] rounded-lg px-3 py-2.5 text-[13px] text-[#f7f8f8] font-mono break-all">
                {newKey.raw_key}
              </code>
              <button
                onClick={copyKey}
                className="h-10 px-3 border border-[#23252a] bg-[#0a0b0d] hover:border-[#34343a] text-[#f7f8f8] rounded-lg transition-colors flex items-center justify-center shrink-0"
                title="Copy to clipboard"
              >
                {keyCopied ? <Check size={14} className="text-[#22c55e]" /> : <Copy size={14} />}
              </button>
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => setNewKey(null)}
                className="bg-[#ededed] text-[#010102] px-4 py-2 rounded-lg text-[13px] font-medium hover:bg-white transition-colors"
              >
                I've saved it securely
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── DELETE ACCOUNT MODAL ── */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
            <h3 className="text-[16px] font-semibold text-[#f7f8f8] mb-2">Delete account</h3>
            <p className="text-[13px] text-[#8a8f98] mb-4 leading-relaxed">
              This will permanently delete your account, all incidents, API keys, and integrations.{' '}
              <span className="text-[#f7f8f8]">This cannot be undone.</span>
            </p>
            <div className="mb-4">
              <label className="text-[12px] text-[#62666d] mb-1.5 block">
                Type <span className="text-[#f7f8f8] font-mono">delete my account</span> to confirm
              </label>
              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                placeholder="delete my account"
                className="w-full h-10 px-3 bg-[#070708] border border-[#23252a] rounded-lg text-[13px] text-[#f7f8f8] placeholder-[#62666d] focus:outline-none focus:ring-2 focus:ring-[#ef4444]/30 focus:border-[#ef4444]/40 transition-colors"
              />
            </div>
            {deleteError && <p className="text-[12px] text-[#ef4444] mb-3">{deleteError}</p>}
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => { setShowDeleteModal(false); setDeleteConfirmText(''); setDeleteError(null) }}
                className="px-4 h-10 text-[13px] text-[#8a8f98] hover:text-[#f7f8f8] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteAccount}
                disabled={deleteConfirmText !== 'delete my account' || deletingAccount}
                className="flex items-center gap-2 px-4 h-10 bg-[#ef4444] hover:bg-[#dc2626] text-white text-[13px] font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {deletingAccount && <Loader2 size={14} className="animate-spin" />}
                Delete account
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
