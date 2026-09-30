import { NextResponse, type NextRequest } from 'next/server'

import { api, toMessage } from '@/lib/api/client'
import { safeNextPath } from '@/lib/redirect'

/**
 * Final step of connecting GitHub. The API's OAuth callback parks the token
 * under a one-time hand-off code and redirects here; this route (running with
 * the signed-in user's session) claims it, so a GitHub account can only ever
 * attach to the TrueAI account that started the flow.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl
  const handoff = searchParams.get('handoff') ?? ''
  const returnTo = safeNextPath(searchParams.get('return_to'), '/integrations')
  const destination = new URL(returnTo, origin)

  if (handoff.length < 20) {
    destination.searchParams.set('github_error', 'invalid_state')
    return NextResponse.redirect(destination)
  }

  try {
    await api.post('/auth/github/complete', { handoff })
    destination.searchParams.set('github', 'connected')
  } catch (error) {
    destination.searchParams.set('github_error', 'complete_failed')
    destination.searchParams.set('message', toMessage(error).slice(0, 200))
  }
  return NextResponse.redirect(destination)
}
