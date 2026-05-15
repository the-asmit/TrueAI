import type { Metadata } from 'next'
import { Suspense } from 'react'
import { apiClient } from '@/lib/api/client'
import { DashboardClient, type Incident } from './DashboardClient'

export const metadata: Metadata = {
  title: 'Incidents — TrueAI',
  description: 'Monitor and resolve AI-detected incidents automatically',
}

interface IncidentListResponse {
  items: Incident[];
  total: number;
  page: number;
  page_size: number;
}

async function DashboardContent() {
  let incidentsData: IncidentListResponse | null = null;
  let hasError = false;

  try {
    incidentsData = await apiClient.get<IncidentListResponse>('/incidents');
  } catch (error) {
    console.error('Failed to fetch dashboard data:', error);
    hasError = true;
  }

  return (
    <DashboardClient
      initialIncidents={incidentsData?.items || []}
      hasError={hasError}
    />
  )
}

function DashboardSkeleton() {
  return (
    <div className="p-6 space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="h-6 w-32 bg-[#0f1011] rounded-[4px] animate-pulse"></div>
          <div className="h-4 w-64 bg-[#0f1011] rounded-[4px] animate-pulse mt-2"></div>
        </div>
        <div className="h-8 w-36 bg-[#0f1011] rounded-[6px] animate-pulse mt-0.5"></div>
      </div>
      <div className="flex items-center gap-4 border-b border-[#23252a] pb-2 mt-4">
        {[1, 2, 3, 4, 5].map(i => <div key={i} className="h-5 w-16 bg-[#0f1011] rounded-[4px] animate-pulse mb-1"></div>)}
      </div>
      <div className="border border-[#23252a] rounded-[6px] bg-[#0a0b0d] overflow-hidden mt-4">
        <div className="h-10 border-b border-[#23252a] bg-[#0a0a0a]/50 animate-pulse"></div>
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} className="h-12 border-b border-[#23252a] animate-pulse bg-[#0a0b0d]"></div>
        ))}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <DashboardContent />
    </Suspense>
  )
}
