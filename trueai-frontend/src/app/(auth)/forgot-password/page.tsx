'use client'

import { useState, type FormEvent } from 'react'
import Link from 'next/link'
import { Zap, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'

export default function ForgotPasswordPage() {
  const supabase = createClient()

  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'

    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${appUrl}/reset-password`,
    })

    setLoading(false)

    if (resetError) {
      setError(resetError.message)
      return
    }

    setSuccess(true)
  }

  return (
    <div className="min-h-screen bg-[#010102] flex flex-col items-center justify-center px-4 font-sans">
      <div className="w-full max-w-[400px] bg-[#0f1011] border border-[#23252a] rounded-xl p-8 shadow-[0_0_0_1px_#23252a] relative">
        
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
              We sent a password reset link to{' '}
              <span className="text-[#f7f8f8] font-mono">{email}</span>.
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
              <h1 className="text-[22px] font-semibold text-[#f7f8f8] tracking-[-0.4px]">Reset password</h1>
              <p className="text-[14px] text-[#8a8f98] mt-1 font-normal">
                Enter your email to receive a reset link
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
                <label htmlFor="reset-email" className="block text-[13px] font-medium text-[#f7f8f8] mb-1.5">
                  Email
                </label>
                <input
                  id="reset-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full h-[42px] px-[12px] bg-[#0f1011] border border-[#23252a] rounded-lg text-[14px] text-[#f7f8f8] placeholder-[#62666d] focus:outline-none focus:border-[#34343a] focus:ring-2 focus:ring-[#ededed]/30 transition-all font-mono"
                />
              </div>

              <button
                id="reset-submit-btn"
                type="submit"
                disabled={loading || !email}
                className="w-full h-[42px] mt-2 flex items-center justify-center gap-2 bg-[#ededed] hover:bg-[#ffffff] text-[#010102] text-[14px] font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading && <Loader2 size={14} className="animate-spin" />}
                {loading ? 'Sending link…' : 'Send reset link'}
              </button>
            </form>

            <div className="h-[1px] bg-[#23252a] w-full my-6" />

            <p className="text-[13px] text-[#8a8f98] text-center">
              Remember your password?{' '}
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
