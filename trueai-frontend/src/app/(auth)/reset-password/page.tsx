'use client'

import { useState, useEffect, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Zap, AlertCircle, Loader2, Eye, EyeOff } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'

export default function ResetPasswordPage() {
  const router = useRouter()
  const supabase = createClient()

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [isCheckingSession, setIsCheckingSession] = useState(true)
  const [sessionValid, setSessionValid] = useState(false)

  useEffect(() => {
    const checkSession = async () => {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        setSessionValid(false)
      } else {
        setSessionValid(true)
      }
      setIsCheckingSession(false)
    }
    checkSession()
  }, [supabase])

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)

    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }

    setLoading(true)

    const { error: updateError } = await supabase.auth.updateUser({
      password,
    })

    setLoading(false)

    if (updateError) {
      setError(updateError.message)
      return
    }

    router.push('/login?message=Password updated successfully. Please sign in.')
  }

  return (
    <div className="min-h-screen bg-[#010102] flex flex-col items-center justify-center px-4 font-sans">
      <div className="w-full max-w-[400px] bg-[#0f1011] border border-[#23252a] rounded-xl p-8 shadow-[0_0_0_1px_#23252a]">
        
        {/* Logo/Wordmark */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <Zap size={20} className="text-[#f7f8f8]" fill="currentColor" />
          <span className="text-[18px] font-bold tracking-tight text-[#f7f8f8]">
            TrueAI
          </span>
        </div>

        {isCheckingSession ? (
          <div className="flex flex-col items-center justify-center py-8">
            <Loader2 size={24} className="text-[#ededed] animate-spin mb-4" />
            <p className="text-[14px] text-[#8a8f98]">Verifying reset link...</p>
          </div>
        ) : !sessionValid ? (
          <div className="flex flex-col items-center text-center py-4">
            <div className="flex items-center justify-center w-12 h-12 rounded-full border border-[#dc2626]/30 bg-[#dc2626]/10 mb-5">
              <AlertCircle size={20} className="text-[#dc2626]" strokeWidth={2} />
            </div>
            <p className="text-[16px] font-medium text-[#f7f8f8]">Invalid or expired link</p>
            <p className="text-[14px] text-[#8a8f98] mt-2 leading-relaxed max-w-[280px]">
              Your password reset link is invalid or has expired. Please request a new one.
            </p>
            <Link
              href="/forgot-password"
              className="mt-8 text-[14px] font-medium text-[#ededed] hover:text-[#ffffff] transition-colors"
            >
              Request new link &rarr;
            </Link>
          </div>
        ) : (
          <>
            <div className="mb-6 text-center">
              <h1 className="text-[22px] font-semibold text-[#f7f8f8] tracking-[-0.4px]">Set new password</h1>
              <p className="text-[14px] text-[#8a8f98] mt-1 font-normal">
                Please enter your new password below
              </p>
            </div>

            {error && (
              <div className="flex items-start gap-2 mb-5 p-3 rounded-lg border border-[#dc2626]/20 bg-[#dc2626]/10">
                <AlertCircle size={14} className="text-[#dc2626] mt-0.5 shrink-0" strokeWidth={2} />
                <p className="text-[13px] text-[#dc2626]">{error}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <div>
                <label htmlFor="reset-password" className="block text-[13px] font-medium text-[#f7f8f8] mb-1.5">
                  New password
                </label>
                <div className="relative">
                  <input
                    id="reset-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    required
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Min. 8 characters"
                    className="w-full h-[42px] pl-[12px] pr-[36px] bg-[#0f1011] border border-[#23252a] rounded-lg text-[14px] text-[#f7f8f8] placeholder-[#62666d] focus:outline-none focus:border-[#34343a] focus:ring-2 focus:ring-[#ededed]/30 transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-[12px] top-1/2 -translate-y-1/2 text-[#62666d] hover:text-[#f7f8f8] transition-colors"
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <div>
                <label htmlFor="reset-confirm-password" className="block text-[13px] font-medium text-[#f7f8f8] mb-1.5">
                  Confirm new password
                </label>
                <div className="relative">
                  <input
                    id="reset-confirm-password"
                    type={showConfirmPassword ? "text" : "password"}
                    autoComplete="new-password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    className={`w-full h-[42px] pl-[12px] pr-[36px] bg-[#0f1011] border rounded-lg text-[14px] text-[#f7f8f8] placeholder-[#62666d] focus:outline-none focus:ring-2 transition-all ${
                      confirmPassword && confirmPassword !== password
                        ? 'border-[#dc2626]/60 focus:border-[#dc2626] focus:ring-[#dc2626]/20'
                        : 'border-[#23252a] focus:border-[#34343a] focus:ring-[#ededed]/30'
                    }`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-[12px] top-1/2 -translate-y-1/2 text-[#62666d] hover:text-[#f7f8f8] transition-colors"
                  >
                    {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {confirmPassword && confirmPassword !== password && (
                  <p className="text-[13px] text-[#dc2626] mt-1.5">Passwords don't match</p>
                )}
              </div>

              <button
                id="reset-submit-btn"
                type="submit"
                disabled={loading || !password || !confirmPassword}
                className="w-full h-[42px] mt-2 flex items-center justify-center gap-2 bg-[#ededed] hover:bg-[#ffffff] text-[#010102] text-[14px] font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading && <Loader2 size={14} className="animate-spin" />}
                {loading ? 'Updating password…' : 'Update password'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
