import type { EmailOtpType } from '@supabase/supabase-js'
import { NextResponse, type NextRequest } from 'next/server'

import { safeNextPath } from '@/lib/redirect'
import { createClient } from '@/lib/supabase/server'

/**
 * Completes Supabase email links:
 *   - sign-up confirmation     → /onboarding
 *   - password recovery        → /reset-password
 *   - magic link / email change → ?next= (validated) or /dashboard
 * Both link styles are supported: ?token_hash=&type= and PKCE ?code=.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl
  const code = searchParams.get('code')
  const tokenHash = searchParams.get('token_hash')
  const type = searchParams.get('type') as EmailOtpType | null
  const next = searchParams.get('next')

  const supabase = await createClient()
  let error: string | null = null

  if (tokenHash && type) {
    const result = await supabase.auth.verifyOtp({ token_hash: tokenHash, type })
    error = result.error?.message ?? null
  } else if (code) {
    const result = await supabase.auth.exchangeCodeForSession(code)
    error = result.error?.message ?? null
  } else {
    error = 'The link is missing its verification code.'
  }

  if (error) {
    const failure = new URL('/login', origin)
    failure.searchParams.set('error', 'link_invalid')
    return NextResponse.redirect(failure)
  }

  if (type === 'recovery') return NextResponse.redirect(new URL('/reset-password', origin))
  if (type === 'signup' || type === 'invite') return NextResponse.redirect(new URL('/onboarding', origin))
  return NextResponse.redirect(new URL(safeNextPath(next), origin))
}
