import { ButtonLink } from '@/components/ui/button'

export default function IncidentNotFound() {
  return (
    <div className="mx-auto max-w-[980px] px-4 py-16 sm:px-8">
      <h1 className="text-[1.625rem] font-bold tracking-[-0.02em] text-ink">Incident not found</h1>
      <p className="mt-2 max-w-[55ch] text-sm leading-relaxed text-ink-2">
        It may have been deleted, or it belongs to a different account.
      </p>
      <ButtonLink href="/dashboard" variant="secondary" className="mt-6">
        Back to incidents
      </ButtonLink>
    </div>
  )
}
