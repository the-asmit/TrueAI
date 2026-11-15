import type { Metadata } from 'next'
import Link from 'next/link'

import { breadcrumbs, JsonLd } from '@/components/marketing/json-ld'
import { PageHero, Prose } from '@/components/marketing/page-parts'
import { pageMetadata } from '@/lib/metadata'

export const metadata: Metadata = pageMetadata({
  title: 'Terms of Service',
  socialTitle: 'TrueAI Terms of Service',
  description:
    'The terms for using TrueAI: your account, your code and data, AI-proposed changes you review before merging, acceptable use and liability.',
})

// Describes the service as the TrueAI code provides it. Change this page whenever that behaviour changes.
export default function TermsPage() {
  return (
    <>
      <JsonLd data={breadcrumbs('Terms of Service', '/terms')} />

      <PageHero
        name="Terms of Service"
        title="Terms of Service."
        lede="The agreement between you and TrueAI when you create an account or use the service."
      />

      <Prose>
        <h2 id="agreement">The agreement</h2>
        <p>
          These terms are an agreement between you and TrueAI (“we”, “us”). By creating an account or using TrueAI, you agree to them. If you use
          TrueAI for an organisation, you confirm that you may accept these terms on its behalf.
        </p>

        <h2 id="the-service">The service</h2>
        <p>
          TrueAI receives errors that Sentry sends to your webhook URL, analyses them against the code in the GitHub repositories you connect, and
          either proposes a fix as a pull request or gives you next steps. <Link href="/how-it-works">How it works</Link> describes this in detail.
        </p>

        <h2 id="your-account">Your account</h2>
        <ul>
          <li>Give accurate information when you sign up, and keep your password and webhook URLs secret.</li>
          <li>
            You are responsible for activity under your account. If you think it has been misused, change your password and revoke your webhook keys
            under Settings.
          </li>
          <li>
            Only connect GitHub repositories and Sentry projects you are allowed to, and only send us data you have the right to share.
          </li>
        </ul>

        <h2 id="your-code">Your code and data</h2>
        <p>
          You keep all rights to your code, your error data and the pull requests TrueAI opens for you. You allow us to access, process and
          transmit them, including to the service providers listed in our <Link href="/privacy">Privacy Policy</Link>, only as needed to run TrueAI
          for you. The Privacy Policy explains what we collect and how we handle it.
        </p>

        <h2 id="ai-changes">Changes proposed by AI</h2>
        <p>
          Fixes, explanations and next steps are produced by AI. They can be wrong, incomplete or unsuitable for your code even after TrueAI’s own
          review. TrueAI never merges anything: every change arrives as a pull request for you to review. You decide what to merge and deploy, and
          you are responsible for those decisions.
        </p>

        <h2 id="acceptable-use">Acceptable use</h2>
        <p>Don’t use TrueAI to:</p>
        <ul>
          <li>break the law or infringe anyone’s rights;</li>
          <li>attack, overload or disrupt the service, or get around its rate limits or security;</li>
          <li>access accounts, repositories or data that aren’t yours to access;</li>
          <li>send us data you have no right to share.</li>
        </ul>

        <h2 id="third-parties">Other services</h2>
        <p>
          TrueAI works with GitHub and Sentry and relies on other providers, such as Groq for AI analysis. Your use of GitHub and Sentry is also
          governed by their own terms, and we aren’t responsible for those services.
        </p>

        <h2 id="availability">Availability and changes</h2>
        <p>
          We work to keep TrueAI available and correct, but we can’t promise it will be uninterrupted or error-free. We may change, add or remove
          features, and we’ll give reasonable notice of changes that significantly affect you.
        </p>

        <h2 id="ending">Ending your use</h2>
        <p>
          You can stop using TrueAI and delete your account at any time from Settings. We may suspend or close an account that breaks these terms
          or puts the service or other users at risk.
        </p>

        <h2 id="disclaimers">Disclaimers</h2>
        <p>
          TrueAI is provided “as is” and “as available”, without warranties of any kind, whether express or implied, including any warranty that
          its analyses or proposed changes are accurate, complete or fit for a particular purpose.
        </p>

        <h2 id="liability">Limitation of liability</h2>
        <p>
          To the maximum extent permitted by law, we are not liable for any indirect, incidental, special or consequential losses, or for losses
          caused by changes you choose to merge or deploy, and our liability for anything else is limited to the maximum extent permitted by law.
        </p>

        <h2 id="changes">Changes to these terms</h2>
        <p>
          We may update these terms. When we do, we change the date below, and for significant changes we’ll tell you by email or in the dashboard
          before they take effect. Continuing to use TrueAI afterwards means you accept the updated terms.
        </p>
        <p>Last updated: 15 November 2026</p>
      </Prose>
    </>
  )
}
