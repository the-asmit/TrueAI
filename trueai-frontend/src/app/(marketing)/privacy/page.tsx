import type { Metadata } from 'next'
import Link from 'next/link'

import { breadcrumbs, JsonLd } from '@/components/marketing/json-ld'
import { PageHero, Prose } from '@/components/marketing/page-parts'
import { pageMetadata } from '@/lib/metadata'

export const metadata: Metadata = pageMetadata({
  title: 'Privacy Policy',
  socialTitle: 'TrueAI Privacy Policy',
  description:
    'What TrueAI collects, why, who it shares data with, how private data is removed from error reports, how long data is kept and how to delete it.',
})

// Every statement here describes what the TrueAI code does. Change this page whenever that behaviour changes.
export default function PrivacyPage() {
  return (
    <>
      <JsonLd data={breadcrumbs('Privacy Policy', '/privacy')} />

      <PageHero
        name="Privacy Policy"
        title="Privacy Policy."
        lede="What TrueAI collects, why it needs it, who else sees it and how to have it deleted."
      />

      <Prose>
        <h2 id="who-we-are">Who we are</h2>
        <p>
          This policy covers the TrueAI website, dashboard and service (“TrueAI”, “we”, “us”). You can see and delete your data yourself from your
          account; <a href="#your-choices">Your choices</a> explains how.
        </p>

        <h2 id="what-we-collect">What we collect</h2>
        <p>
          <strong>Your account.</strong> Your email address and password are handled by our authentication provider, Supabase; we never see your
          password. We also keep the name you give us.
        </p>
        <p>
          <strong>Your GitHub connection.</strong> Your GitHub username and user ID, the permissions you granted (the <code>repo</code> and{' '}
          <code>read:user</code> scopes), your GitHub access token, which is encrypted before it is stored, and the repositories and branches you
          choose, including any rules that send specific Sentry projects to specific repositories.
        </p>
        <p>
          <strong>Your Sentry settings.</strong> If you add them: your Sentry organisation slug, a Sentry auth token and your integration’s signing
          secret. The token and secret are encrypted before they are stored.
        </p>
        <p>
          <strong>Webhook keys.</strong> For each key: its name, a short prefix so you can recognise it, when it was last used and whether it was
          revoked. We store only a one-way hash of the key itself, never the key.
        </p>
        <p>
          <strong>Errors Sentry sends us.</strong> When Sentry reports a new issue, we store the error type and message, environment, level,
          platform, the Sentry identifiers and link for the issue, the stack trace and the rest of the event, after the private data described
          below has been removed.
        </p>
        <p>
          <strong>Analysis results.</strong> For each incident: the root cause, explanation and confidence, the proposed code change, the review’s
          notes and the next steps; for a pull request, its link, number, branch and status; and a record of how the analysis ran, used to keep the
          service reliable.
        </p>
        <p>
          <strong>Your source code.</strong> We don’t keep a copy of your repository. When an error is analysed, we read the files involved from
          GitHub at that moment. The proposed change, which contains the changed lines of code, is stored with the incident. A list of your
          repository’s file paths may be cached for up to an hour to speed up repeated analyses.
        </p>
        <p>
          <strong>Technical data.</strong> We use IP addresses to rate-limit requests; these entries expire after a short time. Our servers keep
          operational logs that include account and incident identifiers; log files are rotated, so older entries are removed automatically.
        </p>

        <h2 id="how-we-use-it">How we use it</h2>
        <ul>
          <li>To run the service: receive errors from Sentry, analyse them against your code, open pull requests and track when they are merged.</li>
          <li>To show you your incidents, reports and settings in the dashboard.</li>
          <li>To send the emails that sign-in needs, such as confirming your address and resetting your password.</li>
          <li>To keep the service secure and available, for example by rate-limiting requests and detecting abuse.</li>
        </ul>
        <p>We don’t sell your data, use it for advertising, or use it to train AI models.</p>

        <h2 id="ai-model">What we send to the AI model</h2>
        <p>
          To analyse an error, we send the following to our AI model provider, Groq, after private data has been removed:
        </p>
        <ul>
          <li>The error type and message, level, platform, environment, release, transaction and the chain of exceptions.</li>
          <li>The request method and URL, and the names of request body fields, never their values.</li>
          <li>The runtime and up to twelve tags from the event.</li>
          <li>The stack frames from your own code, with a few lines around each, and the last few breadcrumbs.</li>
          <li>Excerpts of the files involved from your repository, and the proposed change.</li>
        </ul>
        <p>Groq’s own terms and data policy apply to what it receives.</p>

        <h2 id="private-data">How private data is removed</h2>
        <p>Before an error from Sentry is stored or sent anywhere, we automatically remove:</p>
        <ul>
          <li>
            The value of any field whose name suggests a secret or personal data, such as password, token, secret, auth, cookie, session, API key,
            private key, credential, signature, CSRF, card number, CVV, SSN or IBAN.
          </li>
          <li>
            Values that look like secrets or personal data wherever they appear: web tokens, bearer and basic credentials, GitHub tokens, common API
            keys, AWS access keys, private keys, usernames and passwords inside URLs, email addresses, and long digit sequences such as card numbers.
          </li>
        </ul>
        <p>
          This is automatic and can’t catch everything, for example a name in a free-text message. Configure Sentry not to send personal data you
          don’t need to share.
        </p>

        <h2 id="who-we-share-with">Who we share data with</h2>
        <p>We share data only with the services we need to run TrueAI, and only for that purpose:</p>
        <ul>
          <li>
            <strong>Supabase</strong>: our database and authentication provider, which also sends sign-in emails.
          </li>
          <li>
            <strong>Groq</strong>: the AI model provider, which receives the data described above.
          </li>
          <li>
            <strong>GitHub</strong>: we read your repositories and open pull requests there on your behalf.
          </li>
          <li>
            <strong>Sentry</strong>: we receive errors from Sentry and, if you add a Sentry token, fetch full events from it.
          </li>
          <li>
            <strong>Hosting and infrastructure providers</strong>: run the servers, networks and storage TrueAI depends on.
          </li>
        </ul>
        <p>We may also disclose data where the law requires it.</p>

        <h2 id="cookies">Cookies</h2>
        <p>
          We use cookies only to keep you signed in, and one cookie, <code>theme</code>, to remember whether you chose the light or dark theme (kept
          for a year). We don’t use analytics or advertising cookies.
        </p>

        <h2 id="retention">How long we keep data</h2>
        <ul>
          <li>Your account, connections and incidents are kept while your account is open.</li>
          <li>You can delete any incident and its report from the dashboard at any time.</li>
          <li>
            Deleting your account removes your account and everything that belongs to it: incidents, reports, connections, settings and keys.
          </li>
          <li>Short-lived technical data, such as rate-limit entries and cached file lists, expires on its own.</li>
          <li>
            Pull requests we opened live in your repository on GitHub, and errors stay in your Sentry account; deleting your TrueAI account doesn’t
            remove them.
          </li>
        </ul>

        <h2 id="security">How we protect it</h2>
        <p>
          Tokens and secrets are encrypted before they are stored, webhook keys are stored only as hashes, the database denies all direct access
          from browsers, and every connection to the service is encrypted. <Link href="/security">Security</Link> describes this in more detail.
        </p>

        <h2 id="your-choices">Your choices</h2>
        <ul>
          <li>See everything we hold about your incidents and connections in your dashboard.</li>
          <li>
            Disconnect GitHub under Integrations: this revokes TrueAI’s authorisation at GitHub and deletes the stored token. You can also remove
            TrueAI under your GitHub account’s settings, in Applications.
          </li>
          <li>Revoke webhook keys under Settings.</li>
          <li>Delete your account, and everything that belongs to it, under Settings, in the Danger zone.</li>
        </ul>
        <p>
          Depending on where you live, you may have further rights over your data. Access and deletion are available to you directly in your
          account settings at any time.
        </p>

        <h2 id="children">Children</h2>
        <p>TrueAI is a tool for software teams and isn’t intended for children.</p>

        <h2 id="changes">Changes to this policy</h2>
        <p>
          When we change this policy, we update it here and change the date below. For significant changes, we’ll tell you by email or in the
          dashboard.
        </p>
        <p>Last updated: 15 November 2026</p>
      </Prose>
    </>
  )
}
