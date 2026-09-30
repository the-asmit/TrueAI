import { NextResponse, type NextRequest } from 'next/server'

import { createClient } from '@/lib/supabase/server'

/** Signs out server-side (clears the session cookies) and returns to the sign-in page. */
export async function POST(request: NextRequest) {
  const supabase = await createClient()
  await supabase.auth.signOut()
  return NextResponse.redirect(new URL('/login?signed_out=1', request.nextUrl.origin), { status: 303 })
}
