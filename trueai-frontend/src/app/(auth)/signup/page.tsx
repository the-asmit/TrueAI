'use client'

import { useState, type FormEvent } from 'react'
import Link from 'next/link'
import { Zap, AlertCircle, CheckCircle2, Loader2, Eye, EyeOff } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'

export default function SignUpPage() {
  const supabase = createClient()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

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

    const { error: authError } = await supabase.auth.signUp({ email, password })

    setLoading(false)

    if (authError) {
      setError(authError.message)
      return
    }

    setSuccess(true)
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

        {success ? (
          <div className="flex flex-col items-center text-center py-4">
            <div className="flex items-center justify-center w-12 h-12 rounded-full border border-[#16a34a]/30 bg-[#16a34a]/10 mb-5">
              <CheckCircle2 size={20} className="text-[#16a34a]" strokeWidth={2} />
            </div>
            <p className="text-[16px] font-medium text-[#f7f8f8]">Check your email</p>
            <p className="text-[14px] text-[#8a8f98] mt-2 leading-relaxed max-w-[280px]">
              We sent a confirmation link to{' '}
              <span className="text-[#f7f8f8] font-mono">{email}</span>.
              Click it to activate your account.
            </p>
            <Link
              href="/login"
              className="mt-8 text-[14px] font-medium text-[#ededed] hover:text-[#ffffff] transition-colors"
            >
              Back to sign in &rarr;
            </Link>
          </div>
        ) : (
          <>
            <div className="mb-6 text-center">
              <h1 className="text-[22px] font-semibold text-[#f7f8f8] tracking-[-0.4px]">Create account</h1>
              <p className="text-[14px] text-[#8a8f98] mt-1 font-normal">
                Start automating incident resolution
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
                <label htmlFor="signup-email" className="block text-[13px] font-medium text-[#f7f8f8] mb-1.5">
                  Email
                </label>
                <input
                  id="signup-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full h-[42px] px-[12px] bg-[#0f1011] border border-[#23252a] rounded-lg text-[14px] text-[#f7f8f8] placeholder-[#62666d] focus:outline-none focus:border-[#34343a] focus:ring-2 focus:ring-[#ededed]/30 transition-all font-mono"
                />
              </div>

              <div>
                <label htmlFor="signup-password" className="block text-[13px] font-medium text-[#f7f8f8] mb-1.5">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="signup-password"
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
                <label htmlFor="signup-confirm-password" className="block text-[13px] font-medium text-[#f7f8f8] mb-1.5">
                  Confirm password
                </label>
                <div className="relative">
                  <input
                    id="signup-confirm-password"
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
                id="signup-submit-btn"
                type="submit"
                disabled={loading}
                className="w-full h-[42px] mt-2 flex items-center justify-center gap-2 bg-[#ededed] hover:bg-[#ffffff] text-[#010102] text-[14px] font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading && <Loader2 size={14} className="animate-spin" />}
                {loading ? 'Creating account…' : 'Create account'}
              </button>
            </form>

            <div className="h-[1px] bg-[#23252a] w-full my-6" />

            <p className="text-[13px] text-[#8a8f98] text-center">
              Already have an account?{' '}
              <Link href="/login" className="text-[#ededed] hover:text-[#ffffff] transition-colors">
                Sign in
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  )
}
