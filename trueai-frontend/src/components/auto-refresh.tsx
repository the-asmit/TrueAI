'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

/**
 * Re-renders the current server page on an interval: fast while work is in
 * progress, slow otherwise, and never while the tab is hidden.
 */
export function AutoRefresh({ active, fastMs = 4000, slowMs = 30000 }: { active: boolean; fastMs?: number; slowMs?: number }) {
  const router = useRouter()

  useEffect(() => {
    const interval = active ? fastMs : slowMs
    let timer: ReturnType<typeof setInterval> | null = null

    const start = () => {
      if (timer === null) timer = setInterval(() => router.refresh(), interval)
    }
    const stop = () => {
      if (timer !== null) {
        clearInterval(timer)
        timer = null
      }
    }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        router.refresh()
        start()
      } else {
        stop()
      }
    }

    if (document.visibilityState === 'visible') start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [active, fastMs, slowMs, router])

  return null
}
