import { ArrowRight } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { GitHubMark, SentryMark, Wordmark } from '@/components/brand'
import { AnswerExhibit, HandoverExhibit, MergePanel, PrivacyPanel, RecordPanel } from '@/components/landing/exhibits'
import { FixStream } from '@/components/landing/fix-stream'
import { ButtonLink } from '@/components/ui/button'
import { createClient } from '@/lib/supabase/server'

// Light buttons on the dark stage (the hero, its header and the closing band).
const STAGE_BUTTON =
  'inline-flex h-11 items-center gap-2 rounded-md bg-stage-ink px-5 text-[0.9375rem] font-medium text-stage transition-opacity hover:opacity-90 focus-visible:outline-stage-ink [&_svg]:size-4'
const STAGE_BUTTON_SMALL =
  'inline-flex h-8 items-center rounded-md bg-stage-ink px-3 text-[0.8125rem] font-medium text-stage transition-opacity hover:opacity-90 focus-visible:outline-stage-ink'

const CONTROLS = [
  {
    title: 'Nothing merges without you.',
    body: 'Every fix arrives as a pull request. Your review and your CI stay exactly as they are.',
    panel: <MergePanel />,
  },
  {
    title: 'Every step is on the record.',
    body: 'Each incident shows every step TrueAI took, when it took it, and why it decided what it did.',
    panel: <RecordPanel />,
  },
  {
    title: 'Private data stays private.',
    body: 'Cookies, tokens, emails and request bodies are removed before anything is stored or read by a model.',
    panel: <PrivacyPanel />,
  },
]

const SETUP = [
  { title: 'Connect GitHub', body: 'Sign in with GitHub and choose the repository and branch.' },
  { title: 'Add one URL to Sentry', body: 'TrueAI gives you a webhook URL to paste into a Sentry integration.' },
  { title: 'Get your first fix', body: 'The next error arrives with its root cause, and a pull request when it is safe.' },
]

export default async function LandingPage() {
  let signedIn = false
  try {
    const supabase = await createClient()
    const {
      data: { user },
    } = await supabase.auth.getUser()
    signedIn = Boolean(user)
  } catch {
    signedIn = false
  }
  const primaryHref = signedIn ? '/dashboard' : '/signup'
  const primaryLabel = signedIn ? 'Open your dashboard' : 'Create an account'

  return (
    <div className="bg-paper">
      {/* The header shares the hero's dark stage so the first viewport reads as one surface. */}
      <header className="sticky top-0 z-40 border-b border-white/10 bg-stage/90 text-stage-ink backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1240px] items-center justify-between gap-6 px-4 sm:px-8">
          <Wordmark className="text-stage-ink" />
          <nav aria-label="Page" className="hidden items-center gap-7 text-[0.8125rem] text-stage-ink-2 md:flex">
            <a href="#answer" className="hover:text-stage-ink">How it works</a>
            <a href="#control" className="hover:text-stage-ink">Safety</a>
            <a href="#setup" className="hover:text-stage-ink">Setup</a>
          </nav>
          <div className="flex items-center gap-2">
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

      <main id="main">
        {/* ---- First viewport: the promise, and errors turning into fixes ---- */}
        <section className="relative overflow-hidden bg-stage text-stage-ink">
          <div className="relative z-10 mx-auto max-w-[1240px] px-4 pt-14 text-center sm:px-8 sm:pt-16 lg:pt-[min(5rem,7vh)]">
            <h1 className="text-[2.75rem] font-bold leading-[0.98] tracking-[-0.045em] sm:text-[4.5rem] lg:text-[min(5.5rem,10.5vh)]">
              <span className="block">Stop debugging.</span>
              <span className="block">Start merging.</span>
            </h1>
            <p className="mx-auto mt-6 max-w-[56ch] text-[1.0625rem] leading-[1.6] text-stage-ink-2 sm:text-[1.125rem]">
              TrueAI reads every Sentry error, finds the root cause in your code and opens a reviewed fix as a pull request,
              usually within a minute. When code isn’t the answer, you get the exact next steps instead.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <Link href={primaryHref} className={STAGE_BUTTON}>
                {primaryLabel} <ArrowRight aria-hidden />
              </Link>
              <a
                href="#answer"
                className="inline-flex h-11 items-center rounded-md border border-white/20 px-5 text-[0.9375rem] font-medium text-stage-ink transition-colors hover:border-white/40 hover:bg-white/5"
              >
                See how it works
              </a>
            </div>
            <p className="mt-8 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[0.8125rem] text-stage-ink-2">
              <span>Works with</span>
              <span className="inline-flex items-center gap-1.5 text-stage-ink">
                <SentryMark className="size-4" /> Sentry
              </span>
              <span className="inline-flex items-center gap-1.5 text-stage-ink">
                <GitHubMark className="size-4" /> GitHub
              </span>
            </p>
          </div>
          <FixStream className="h-[400px] sm:h-[480px] lg:h-[540px]" />
        </section>

        {/* ---- What arrives with every incident ---- */}
        <Section
          id="answer"
          title="Open the alert. The answer is already there."
          lede="Every incident comes with the root cause in plain English, the exact change that fixes it, and a second opinion on that change. Nothing left to dig through."
        >
          <AnswerExhibit />
        </Section>

        {/* ---- Judgment: when code is not the fix ---- */}
        <section className="border-t border-rule">
          <div className="mx-auto grid max-w-[1240px] items-center gap-10 px-4 py-20 sm:px-8 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:gap-16 lg:py-28">
            <div>
              <h2 className="max-w-[18ch] text-balance text-[2rem] font-bold leading-[1.1] tracking-[-0.03em] text-ink sm:text-[2.5rem]">
                When the code isn’t the problem, it says so.
              </h2>
              <p className="mt-5 max-w-[44ch] text-[1.0625rem] leading-[1.65] text-ink-2">
                A database that’s down or a secret that’s missing gets a checklist written for that exact incident, not a risky
                patch. And when TrueAI isn’t sure, it hands you the diagnosis instead of guessing.
              </p>
            </div>
            <HandoverExhibit />
          </div>
        </section>

        {/* ---- Control ---- */}
        <Section
          id="control"
          title="It proposes. You decide."
          lede="Handing production errors to AI only works if you stay in charge. TrueAI never acts alone, never hides a step, and never sees what it doesn’t need."
        >
          <ul className="grid gap-x-8 gap-y-12 md:grid-cols-3">
            {CONTROLS.map((item) => (
              <li key={item.title}>
                {item.panel}
                <p className="mt-5 text-[1.0625rem] font-semibold text-ink">{item.title}</p>
                <p className="mt-1.5 max-w-[38ch] text-[0.9375rem] leading-relaxed text-ink-2">{item.body}</p>
              </li>
            ))}
          </ul>
        </Section>

        {/* ---- Setup ---- */}
        <Section id="setup" title="Running in five minutes." lede="Nothing to configure and no infrastructure to run. Sign up, connect two tools, and keep working.">
          <ol className="grid gap-x-8 gap-y-10 md:grid-cols-3">
            {SETUP.map((step, index) => (
              <li key={step.title} className="border-t-2 border-ink pt-5">
                <p className="tabular text-[0.875rem] text-ink-3">{index + 1}</p>
                <p className="mt-2 text-[1.0625rem] font-semibold text-ink">{step.title}</p>
                <p className="mt-1.5 max-w-[36ch] text-[0.9375rem] leading-relaxed text-ink-2">{step.body}</p>
              </li>
            ))}
          </ol>
          <ButtonLink href={primaryHref} size="lg" iconEnd={<ArrowRight />} className="mt-12">
            {signedIn ? 'Open your dashboard' : 'Create your account'}
          </ButtonLink>
        </Section>

        {/* ---- Close ---- */}
        <section className="bg-stage text-stage-ink">
          <div className="mx-auto flex max-w-[1240px] flex-col items-start gap-10 px-4 py-24 sm:px-8 lg:flex-row lg:items-end lg:justify-between lg:py-32">
            <div>
              <h2 className="max-w-[20ch] text-balance text-[2.5rem] font-bold leading-[1.05] tracking-[-0.035em] sm:text-[3.25rem]">
                The next production error is already on its way.
              </h2>
              <p className="mt-5 max-w-[42ch] text-[1.0625rem] leading-relaxed text-stage-ink-2">Let TrueAI take the first look, so you don’t have to.</p>
            </div>
            <Link href={primaryHref} className={`${STAGE_BUTTON} shrink-0`}>
              {primaryLabel} <ArrowRight aria-hidden />
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-center justify-between gap-4 px-4 py-6 text-[0.8125rem] text-ink-3 sm:px-8">
          <div className="flex items-center gap-3">
            <Wordmark className="text-ink-2" />
            <span>© {new Date().getFullYear()}</span>
          </div>
          <nav aria-label="Contact" className="flex items-center gap-5">
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

function Section({ id, title, lede, children }: { id: string; title: string; lede: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-14 border-t border-rule">
      <div className="mx-auto max-w-[1240px] px-4 py-20 sm:px-8 lg:py-28">
        <h2 id={`${id}-title`} className="max-w-[22ch] text-balance text-[2rem] font-bold leading-[1.1] tracking-[-0.03em] text-ink sm:text-[2.5rem]">
          {title}
        </h2>
        <p className="mt-5 max-w-[56ch] text-[1.0625rem] leading-[1.65] text-ink-2">{lede}</p>
        <div className="mt-12 lg:mt-14">{children}</div>
      </div>
    </section>
  )
}
