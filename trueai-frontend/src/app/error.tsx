'use client'

import { useEffect } from 'react'

import { Wordmark } from '@/components/brand'
import { Button, ButtonLink } from '@/components/ui/button'

export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="flex min-h-dvh flex-col bg-paper px-6 py-6 sm:px-10">
      <Wordmark />
      <main id="main" className="flex flex-1 items-center">
        <div className="max-w-md">
          <h1 className="text-[1.75rem] font-bold tracking-[-0.02em] text-ink">Something went wrong</h1>
          <p className="mt-2 text-sm leading-relaxed text-ink-2">
            This page hit an unexpected problem. Trying again usually works; if it keeps happening, the reference below helps
            trace it.
          </p>
          {error.digest && <p className="mt-3 font-mono text-[0.75rem] text-ink-3">Reference {error.digest}</p>}
          <div className="mt-6 flex gap-2">
            <Button onClick={reset}>Try again</Button>
            <ButtonLink href="/dashboard" variant="secondary">
              Go to incidents
            </ButtonLink>
          </div>
        </div>
      </main>
    </div>
  )
}
