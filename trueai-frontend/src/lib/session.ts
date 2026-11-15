import 'server-only'

import { cache } from 'react'

import { createClient } from '@/lib/supabase/server'

/** Whether this request comes from a signed-in user. Cached per request, so a layout and its page share one check. */
export const isSignedIn = cache(async (): Promise<boolean> => {
  try {
    const supabase = await createClient()
    const {
      data: { user },
    } = await supabase.auth.getUser()
    return Boolean(user)
  } catch {
    return false
  }
})
