import type { Metadata } from 'next'

import { RedactionExample } from '@/components/marketing/figures'
import { breadcrumbs, JsonLd } from '@/components/marketing/json-ld'
import { PageHero, Row, Rows, Section } from '@/components/marketing/page-parts'
import { pageMetadata } from '@/lib/metadata'

export const metadata: Metadata = pageMetadata({
  title: { absolute: 'Security and privacy: what TrueAI can access' },
  socialTitle: 'Security and privacy: what TrueAI can access',
  description:
    'What TrueAI can access on GitHub, what it stores, what it sends to the AI model, how private data is removed and the rules every fix must pass.',
})

export default function SecurityPage() {
  return (
    <>
      <JsonLd data={breadcrumbs('Security', '/security')} />

      <PageHero
        name="Security"
        title="What TrueAI can see, keep and change."
        lede="The GitHub access it asks for, the data it stores, what it sends to the AI model, and the rules every fix has to pass before it reaches you."
      />

      <Section id="github" title="GitHub access.">
        <Rows>
          <Row title="Permissions requested">
            <p>
              TrueAI connects through a GitHub OAuth App and asks for two scopes: <code>repo</code> and <code>read:user</code>.
            </p>
            <p>
              GitHub doesn’t let an OAuth App limit itself to one repository, so <code>repo</code> grants read and write access to the repositories
              your account can reach, private ones included. <code>read:user</code> reads your profile, such as your username.
            </p>
          </Row>
          <Row title="What TrueAI does with that access">
            <ul>
              <li>Lists your repositories and branches so you can choose one during setup.</li>
              <li>Reads files from the repository you chose, at the commit being analysed.</li>
              <li>Checks that your account can push to that repository.</li>
              <li>
                Creates a <code>trueai/fix-…</code> branch, one commit and a pull request for each fix.
              </li>
              <li>Checks your pull requests’ status, to see when one is merged or closed.</li>
            </ul>
            <p>It never pushes to your base branch and never merges anything.</p>
          </Row>
          <Row title="How your token is kept">
            <p>
              Your GitHub token is encrypted before it is stored, is only decrypted on the server when TrueAI needs it, and is never sent to your
              browser. The link that connects GitHub is signed and expires, so a forged link can’t attach another account.
            </p>
            <p>
              Disconnecting GitHub in Integrations revokes TrueAI’s authorisation at GitHub and deletes the stored token.
            </p>
          </Row>
        </Rows>
      </Section>

      <Section id="storage" title="What’s stored.">
        <Rows>
          <Row title="Your account">
            <p>Your email and password are handled by Supabase Auth. TrueAI keeps your name.</p>
          </Row>
          <Row title="Connections">
            <p>
              Your GitHub username, the scopes you granted and your encrypted token; the repository and branch you chose; and, if you add them, your
              Sentry organisation slug with an encrypted Sentry token and signing secret.
            </p>
          </Row>
          <Row title="Webhook keys">
            <p>Only a one-way hash of each key. The full webhook URL is shown once, when you create it.</p>
          </Row>
          <Row title="Incidents">
            <p>
              The error type and message, environment, level and platform, and the Sentry event with secrets and personal data already removed.
            </p>
          </Row>
          <Row title="Analyses and pull requests">
            <p>
              The root cause, explanation and confidence, the proposed change, the review’s notes and the next steps; for pull requests, the link,
              number, branch and status.
            </p>
          </Row>
          <Row title="Who can read it">
            <p>
              Everything lives in a Supabase Postgres database with row-level security on and no direct access from the browser. The dashboard reads
              through the TrueAI API, which only returns your own data.
            </p>
            <p>You can delete any incident, or delete your account to remove everything that belongs to it.</p>
          </Row>
        </Rows>
      </Section>

      <Section id="ai" title="What’s sent to the AI model.">
        <Rows>
          <Row title="From Sentry">
            <ul>
              <li>The error type and message, level, platform, environment, release, transaction and the chain of exceptions.</li>
              <li>The request method and URL, and the names of request body fields, never their values.</li>
              <li>The runtime and up to twelve tags.</li>
              <li>The stack frames from your own code, with a few lines around each, and the last few breadcrumbs.</li>
            </ul>
            <p>All of it after secrets and personal data have been removed, as described below.</p>
          </Row>
          <Row title="From your repository">
            <p>
              The files your stack trace points to: whole when they are short, otherwise the code around the relevant lines. Also any other file the
              analysis needs to follow the cause, and the proposed change itself. Nothing else from your repository is sent.
            </p>
          </Row>
          <Row title="The model provider">
            <p>TrueAI sends this to its AI model provider, Groq. The provider’s own data policy applies to what it receives.</p>
          </Row>
          <Row title="Treated as data, not instructions">
            <p>
              Error data and code are passed to the model as clearly marked evidence. Text inside an error message, a request or a source file can’t
              take over the analysis or change what TrueAI does.
            </p>
          </Row>
        </Rows>
      </Section>

      <Section id="privacy" title="How private data is removed.">
        <div className="mb-12 max-w-[860px]">
          <RedactionExample />
        </div>
        <Rows>
          <Row title="By field name">
            <p>
              Any field whose name contains password, secret, token, auth, cookie, session, API key, private key, credential, signature, CSRF, card
              number, CVV, SSN or IBAN has its value replaced with <code>[Filtered]</code>, wherever it appears in the event.
            </p>
          </Row>
          <Row title="By what the value looks like">
            <p>
              JSON web tokens, bearer and basic credentials, GitHub tokens, common API keys, AWS access keys, private keys, usernames and passwords
              inside URLs, email addresses, and long digit sequences such as card numbers are replaced wherever they appear, including in messages,
              URLs and headers.
            </p>
          </Row>
          <Row title="When it happens">
            <p>As each Sentry event arrives: before it is stored, and so before anything is sent to the AI model.</p>
          </Row>
        </Rows>
      </Section>

      <Section id="guardrails" title="Rules every fix must pass.">
        <Rows>
          <Row title="Small and focused">
            <p>At most five files and 200 changed lines, and never removing more than half of a file.</p>
          </Row>
          <Row title="Protected files stay untouched">
            <p>
              CI and deployment pipelines, Dockerfiles and Compose files, lockfiles, <code>.env</code> files, keys and certificates, Terraform,
              CODEOWNERS and package registry settings always need a human.
            </p>
          </Row>
          <Row title="No risky code">
            <p>
              A fix may not add <code>eval</code> or <code>exec</code>, shell commands, unsafe deserialisation, disabled TLS verification,
              download-and-run scripts, embedded credentials or disabled authentication checks, unless the file already contains them.
            </p>
          </Row>
          <Row title="If a rule is broken">
            <p>No pull request is opened. The change is attached to the incident as a suggestion, with the rule it broke, for you to decide.</p>
          </Row>
        </Rows>
      </Section>

      <Section id="webhook" title="Webhook protection.">
        <Rows>
          <Row title="Keys">
            <p>Every webhook URL carries its own key. Only its hash is stored, and you can revoke a key at any time.</p>
          </Row>
          <Row title="Signatures">
            <p>Add your Sentry integration’s signing secret and TrueAI checks the signature of every delivery, rejecting any that don’t match.</p>
          </Row>
          <Row title="Limits">
            <p>Deliveries are rate-limited per key, payloads are capped at 2 MB, and a repeated delivery of the same Sentry event is ignored.</p>
          </Row>
        </Rows>
      </Section>
    </>
  )
}
