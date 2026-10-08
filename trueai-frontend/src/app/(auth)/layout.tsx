import type { ReactNode } from 'react'

import { GitHubMark, SentryMark, Wordmark } from '@/components/brand'
import { ExampleReport } from '@/components/example-report'
import { ThemeToggle } from '@/components/theme-toggle'

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-dvh bg-paper lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="relative flex flex-col px-5 py-5 sm:px-10">
        <div aria-hidden className="dot-grid absolute inset-0" />
        <header className="relative flex items-center justify-between">
          <Wordmark />
          <ThemeToggle />
        </header>
        <main id="main" className="relative flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[420px]">
            {/* The form sits on a sheet, with larger controls than the app's dense forms. */}
            <div className="rounded-xl border border-rule bg-sheet p-6 shadow-[var(--shadow-sheet)] sm:p-8 [&_h1]:text-[1.75rem] [&_input]:h-11 [&_input]:text-[0.9375rem]">
              {children}
            </div>
            <p className="mt-6 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[0.8125rem] text-ink-3">
              <span>Works with</span>
              <span className="inline-flex items-center gap-1.5 text-ink-2">
                <SentryMark className="size-3.5" /> Sentry
              </span>
              <span className="inline-flex items-center gap-1.5 text-ink-2">
                <GitHubMark className="size-3.5" /> GitHub
              </span>
            </p>
          </div>
        </main>
      </div>
      <aside
        aria-label="What TrueAI produces"
        className="hidden border-l border-rule bg-sunken/60 lg:sticky lg:top-0 lg:flex lg:h-dvh lg:justify-center lg:overflow-y-auto lg:px-12"
      >
        <div className="my-auto w-full max-w-[520px] py-12">
          <p className="mb-4 max-w-[46ch] text-[0.8125rem] leading-relaxed text-ink-2">
            For every Sentry error, TrueAI writes a report like this one, and opens the pull request when it is safe to.
          </p>
          <ExampleReport compact />
        </div>
      </aside>
    </div>
  )
}
