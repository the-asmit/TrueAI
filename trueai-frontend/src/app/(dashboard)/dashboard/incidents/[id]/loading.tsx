import { Skeleton } from '@/components/ui/misc'

export default function Loading() {
  return (
    <div className="mx-auto max-w-[980px] px-4 pt-6 sm:px-8 sm:pt-8" aria-busy="true" aria-label="Loading incident">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="mt-6 h-4 w-40" />
      <Skeleton className="mt-3 h-9 w-72" />
      <Skeleton className="mt-3 h-4 w-full max-w-xl" />
      <Skeleton className="mt-6 h-32 w-full rounded-lg" />
      <div className="mt-10 space-y-3">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </div>
    </div>
  )
}
