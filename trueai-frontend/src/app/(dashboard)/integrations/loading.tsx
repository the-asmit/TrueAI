import { Skeleton } from '@/components/ui/misc'

export default function Loading() {
  return (
    <div className="mx-auto max-w-[860px] px-4 pt-6 sm:px-8 sm:pt-10" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-44" />
      <Skeleton className="mt-2 h-4 w-80" />
      <div className="mt-10 space-y-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-2/3" />
      </div>
      <div className="mt-12 space-y-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-24 w-full rounded-lg" />
      </div>
    </div>
  )
}
