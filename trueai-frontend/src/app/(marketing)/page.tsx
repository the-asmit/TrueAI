import { ArrowRight, ChevronDown } from 'lucide-react'
import Link from 'next/link'

import { GitHubMark, SentryMark } from '@/components/brand'
import { AnswerExhibit, HandoverExhibit } from '@/components/landing/exhibits'
import { FixFlow } from '@/components/landing/fix-flow'
import { SetupSteps } from '@/components/landing/setup-steps'
import { JsonLd } from '@/components/marketing/json-ld'
import { ControlPanels, LearnMore, NIGHT_BUTTON, Section, STAGE_BUTTON } from '@/components/marketing/page-parts'
import { isSignedIn } from '@/lib/session'
import { APP_URL, REPO_URL } from '@/lib/site'

// Shown in the FAQ section and sent to search engines as FAQPage structured data.
const FAQ = [
  {
    question: 'Is my code safe?',
    answer:
      'TrueAI reads only the files your stack trace points to, plus any it needs to follow the cause, at one pinned commit. Secrets and personal data are removed from error data before the AI model sees it, and your GitHub token is stored encrypted. Every change arrives as a pull request: nothing merges without you.',
  },
  {
    question: 'Which languages does it support?',
    answer:
      'TrueAI is not tied to one language. It follows the file paths in Sentry’s stack trace to files in your repository, so it works wherever those paths match: Python, Go or Ruby, for example, and JavaScript or TypeScript with source maps uploaded to Sentry.',
  },
  {
    question: 'Do I need to install anything or change my code?',
    answer:
      'No. If your app already reports errors to Sentry, connect GitHub, choose a repository and add one URL to Sentry. There is nothing to install and no code to change.',
  },
  {
    question: 'Where is the source, and what does it cost?',
    answer: 'The full source is on GitHub, and TrueAI is free to use.',
  },
  {
    question: 'What happens when it can’t fix something?',
    answer:
      'No pull request is opened. The incident is marked for your review with the exact reason, and you get clear next steps. When a patch was drafted but did not pass review or the confidence bar, it is attached as a suggestion you can use or ignore.',
  },
]

export default async function LandingPage() {
  const signedIn = await isSignedIn()
  const primaryHref = signedIn ? '/dashboard' : '/signup'
  const primaryLabel = signedIn ? 'Open your dashboard' : 'Create an account'

  return (
    <>
      <JsonLd data={structuredData()} />

      {/* ---- First viewport: the promise, and one error becoming a fix ---- */}
      <section className="relative overflow-hidden border-b border-rule bg-stage text-stage-ink">
        <div className="relative z-10 mx-auto max-w-[1240px] px-4 pt-14 text-center sm:px-8 sm:pt-16 lg:pt-[min(5rem,7vh)]">
          <h1 className="text-[2.75rem] font-bold leading-[0.98] tracking-[-0.045em] sm:text-[4.5rem] lg:text-[min(5.5rem,10.5vh)]">
            <span className="block">Stop debugging.</span>
            <span className="block">Start merging.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-[44ch] text-[1.0625rem] leading-[1.6] text-stage-ink-2 sm:text-[1.125rem]">
            TrueAI turns every Sentry error into a reviewed fix on GitHub, usually within a minute.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link href={primaryHref} className={STAGE_BUTTON}>
              {primaryLabel} <ArrowRight aria-hidden />
            </Link>
            <Link
              href="/how-it-works"
              className="inline-flex h-11 items-center rounded-md border border-stage-ink/20 px-5 text-[0.9375rem] font-medium text-stage-ink transition-colors hover:border-stage-ink/40 hover:bg-stage-ink/5"
            >
              See how it works
            </Link>
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
        <div className="mx-auto max-w-[1100px] px-4 pb-16 pt-12 sm:px-8 lg:pb-20 lg:pt-14">
          <FixFlow />
        </div>
      </section>

      {/* ---- What arrives with every incident ---- */}
      <Section id="answer" title="Open the alert. The answer is already there." more={{ href: '/how-it-works', label: 'about how TrueAI works' }}>
        <AnswerExhibit />
      </Section>

      {/* ---- Judgment: when code is not the fix ---- */}
      <section className="border-t border-rule">
        <div className="mx-auto grid max-w-[1240px] items-center gap-10 px-4 py-20 sm:px-8 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:gap-16 lg:py-28">
          <div>
            <h2 className="max-w-[18ch] text-balance text-[2rem] font-bold leading-[1.1] tracking-[-0.03em] text-ink sm:text-[2.5rem]">
              When the code isn’t the problem, it says so.
            </h2>
            <p className="mt-5 max-w-[36ch] text-balance text-[1.0625rem] leading-[1.65] text-ink-2">
              A database that’s down gets a checklist, not a risky patch.
            </p>
            <LearnMore href="/how-it-works#next-steps" label="about next steps for incidents code can’t fix" />
          </div>
          <HandoverExhibit />
        </div>
      </section>

      {/* ---- Control ---- */}
      <Section id="control" title="It proposes. You decide." more={{ href: '/security', label: 'about security and privacy' }}>
        <ControlPanels />
      </Section>

      {/* ---- Setup ---- */}
      <Section id="setup" title="Running in five minutes." more={{ href: '/docs', label: 'in the setup guide' }}>
        <SetupSteps />
      </Section>

      {/* ---- Questions: native <details>, so every answer is in the server HTML and works without JavaScript ---- */}
      <Section id="faq" title="Questions, answered.">
        <div className="border-b border-rule">
          {FAQ.map((item) => (
            <details key={item.question} className="group border-t border-rule">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-6 text-[1.125rem] font-semibold text-ink [&::-webkit-details-marker]:hidden">
                {item.question}
                <ChevronDown
                  aria-hidden
                  className="size-5 shrink-0 text-ink-3 transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none"
                />
              </summary>
              <p className="max-w-[68ch] pb-7 text-[1.0625rem] leading-[1.65] text-ink-2">{item.answer}</p>
            </details>
          ))}
        </div>
      </Section>

      {/* ---- Close ---- */}
      <section className="bg-night text-night-ink">
        <div className="mx-auto flex max-w-[1240px] flex-col items-start gap-10 px-4 py-24 sm:px-8 lg:flex-row lg:items-end lg:justify-between lg:py-32">
          <h2 className="max-w-[20ch] text-balance text-[2.5rem] font-bold leading-[1.05] tracking-[-0.035em] sm:text-[3.25rem]">
            The next production error is already on its way.
          </h2>
          <Link href={primaryHref} className={`${NIGHT_BUTTON} shrink-0`}>
            {primaryLabel} <ArrowRight aria-hidden />
          </Link>
        </div>
      </section>
    </>
  )
}

/** What search engines read about TrueAI: the product, who makes it, and the FAQ above. */
function structuredData() {
  const description =
    'TrueAI reads each Sentry error, finds the root cause in your code and opens a reviewed fix as a GitHub pull request.'
  return [
    {
      '@context': 'https://schema.org',
      // SoftwareSourceCode is what makes codeRepository a valid property here.
      '@type': ['SoftwareApplication', 'SoftwareSourceCode'],
      name: 'TrueAI',
      description,
      url: APP_URL,
      applicationCategory: 'DeveloperApplication',
      operatingSystem: 'Web',
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
      codeRepository: REPO_URL,
    },
    {
      '@context': 'https://schema.org',
      '@type': 'Organization',
      name: 'TrueAI',
      url: APP_URL,
      logo: `${APP_URL}/apple-icon.png`,
      sameAs: [REPO_URL],
    },
    {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: FAQ.map((item) => ({
        '@type': 'Question',
        name: item.question,
        acceptedAnswer: { '@type': 'Answer', text: item.answer },
      })),
    },
  ]
}
