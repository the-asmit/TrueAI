"use client"

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { RefreshCw } from 'lucide-react'

export interface Incident {
  id: string;
  user_id: string;
  sentry_event_id: string;
  error_type: string;
  error_message: string;
  stack_trace: Record<string, unknown> | unknown[] | null;
  environment: string;
  level: string | null;
  platform: string | null;
  issue_classification: string | null;
  pipeline_error: string | null;
  status: 'pending' | 'processing' | 'resolved' | 'flagged' | 'failed';
  created_at: string;
  updated_at: string | null;
}

interface Props {
  initialIncidents: Incident[];
  hasError: boolean;
}

// ─── helpers ──────────────────────────────────────────────────────────────────

const formatTime = (dateString: string) => {
  try {
    const parsed = dateString.endsWith('Z') || dateString.includes('+')
      ? dateString
      : `${dateString}Z`
    const diff = Date.now() - new Date(parsed).getTime()
    if (diff < 0) return 'just now'
    const m = Math.floor(diff / 60000)
    if (m < 1) return 'just now'
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    return `${Math.floor(h / 24)}d ago`
  } catch { return 'unknown' }
}

const STATUS_STYLES: Record<string, string> = {
  pending:    'bg-white/5 text-white/40 border border-white/10',
  processing: 'bg-blue-500/10 text-blue-400 border border-blue-500/20',
  resolved:   'bg-green-500/10 text-green-400 border border-green-500/20',
  failed:     'bg-red-500/10 text-red-400 border border-red-500/20',
  flagged:    'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20',
}

const COUNT_STYLES: Record<string, string> = {
  failed:     'bg-red-500/10 text-red-400 border border-red-500/20',
  processing: 'bg-blue-500/10 text-blue-400 border border-blue-500/20',
}

// ─── component ────────────────────────────────────────────────────────────────

export function DashboardClient({ initialIncidents, hasError }: Props) {
  const router = useRouter()
  const [activeTab, setActiveTab] = useState('All')

  // Polling every 30 seconds — unchanged
  useEffect(() => {
    const interval = setInterval(() => { router.refresh() }, 30000)
    return () => clearInterval(interval)
  }, [router])

  const tabs = ['All', 'Processing', 'Resolved', 'Failed', 'Flagged']

  const filteredIncidents = initialIncidents.filter(incident => {
    if (activeTab === 'All') return true
    return incident.status?.toLowerCase() === activeTab.toLowerCase()
  })

  // Inline status counts for the header pills
  const counts = (['failed', 'processing'] as const).reduce<Record<string, number>>((acc, s) => {
    acc[s] = initialIncidents.filter(i => i.status === s).length
    return acc
  }, {})

  return (
    <div className="flex flex-col h-full">

      {/* Page header */}
      <div className="pt-8 pb-6 px-6 border-b border-white/5">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-semibold text-white">Incidents</h1>
          {Object.entries(counts).map(([status, count]) => count > 0 && (
            <span key={status} className={`text-xs font-mono px-2 py-0.5 rounded-sm capitalize ${COUNT_STYLES[status]}`}>
              {count} {status}
            </span>
          ))}
        </div>
        <p className="text-sm text-white/40 mt-1">
          Errors captured from Sentry, analyzed and auto-fixed by AI
        </p>
      </div>

      {/* Error banner */}
      {hasError && (
        <div className="mx-6 mt-6 px-4 py-3 bg-red-500/5 border border-red-500/20 rounded-md flex items-center justify-between">
          <p className="text-sm text-red-400">Failed to load incidents.</p>
          <button onClick={() => router.refresh()} className="flex items-center gap-1.5 text-xs text-red-400 hover:opacity-80 transition-opacity">
            <RefreshCw size={12} /> Retry
          </button>
        </div>
      )}

      {/* Filter tabs */}
      {!hasError && (
        <div className="flex gap-0 border-b border-white/8 px-6">
          {tabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm transition-colors cursor-pointer -mb-px ${
                activeTab === tab
                  ? 'text-white border-b-2 border-white'
                  : 'text-white/40 hover:text-white/70'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      )}

      {/* Incidents list */}
      {!hasError && (
        initialIncidents.length === 0 ? (
          <div className="flex-1 flex items-center justify-center py-20">
            <p className="text-sm font-mono text-white/20">No incidents found.</p>
          </div>
        ) : filteredIncidents.length === 0 ? (
          <div className="flex-1 flex items-center justify-center py-20">
            <p className="text-sm font-mono text-white/20">No {activeTab.toLowerCase()} incidents.</p>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
            {filteredIncidents.map(incident => (
              <div
                key={incident.id}
                onClick={() => router.push(`/dashboard/incidents/${incident.id}`)}
                className="group bg-[#111111] rounded-lg border border-white/8 p-4 flex items-center justify-between cursor-pointer transition-all duration-200 hover:bg-[#141414] hover:border-white/12"
                style={{
                  boxShadow: '0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.04)',
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLDivElement).style.boxShadow =
                    '0 4px 12px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.06)'
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLDivElement).style.boxShadow =
                    '0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.04)'
                }}
              >
                {/* Left */}
                <div className="min-w-0 flex-1 mr-8">
                  <p className="font-mono text-sm text-white font-medium truncate">
                    {incident.error_type || 'Unknown Error'}
                  </p>
                  {incident.error_message && (
                    <p className="text-sm text-white/40 mt-0.5 truncate">
                      {incident.error_message.length > 90
                        ? incident.error_message.slice(0, 90) + '…'
                        : incident.error_message}
                    </p>
                  )}
                  {incident.sentry_event_id && (
                    <p className="text-xs font-mono text-white/20 mt-1">
                      {incident.sentry_event_id.slice(0, 16)}…
                    </p>
                  )}
                </div>

                {/* Right */}
                <div className="flex items-center gap-4 shrink-0">
                  <span className="text-xs font-mono text-white/30">
                    {formatTime(incident.created_at)}
                  </span>
                  <span className={`text-xs font-mono px-2 py-0.5 rounded-sm capitalize ${STATUS_STYLES[incident.status] ?? STATUS_STYLES.pending}`}>
                    {incident.status?.replace('_', ' ')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}
