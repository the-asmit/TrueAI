import { Skeleton } from '@/components/ui/misc'

export default function Loading() {
  return (
    <div className="mx-auto max-w-[1180px] px-4 pt-6 sm:px-8 sm:pt-10" aria-busy="true" aria-label="Loading incidents">
      <Skeleton className="h-8 w-40" />
      <Skeleton className="mt-2 h-4 w-72" />
      <div className="mt-8 flex gap-2 border-b border-rule pb-2">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-5 w-20" />
        ))}
      </div>
      <div className="mt-4 overflow-hidden rounded-lg border border-rule bg-sheet">
        {Array.from({ length: 7 }, (_, index) => (
          <div key={index} className="flex items-center justify-between gap-6 border-b border-rule px-4 py-4 last:border-b-0">
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-3/4 max-w-lg" />
            </div>
            <Skeleton className="hidden h-4 w-28 md:block" />
          </div>
        ))}
      </div>
    </div>
  )
}
