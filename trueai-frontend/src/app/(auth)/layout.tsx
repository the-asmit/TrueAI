import type { ReactNode } from 'react'

import { Wordmark } from '@/components/brand'
import { ExampleReport } from '@/components/example-report'

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-dvh bg-paper lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="flex flex-col px-6 py-6 sm:px-10">
        <Wordmark />
        <main id="main" className="flex flex-1 items-center py-12">
          <div className="w-full max-w-[380px]">{children}</div>
        </main>
      </div>
      <aside
        aria-label="What TrueAI produces"
        className="hidden border-l border-rule bg-sunken/60 lg:sticky lg:top-0 lg:flex lg:h-dvh lg:justify-center lg:overflow-y-auto lg:px-12"
      >
        <div className="my-auto w-full max-w-[520px] py-12">
          <p className="mb-4 max-w-[46ch] text-[0.8125rem] leading-relaxed text-ink-2">
            For every Sentry error, TrueAI writes a report like this one — and opens the pull request when it is safe to.
          </p>
          <ExampleReport compact />
        </div>
      </aside>
    </div>
  )
}
