'use client'

import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

interface TopNavProps {
  userEmail: string | null
}

export function TopNav({ userEmail }: TopNavProps) {
  const router = useRouter()
  const supabase = createClient()

  const handleSignOut = async () => {
    await supabase.auth.signOut()
    router.push('/login')
  }

  return (
    <header className="h-12 bg-[#0a0a0a] border-b border-white/8 flex items-center justify-end px-6 shrink-0">
      <div className="flex items-center gap-3">
        <span className="text-sm text-white/40 hidden sm:block">
          {userEmail ?? ''}
        </span>
        <span className="text-white/20 select-none">|</span>
        <button
          id="sign-out-btn"
          onClick={handleSignOut}
          className="text-sm text-white/40 hover:text-white transition-colors"
        >
          Sign out
        </button>
      </div>
    </header>
  )
}
