import type { Metadata } from 'next'
import Link from 'next/link'

import { NextStepsExample, PullRequestPreview } from '@/components/marketing/figures'
import { breadcrumbs, JsonLd } from '@/components/marketing/json-ld'
import { PageHero, Row, Rows, Section } from '@/components/marketing/page-parts'

export const metadata: Metadata = {
  title: 'How it works',
  description:
    'How TrueAI turns a Sentry error into a reviewed GitHub pull request: reading your code, finding the root cause, checking the fix, and when it stops.',
}

export default function HowItWorksPage() {
  return (
    <>
      <JsonLd data={breadcrumbs('How it works', '/how-it-works')} />

      <PageHero
        name="How it works"
        title="From a Sentry error to a reviewed pull request."
        lede="What happens between the moment Sentry sees a new error and the moment a fix is waiting for you on GitHub, usually within a minute."
      />

      <Section id="steps" title="What happens to each error.">
        <Rows>
          <Row title="1. Sentry sends the error">
            <p>
              When Sentry sees a new issue, it sends it to your TrueAI webhook URL. TrueAI removes secrets and personal data before anything is
              stored, then starts the analysis in the background.
            </p>
            <p>
              If the same error keeps happening while its incident is still open, TrueAI counts the repeats instead of analysing it again, so a noisy
              error never turns into a pile of pull requests.
            </p>
          </Row>
          <Row title="2. The error is classified">
            <p>
              TrueAI decides what kind of problem this is and how serious it is: a bug in your code, a configuration problem, infrastructure, bad data
              or a dependency. This first read sets the direction; the code has the final say.
            </p>
          </Row>
          <Row title="3. Your code is read at one commit">
            <p>
              TrueAI pins your branch to its latest commit and reads the files your stack trace points to at that exact commit, so the analysis and
              the fix always see the same code. Short files are read whole; for longer ones, the code around each line in the trace.
            </p>
            <p>When the cause sits somewhere else, such as a caller, a model or a settings file, it reads that file too before deciding.</p>
          </Row>
          <Row title="4. The root cause is found">
            <p>
              You get the root cause in one sentence, an explanation in plain language and how confident TrueAI is. It also decides whether changing
              code is the right fix at all. If it isn’t, or if the evidence is thin, it writes next steps instead of guessing a patch.
            </p>
          </Row>
          <Row title="5. The smallest fix is written and checked">
            <p>
              The fix is applied to a copy of your files, never straight to your repository. It must apply cleanly, pass a syntax check for Python,
              JSON, YAML and TOML files, and follow the{' '}
              <Link href="/security#guardrails">safety rules every fix has to pass</Link>. When something fails, the problem is fed back and the fix is
              rewritten.
            </p>
          </Row>
          <Row title="6. A second look reviews the fix">
            <p>
              A separate review checks the change against the root cause, looking for regressions and missed edge cases. It approves the fix, asks for
              changes, which sends it back to be rewritten, or rejects it.
            </p>
          </Row>
          <Row title="7. A pull request opens only when every check passes">
            <ul>
              <li>The review approved the fix.</li>
              <li>TrueAI is confident in both the root cause and the review.</li>
              <li>The change isn’t rated high-risk and breaks no safety rule.</li>
              <li>A repository is connected and your GitHub account can push to it.</li>
            </ul>
            <p>
              If any of these fails, no pull request is opened. The incident is marked for your review with the exact reasons, and the drafted change
              is attached as a suggestion you can use or ignore.
            </p>
          </Row>
        </Rows>
      </Section>

      <Section id="pull-request" title="The pull request.">
        <div className="mb-12 max-w-[760px]">
          <PullRequestPreview />
        </div>
        <Rows>
          <Row title="One branch, one commit">
            <p>
              Each incident gets its own branch, <code>trueai/fix-…</code>, created from the exact commit that was analysed. The whole change lands as
              a single commit, labelled <code>trueai</code>. TrueAI never pushes to your base branch and never merges.
            </p>
          </Row>
          <Row title="What the description tells you">
            <p>
              The error and its environment, the category and severity, both confidence scores, the root cause, the explanation, what the change
              does, the review’s notes, the files changed, and links to the incident and the Sentry issue.
            </p>
          </Row>
          <Row title="Running the analysis again">
            <p>
              When you re-run an incident, the revised fix is added to the same pull request as a new commit. Nothing is force-pushed and no duplicate
              pull requests are opened.
            </p>
          </Row>
          <Row title="Merges are tracked">
            <p>
              TrueAI checks open pull requests every ten minutes. When yours is merged, the incident is marked resolved. Closing the pull request
              dismisses the fix and returns the incident to your review queue.
            </p>
          </Row>
        </Rows>
      </Section>

      <section id="next-steps" aria-labelledby="next-steps-title" className="scroll-mt-28 border-t border-rule md:scroll-mt-16">
        <div className="mx-auto grid max-w-[1240px] items-center gap-10 px-4 py-20 sm:px-8 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:gap-16 lg:py-28">
          <div>
            <h2 id="next-steps-title" className="max-w-[18ch] text-balance text-[2rem] font-bold leading-[1.1] tracking-[-0.03em] text-ink sm:text-[2.5rem]">
              When the code isn’t the problem, it says so.
            </h2>
            <div className="mt-5 max-w-[42ch] space-y-4 text-[1.0625rem] leading-[1.65] text-ink-2">
              <p>
                An expired certificate, a missing environment variable or a database that’s down can’t be fixed with a code change, and a patch would
                only hide the problem.
              </p>
              <p>
                For these incidents TrueAI writes a short checklist of what to check and change instead. Every incident that doesn’t become a pull
                request still ends with next steps.
              </p>
            </div>
          </div>
          <NextStepsExample />
        </div>
      </section>
    </>
  )
}
