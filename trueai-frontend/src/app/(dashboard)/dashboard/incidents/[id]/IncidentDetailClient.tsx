"use client"

import { useRouter } from 'next/navigation'
import { ArrowLeft, AlertCircle, FileCode, GitPullRequest, ExternalLink, GitBranch, Terminal } from 'lucide-react'
import Link from 'next/link'

export interface Incident {
  id: string;
  user_id: string;
  sentry_event_id: string;
  error_type: string;
  error_message: string;
  environment: string;
  platform?: string;
  status: 'pending' | 'processing' | 'resolved' | 'flagged' | 'failed';
  issue_classification?: string;
  pipeline_error?: string;
  created_at: string;
}

export interface Fix {
  id: string;
  incident_id: string;
  root_cause: string;
  explanation: string;
  fix_diff: string;
  confidence_score: number;
  created_at: string;
}

export interface PR {
  id: string;
  incident_id: string;
  pr_url: string;
  pr_number: number;
  branch_name: string;
  status: string;
  created_at: string;
}

interface Props {
  incident: Incident;
  fix: Fix | null;
  pr: PR | null;
}

export function IncidentDetailClient({ incident, fix, pr }: Props) {
  const router = useRouter()

  // Format time (absolute)
  const formatDate = (dateString: string) => {
    try {
      const parsedString = dateString.endsWith('Z') || dateString.includes('+')
        ? dateString
        : `${dateString}Z`
      const date = new Date(parsedString)
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      })
    } catch {
      return dateString
    }
  }

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'pending':    return 'bg-[#8a8f98]/10 text-[#8a8f98] border-[#8a8f98]/20'
      case 'processing': return 'bg-[#3b82f6]/10 text-[#3b82f6] border-[#3b82f6]/20'
      case 'resolved':   return 'bg-[#22c55e]/10 text-[#22c55e] border-[#22c55e]/20'
      case 'failed':     return 'bg-[#ef4444]/10 text-[#ef4444] border-[#ef4444]/20'
      case 'flagged':    return 'bg-[#f59e0b]/10 text-[#f59e0b] border-[#f59e0b]/20'
      default:           return 'bg-[#8a8f98]/10 text-[#8a8f98] border-[#8a8f98]/20'
    }
  }

  const getStatusDotColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'pending':    return '#8a8f98'
      case 'processing': return '#3b82f6'
      case 'resolved':   return '#22c55e'
      case 'failed':     return '#ef4444'
      case 'flagged':    return '#f59e0b'
      default:           return '#8a8f98'
    }
  }

  const getConfidenceColor = (score: number) => {
    if (score >= 0.75) return { bar: '#22c55e', text: '#22c55e' }
    if (score >= 0.5)  return { bar: '#f59e0b', text: '#f59e0b' }
    return { bar: '#ef4444', text: '#ef4444' }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">

      {/* Back navigation */}
      <button
        onClick={() => router.push('/dashboard')}
        className="flex items-center gap-1.5 text-[13px] text-[#62666d] hover:text-[#f7f8f8] transition-colors group"
      >
        <ArrowLeft size={14} className="group-hover:-translate-x-0.5 transition-transform" />
        Back to Dashboard
      </button>

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 flex-wrap mb-2">
            <h1 className="text-[22px] font-semibold text-[#f7f8f8] tracking-[-0.4px] font-mono">
              {incident.error_type}
            </h1>
            <span className={`inline-flex px-2.5 py-1 rounded-full border text-[11px] font-medium capitalize ${getStatusColor(incident.status)}`}>
              {incident.status?.replace('_', ' ') || 'unknown'}
            </span>
          </div>
          <p className="text-[14px] text-[#8a8f98]">
            {incident.error_message}
          </p>
        </div>
      </div>

      {/* Two column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* ── Left Column ── */}
        <div className="lg:col-span-2 space-y-5">

          {/* Card 1: Error Details */}
          <div className="bg-[#0f1011] border border-[#23252a] rounded-xl overflow-hidden">
            <div className="px-5 py-3.5 border-b border-[#23252a] flex items-center gap-2">
              <AlertCircle size={16} className="text-[#62666d]" />
              <h2 className="text-[13px] font-medium text-[#f7f8f8]">Error Details</h2>
            </div>
            <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-5">
              <div>
                <p className="text-[11px] font-medium text-[#62666d] uppercase tracking-wider mb-1">Environment</p>
                <p className="text-[13px] text-[#f7f8f8]">{incident.environment || 'N/A'}</p>
              </div>
              <div>
                <p className="text-[11px] font-medium text-[#62666d] uppercase tracking-wider mb-1">Platform</p>
                <p className="text-[13px] text-[#f7f8f8] capitalize">{incident.platform || 'N/A'}</p>
              </div>
              <div>
                <p className="text-[11px] font-medium text-[#62666d] uppercase tracking-wider mb-1">Classification</p>
                {incident.issue_classification ? (
                  <span className="bg-[#0f1011] border border-[#23252a] px-2 py-0.5 rounded text-[12px] text-[#8a8f98] inline-block">
                    {incident.issue_classification.replace('_', ' ')}
                  </span>
                ) : (
                  <p className="text-[13px] text-[#62666d]">Unclassified</p>
                )}
              </div>
              <div>
                <p className="text-[11px] font-medium text-[#62666d] uppercase tracking-wider mb-1">Captured At</p>
                <p className="text-[13px] text-[#f7f8f8]">{formatDate(incident.created_at)}</p>
              </div>
              <div className="col-span-2">
                <p className="text-[11px] font-medium text-[#62666d] uppercase tracking-wider mb-1">Sentry Event ID</p>
                <span className="bg-[#070708] border border-[#23252a] px-3 py-2 rounded-lg text-[13px] text-[#8a8f98] font-mono inline-block">
                  {incident.sentry_event_id}
                </span>
              </div>
            </div>
          </div>

          {/* Card 2: Root Cause Analysis */}
          <div className="bg-[#0f1011] border border-[#23252a] rounded-xl overflow-hidden">
            <div className="px-5 py-3.5 border-b border-[#23252a] flex items-center gap-2">
              <Terminal size={16} className="text-[#62666d]" />
              <h2 className="text-[13px] font-medium text-[#f7f8f8]">Root Cause Analysis</h2>
            </div>
            {!fix ? (
              <div className="p-5 flex flex-col items-center justify-center py-14 text-center">
                <div className="w-8 h-8 rounded-full border-2 border-t-[#ededed] border-r-transparent border-b-transparent border-l-transparent animate-spin mb-4" />
                <p className="text-[14px] text-[#8a8f98]">Analysis pending...</p>
                <p className="text-[12px] text-[#62666d] mt-1">This may take a few moments</p>
              </div>
            ) : (
              <div className="p-5 space-y-5">
                <div>
                  <p className="text-[11px] font-medium text-[#62666d] uppercase tracking-wider mb-2">Root Cause</p>
                  <p className="text-[14px] text-[#f7f8f8] leading-relaxed">{fix.root_cause}</p>
                </div>
                <div className="pt-4 border-t border-[#23252a]">
                  <p className="text-[11px] font-medium text-[#62666d] uppercase tracking-wider mb-2">Explanation</p>
                  <p className="text-[14px] text-[#8a8f98] leading-relaxed">{fix.explanation}</p>
                </div>
              </div>
            )}
          </div>

          {/* Card 3: Proposed Fix Diff */}
          <div className="bg-[#0f1011] border border-[#23252a] rounded-xl overflow-hidden">
            <div className="px-5 py-3.5 border-b border-[#23252a] flex items-center gap-2">
              <FileCode size={16} className="text-[#62666d]" />
              <h2 className="text-[13px] font-medium text-[#f7f8f8]">Proposed Fix Diff</h2>
            </div>
            {!fix ? (
              <div className="p-5 flex items-center justify-center py-14">
                <p className="text-[13px] text-[#62666d]">Diff will appear here once the fix is generated.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <pre className="p-5 text-[12px] font-mono bg-[#070708] m-0 leading-relaxed">
                  <code>
                    {fix.fix_diff.split('\n').map((line, i) => {
                      let className = 'text-[#8a8f98]'
                      if (line.startsWith('+')) className = 'text-[#22c55e] bg-[#22c55e]/5 inline-block w-full'
                      else if (line.startsWith('-')) className = 'text-[#ef4444] bg-[#ef4444]/5 inline-block w-full'
                      else if (line.startsWith('@@')) className = 'text-[#3b82f6]'
                      else if (line.startsWith('diff') || line.startsWith('index') || line.startsWith('---') || line.startsWith('+++')) className = 'text-[#62666d]'

                      return (
                        <span key={i} className={className}>
                          {line}{'\n'}
                        </span>
                      )
                    })}
                  </code>
                </pre>
              </div>
            )}
          </div>

        </div>

        {/* ── Right Column ── */}
        <div className="space-y-5">

          {/* Pipeline Status */}
          <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-5">
            <p className="text-[11px] font-medium text-[#62666d] uppercase tracking-wider mb-4">Pipeline Status</p>
            <div className="flex items-center gap-2.5">
              <div
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: getStatusDotColor(incident.status) }}
              />
              <span className="text-[14px] font-medium text-[#f7f8f8] capitalize">
                {incident.status.replace('_', ' ')}
              </span>
            </div>
            {incident.status === 'failed' && incident.pipeline_error && (
              <div className="mt-4 p-3 bg-[#ef4444]/5 border border-[#ef4444]/20 rounded-lg">
                <p className="text-[12px] text-[#ef4444] break-words font-mono leading-relaxed">
                  {incident.pipeline_error}
                </p>
              </div>
            )}
          </div>

          {/* Pull Request */}
          <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-5">
            <p className="text-[11px] font-medium text-[#62666d] uppercase tracking-wider mb-4 flex items-center gap-1.5">
              <GitPullRequest size={12} />
              Pull Request
            </p>
            {!pr ? (
              <p className="text-[13px] text-[#62666d]">No PR created yet</p>
            ) : (
              <div className="space-y-3">
                <Link
                  href={pr.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-[13px] font-medium text-[#ededed] hover:text-[#ffffff] transition-colors"
                >
                  View PR #{pr.pr_number}
                  <ExternalLink size={12} />
                </Link>
                <div className="flex items-center gap-2 bg-[#070708] border border-[#23252a] px-3 py-2 rounded-lg">
                  <GitBranch size={13} className="text-[#62666d] shrink-0" />
                  <span className="text-[12px] font-mono text-[#8a8f98] truncate">{pr.branch_name}</span>
                </div>
              </div>
            )}
          </div>

          {/* Fix Confidence (only when fix exists) */}
          {fix && (() => {
            const confidence = getConfidenceColor(fix.confidence_score)
            return (
              <div className="bg-[#0f1011] border border-[#23252a] rounded-xl p-5">
                <p className="text-[11px] font-medium text-[#62666d] uppercase tracking-wider mb-4">Fix Confidence</p>
                <div className="flex items-end justify-between mb-3">
                  <span
                    className="text-[28px] font-semibold leading-none"
                    style={{ color: confidence.text }}
                  >
                    {Math.round(fix.confidence_score * 100)}%
                  </span>
                </div>
                <div className="h-1.5 w-full bg-[#23252a] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.max(5, fix.confidence_score * 100)}%`,
                      backgroundColor: confidence.bar
                    }}
                  />
                </div>
              </div>
            )
          })()}

        </div>
      </div>
    </div>
  )
}
