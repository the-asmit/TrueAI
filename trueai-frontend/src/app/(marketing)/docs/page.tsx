import type { Metadata } from 'next'
import Link from 'next/link'

import { breadcrumbs, JsonLd } from '@/components/marketing/json-ld'
import { PageHero, Row, Rows, Section } from '@/components/marketing/page-parts'
import { pageMetadata } from '@/lib/metadata'

export const metadata: Metadata = pageMetadata({
  title: { absolute: 'TrueAI docs: connect Sentry and GitHub' },
  socialTitle: 'TrueAI docs: connect Sentry and GitHub',
  description:
    'Set up TrueAI in minutes: connect GitHub, add your webhook URL to Sentry, then review incidents, manage connections and fix common setup problems.',
})

const CONTENTS = [
  { href: '#quick-start', label: 'Quick start' },
  { href: '#sentry', label: 'Connect Sentry' },
  { href: '#dashboard', label: 'Using the dashboard' },
  { href: '#connections', label: 'Managing connections' },
  { href: '#troubleshooting', label: 'Troubleshooting' },
  { href: '#account', label: 'Your account' },
]

export default function DocsPage() {
  return (
    <>
      <JsonLd data={breadcrumbs('Docs', '/docs')} />

      <PageHero
        name="Docs"
        title="Set up TrueAI."
        lede="Connect GitHub, add one URL to Sentry, and your next production error arrives with a fix. Everything after that happens in your dashboard."
      >
        <nav aria-label="On this page" className="mt-10">
          <ul className="flex flex-wrap gap-2">
            {CONTENTS.map((item) => (
              <li key={item.href}>
                <a
                  href={item.href}
                  className="inline-flex h-8 items-center rounded-md border border-stage-ink/20 px-3 text-[0.8125rem] text-stage-ink transition-colors hover:border-stage-ink/40 hover:bg-stage-ink/5"
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </PageHero>

      <Section id="quick-start" title="Quick start." lede="About five minutes, all from the dashboard.">
        <Rows>
          <Row title="1. Create an account">
            <p>
              <Link href="/signup">Sign up</Link> with your email and confirm it from the link we send.
            </p>
          </Row>
          <Row title="2. Connect GitHub">
            <p>
              Authorise TrueAI on GitHub, then choose the repository and branch your errors come from. TrueAI asks for the <code>repo</code> and{' '}
              <code>read:user</code> scopes; <Link href="/security#github">here is what it does with them</Link>.
            </p>
          </Row>
          <Row title="3. Create your webhook URL">
            <p>
              Create the URL in the last setup step and copy it straight away. It contains a secret key and is shown only once; if you lose it, create
              a new one and revoke the old key in Settings.
            </p>
          </Row>
          <Row title="4. Add it to Sentry">
            <p>
              Follow <a href="#sentry">Connect Sentry</a> below. The next new error in that Sentry project appears in your dashboard.
            </p>
          </Row>
        </Rows>
      </Section>

      <Section id="sentry" title="Connect Sentry.">
        <Rows>
          <Row title="Create an Internal Integration">
            <ol>
              <li>
                In Sentry, open <strong>Settings → Developer Settings → Custom Integrations</strong> and create an <strong>Internal Integration</strong>.
              </li>
              <li>
                Paste your TrueAI URL into <strong>Webhook URL</strong> and turn on <strong>Alert Rule Action</strong>.
              </li>
              <li>
                Give it <strong>Read</strong> access to <strong>Issue &amp; Event</strong>, then save.
              </li>
            </ol>
          </Row>
          <Row title="Add an alert rule">
            <p>
              In your project’s alerts, create a rule: <strong>A new issue is created</strong> → <strong>Send a notification via</strong> your
              integration. Every new issue in that project now reaches TrueAI.
            </p>
          </Row>
          <Row title="Using the older WebHooks plugin">
            <p>
              Paste the URL under <strong>Project Settings → Legacy Integrations → WebHooks</strong> instead, and send new issues to it from an alert
              rule. Keep only your current TrueAI URL there.
            </p>
          </Row>
          <Row title="Check that it works">
            <p>
              Trigger an error in your app. It appears on your dashboard within seconds, first as being analysed, then with its report, usually within
              a minute.
            </p>
          </Row>
        </Rows>
      </Section>

      <Section id="dashboard" title="Using the dashboard.">
        <Rows>
          <Row title="Incident statuses">
            <ul>
              <li>
                <strong>Analysing</strong>: TrueAI is working on it.
              </li>
              <li>
                <strong>Pull request open</strong>: a reviewed fix is waiting for you on GitHub.
              </li>
              <li>
                <strong>Needs you</strong>: TrueAI diagnosed it, but a person has to act. The next steps are attached.
              </li>
              <li>
                <strong>Resolved</strong>: the fix was merged, or someone marked the incident resolved.
              </li>
              <li>
                <strong>Analysis failed</strong>: the analysis couldn’t finish. You can run it again.
              </li>
            </ul>
          </Row>
          <Row title="Reading a report">
            <p>
              Open an incident to see the root cause, the explanation, the proposed change and how confident TrueAI is, with a link to the pull request
              or the next steps. <Link href="/how-it-works">How it works</Link> explains what happens before a report appears.
            </p>
          </Row>
          <Row title="Reviewing the fix">
            <p>
              Review and merge the pull request on GitHub like any other. Once it’s merged, the incident is marked resolved on its own, within about ten
              minutes. Closing the pull request instead dismisses the fix and returns the incident to your queue.
            </p>
          </Row>
          <Row title="Acting on an incident">
            <p>
              <strong>Run analysis again</strong> after you change something, such as fixing a configuration problem or connecting a repository.{' '}
              <strong>Mark resolved</strong>, <strong>Ignore</strong> and <strong>Reopen</strong> keep your list tidy, and{' '}
              <strong>Delete incident</strong> removes it and its report for good.
            </p>
          </Row>
        </Rows>
      </Section>

      <Section id="connections" title="Managing connections.">
        <Rows>
          <Row title="Repository and branch">
            <p>
              Change the repository or branch TrueAI works on at any time under <strong>Integrations → GitHub</strong>. New incidents use your choice
              straight away.
            </p>
          </Row>
          <Row title="Several Sentry projects">
            <p>
              Under <strong>Integrations → Project routing</strong>, send incidents from specific Sentry projects to their own repositories. Everything
              else goes to your default repository.
            </p>
          </Row>
          <Row title="Signing secret">
            <p>
              Copy your Sentry integration’s <strong>Client Secret</strong> into <strong>Integrations → Signing secret</strong>. TrueAI then checks
              every delivery’s signature and rejects any that don’t match.
            </p>
          </Row>
          <Row title="Sentry API access">
            <p>
              Some Sentry alerts arrive without a stack trace. Add your organisation slug and a Sentry auth token with event read access under{' '}
              <strong>Integrations → API access</strong>, and TrueAI fetches the full event when it needs to.
            </p>
          </Row>
          <Row title="Webhook keys">
            <p>
              Every webhook URL has its own key, listed under <strong>Settings → API keys</strong>. Revoke a key there and Sentry deliveries using that
              URL stop at once.
            </p>
          </Row>
          <Row title="Disconnecting GitHub">
            <p>
              <strong>Disconnect GitHub</strong> under Integrations revokes TrueAI’s authorisation at GitHub and deletes the stored token. Pull requests
              already opened stay on GitHub.
            </p>
          </Row>
        </Rows>
      </Section>

      <Section id="troubleshooting" title="Troubleshooting.">
        <Rows>
          <Row title="Errors don’t appear in the dashboard">
            <ul>
              <li>Check that your alert rule fires on <strong>A new issue is created</strong> and sends to your integration or WebHooks plugin.</li>
              <li>Sentry only alerts on new issues: another occurrence of an issue it has already seen doesn’t send anything.</li>
              <li>Make sure the URL in Sentry is complete and its key hasn’t been revoked in Settings.</li>
            </ul>
          </Row>
          <Row title="No pull request was opened">
            <p>
              The incident shows the exact reasons. The most common: the change was too large or touched a protected file, confidence was too low, or
              your GitHub account can’t push to the repository. When it’s about access, make sure the account you connected has write access.
            </p>
          </Row>
          <Row title="The report has no code">
            <p>
              Either the event arrived without a stack trace (add <a href="#connections">Sentry API access</a>), or its file paths don’t match files in
              your repository. Check that the right repository and branch are connected; for JavaScript and TypeScript, upload source maps to Sentry
              so its paths point at your source files.
            </p>
          </Row>
          <Row title="The analysis failed">
            <p>
              The analysis couldn’t finish, for example because a service it relies on was briefly unavailable. Open the incident and choose{' '}
              <strong>Run analysis again</strong>.
            </p>
          </Row>
        </Rows>
      </Section>

      <Section id="account" title="Your account.">
        <Rows>
          <Row title="Profile">
            <p>
              Change your name under <strong>Settings → Profile</strong>.
            </p>
          </Row>
          <Row title="Password">
            <p>
              Forgot it? Choose <Link href="/forgot-password">Forgot password?</Link> on the sign-in page and follow the link we email you.
            </p>
          </Row>
          <Row title="Deleting your account">
            <p>
              <strong>Settings → Danger zone → Delete account</strong> removes your account and everything that belongs to it: incidents, reports,
              connections and keys, and revokes TrueAI’s authorisation at GitHub. Pull requests already opened stay on GitHub.
            </p>
          </Row>
        </Rows>
      </Section>
    </>
  )
}
