import type { Metadata } from 'next'
import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import { apiClient } from '@/lib/api/client'
import { IncidentDetailClient, type Incident, type Fix, type PR } from './IncidentDetailClient'

export const metadata: Metadata = {
  title: 'Incident Detail — TrueAI',
}

interface PageProps {
  params: Promise<{ id: string }>
}

async function fetchIncidentData(id: string) {
  try {
    const incident = await apiClient.get<Incident>(`/incidents/${id}`)
    let fix: Fix | null = null
    let pr: PR | null = null

    try {
      fix = await apiClient.get<Fix>(`/incidents/${id}/fix`)
    } catch (e: any) {
      if (e?.status === 404 || e?.statusCode === 404 || e?.code === 404) {
        fix = null
      } else {
        throw e
      }
    }

    try {
      pr = await apiClient.get<PR>(`/incidents/${id}/pr`)
    } catch (e: any) {
      if (e?.status === 404 || e?.statusCode === 404 || e?.code === 404) {
        pr = null
      } else {
        throw e
      }
    }

    return { incident, fix, pr }
  } catch (error: any) {
    if (error?.status === 404) {
      return null
    }
    console.error('Error fetching incident:', error)
    return null
  }
}

async function IncidentDetailContent({ id }: { id: string }) {
  const data = await fetchIncidentData(id)
  
  if (!data) {
    redirect('/dashboard')
  }

  return <IncidentDetailClient incident={data.incident} fix={data.fix} pr={data.pr} />
}

function IncidentDetailSkeleton() {
  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Back button skeleton */}
      <div className="w-32 h-4 bg-[#0f1011] rounded animate-pulse"></div>

      {/* Header skeleton */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mt-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-64 h-8 bg-[#0f1011] rounded-lg animate-pulse"></div>
            <div className="w-20 h-6 bg-[#0f1011] rounded-lg animate-pulse"></div>
          </div>
          <div className="w-96 max-w-full h-4 bg-[#0f1011] rounded animate-pulse"></div>
        </div>
      </div>

      {/* Two column layout skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        {/* Left Column */}
        <div className="lg:col-span-2 space-y-5">
          <div className="h-[200px] bg-[#0a0b0d] border border-[#23252a] rounded-xl overflow-hidden">
            <div className="h-11 border-b border-[#23252a] bg-[#070708] animate-pulse"></div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <div className="h-10 bg-[#0f1011] rounded animate-pulse"></div>
              <div className="h-10 bg-[#0f1011] rounded animate-pulse"></div>
              <div className="h-10 bg-[#0f1011] rounded animate-pulse"></div>
              <div className="h-10 bg-[#0f1011] rounded animate-pulse"></div>
            </div>
          </div>

          <div className="h-[150px] bg-[#0a0b0d] border border-[#23252a] rounded-xl overflow-hidden">
            <div className="h-11 border-b border-[#23252a] bg-[#070708] animate-pulse"></div>
            <div className="p-5 space-y-3">
              <div className="h-4 w-full bg-[#0f1011] rounded animate-pulse"></div>
              <div className="h-4 w-3/4 bg-[#0f1011] rounded animate-pulse"></div>
            </div>
          </div>

          <div className="h-[250px] bg-[#0a0b0d] border border-[#23252a] rounded-xl overflow-hidden">
            <div className="h-11 border-b border-[#23252a] bg-[#070708] animate-pulse"></div>
            <div className="p-5">
              <div className="h-32 bg-[#0f1011] rounded animate-pulse"></div>
            </div>
          </div>
        </div>

        {/* Right Column */}
        <div className="space-y-5">
          <div className="h-[120px] bg-[#0a0b0d] border border-[#23252a] rounded-xl overflow-hidden p-5">
            <div className="h-4 w-24 bg-[#0f1011] rounded animate-pulse mb-4"></div>
            <div className="h-6 w-32 bg-[#0f1011] rounded animate-pulse"></div>
          </div>
          <div className="h-[120px] bg-[#0a0b0d] border border-[#23252a] rounded-xl overflow-hidden p-5">
            <div className="h-4 w-24 bg-[#0f1011] rounded animate-pulse mb-4"></div>
            <div className="h-6 w-48 bg-[#0f1011] rounded animate-pulse mb-2"></div>
            <div className="h-8 w-full bg-[#0f1011] rounded animate-pulse"></div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default async function IncidentDetailPage({ params }: PageProps) {
  const { id } = await params

  return (
    <Suspense fallback={<IncidentDetailSkeleton />}>
      <IncidentDetailContent id={id} />
    </Suspense>
  )
}
