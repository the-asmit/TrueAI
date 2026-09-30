import { Wordmark } from '@/components/brand'
import { ButtonLink } from '@/components/ui/button'

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col bg-paper px-6 py-6 sm:px-10">
      <Wordmark />
      <main id="main" className="flex flex-1 items-center">
        <div className="max-w-md">
          <h1 className="text-[1.75rem] font-bold tracking-[-0.02em] text-ink">This page doesn’t exist</h1>
          <p className="mt-2 text-sm leading-relaxed text-ink-2">The link may be old, or the page may have moved.</p>
          <div className="mt-6 flex gap-2">
            <ButtonLink href="/dashboard">Go to incidents</ButtonLink>
            <ButtonLink href="/" variant="secondary">
              Home
            </ButtonLink>
          </div>
        </div>
      </main>
    </div>
  )
}
