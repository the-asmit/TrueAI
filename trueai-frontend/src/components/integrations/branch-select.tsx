'use client'

import { useEffect, useState } from 'react'

import { listBranches } from '@/app/actions/integrations'
import { Select } from '@/components/ui/field'

const REPO_PATTERN = /^[\w.-]+\/[\w.-]+$/

interface LoadedBranches {
  repo: string
  branches: string[]
  error: string | null
}

/** Branches of ``repo``; selects the repository's default branch unless ``value`` is set. */
export function BranchSelect({ id, repo, value, onChange }: { id: string; repo: string; value: string; onChange: (branch: string) => void }) {
  const [loaded, setLoaded] = useState<LoadedBranches | null>(null)
  const validRepo = REPO_PATTERN.test(repo)

  useEffect(() => {
    if (!validRepo) return
    let cancelled = false
    listBranches(repo).then((result) => {
      if (cancelled) return
      if (result.ok) {
        const { branches, default_branch } = result.data
        const names = branches.includes(default_branch) ? branches : [default_branch, ...branches]
        setLoaded({ repo, branches: names, error: null })
        if (!value || !names.includes(value)) onChange(default_branch)
      } else {
        setLoaded({ repo, branches: [], error: result.error })
      }
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when the repository changes
  }, [repo, validRepo])

  // Results for a different repository (or none yet) mean this one is still loading.
  const current = validRepo && loaded?.repo === repo ? loaded : null
  const loading = validRepo && !current
  const branches = current?.branches ?? []

  if (current?.error) return <p className="text-[0.8125rem] text-failure">{current.error}</p>

  return (
    <Select id={id} value={value} disabled={loading || branches.length === 0} onChange={(event) => onChange(event.target.value)} className="font-mono">
      {loading && <option>Loading branches…</option>}
      {!loading && branches.length === 0 && <option value="">Choose a repository first</option>}
      {branches.map((branch) => (
        <option key={branch} value={branch}>
          {branch}
        </option>
      ))}
    </Select>
  )
}
