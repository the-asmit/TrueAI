import { Star } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { GitHubMark, Wordmark } from '@/components/brand'
import { MarketingNav } from '@/components/marketing/marketing-nav'
import { STAGE_BUTTON_SMALL } from '@/components/marketing/page-parts'
import { ThemeToggle } from '@/components/theme-toggle'
import { isSignedIn } from '@/lib/session'
import { REPO_URL } from '@/lib/site'

/** Header and footer shared by the homepage, How it works, Security and Docs. */
export default async function MarketingLayout({ children }: { children: ReactNode }) {
  const signedIn = await isSignedIn()

  return (
    <div className="bg-paper">
      {/* The header shares the heroes' stage so each page's first viewport reads as one surface. */}
      <header className="sticky top-0 z-40 border-b border-stage-ink/10 bg-stage/90 text-stage-ink backdrop-blur-md">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-center justify-between gap-x-6 px-4 sm:px-8 md:h-14 md:flex-nowrap">
          <div className="flex h-14 items-center">
            <Wordmark className="text-stage-ink" />
          </div>
          {/* On phones the links get their own row under the bar. */}
          <MarketingNav className="order-last -mx-4 h-10 w-[calc(100%+2rem)] overflow-x-auto border-t border-stage-ink/10 px-4 sm:-mx-8 sm:w-[calc(100%+4rem)] sm:px-8 md:order-none md:mx-0 md:h-auto md:w-auto md:overflow-visible md:border-0 md:px-0 md:gap-7" />
          <div className="flex h-14 items-center gap-2">
            <ThemeToggle />
            {signedIn ? (
              <Link href="/dashboard" className={STAGE_BUTTON_SMALL}>Open dashboard</Link>
            ) : (
              <>
                <Link href="/login" className="hidden px-2 text-[0.8125rem] text-stage-ink-2 hover:text-stage-ink sm:inline">Sign in</Link>
                <Link href="/signup" className={STAGE_BUTTON_SMALL}>Create account</Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main id="main">{children}</main>

      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-center justify-between gap-4 px-4 py-6 text-[0.8125rem] text-ink-3 sm:px-8">
          <div className="flex items-center gap-3">
            <Wordmark className="text-ink-2" />
            <span>© {new Date().getFullYear()}</span>
          </div>
          <nav aria-label="Footer" className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <Link href="/privacy" className="hover:text-ink">Privacy</Link>
            <Link href="/terms" className="hover:text-ink">Terms</Link>
            <a href={REPO_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 hover:text-ink">
              <Star className="size-3.5" aria-hidden /> Star on GitHub
            </a>
            <a href="https://github.com/the-asmit" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 hover:text-ink">
              <GitHubMark className="size-3.5" /> GitHub
            </a>
            <a href="https://www.linkedin.com/in/asmit-nayan/" target="_blank" rel="noopener noreferrer" className="hover:text-ink">
              LinkedIn
            </a>
          </nav>
        </div>
      </footer>
    </div>
  )
}
