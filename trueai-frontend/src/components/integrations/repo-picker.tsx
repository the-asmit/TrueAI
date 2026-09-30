'use client'

import { Check, LoaderCircle, Lock } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'

import { searchRepositories } from '@/app/actions/integrations'
import { Input } from '@/components/ui/field'
import type { GitHubRepository } from '@/lib/api/types'
import { cn } from '@/lib/utils'

interface RepoPickerProps {
  id: string
  value: string
  onChange: (repo: GitHubRepository | null, fullName: string) => void
  invalid?: boolean
  describedBy?: string
}

/**
 * Combobox over the repositories the connected GitHub account can access.
 * Typing filters server-side; ↑/↓ move, Enter selects, Escape closes.
 * A full "owner/repo" can also be typed directly.
 */
interface SearchResult {
  query: string
  repos: GitHubRepository[]
  error: string | null
}

export function RepoPicker({ id, value, onChange, invalid, describedBy }: RepoPickerProps) {
  const listId = useId()
  const [query, setQuery] = useState(value)
  const [syncedValue, setSyncedValue] = useState(value)
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState<SearchResult | null>(null)
  const [active, setActive] = useState(0)
  const requestRef = useRef(0)

  // The parent can change the value (a saved mapping, a reset form); follow it.
  if (value !== syncedValue) {
    setSyncedValue(value)
    if (value !== query.trim()) setQuery(value)
  }

  useEffect(() => {
    if (!open) return
    const request = ++requestRef.current
    const timer = setTimeout(async () => {
      const result = await searchRepositories(query.includes('/') ? query.split('/')[1] ?? query : query)
      if (request !== requestRef.current) return
      setSearch(result.ok ? { query, repos: result.data, error: null } : { query, repos: [], error: result.error })
      setActive(0)
    }, 250)
    return () => clearTimeout(timer)
  }, [query, open])

  const loading = open && search?.query !== query
  const results = search?.repos ?? []
  const error = search?.error ?? null

  function choose(repo: GitHubRepository) {
    setQuery(repo.full_name)
    setOpen(false)
    onChange(repo, repo.full_name)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setOpen(true)
      setActive((index) => Math.min(index + 1, Math.max(results.length - 1, 0)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter' && open && results[active]) {
      event.preventDefault()
      choose(results[active])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="relative">
      <Input
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && results[active] ? `${listId}-${active}` : undefined}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        autoComplete="off"
        spellCheck={false}
        placeholder="Search your repositories, or type owner/repo"
        className="font-mono"
        value={query}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onChange={(event) => {
          setQuery(event.target.value)
          setOpen(true)
          onChange(null, event.target.value.trim())
        }}
        onKeyDown={onKeyDown}
      />
      {loading && open && <LoaderCircle className="absolute right-3 top-2.5 size-4 animate-spin text-ink-3" aria-hidden />}
      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-md border border-rule bg-sheet py-1 shadow-[var(--shadow-pop)]"
        >
          {error && <li className="px-3 py-2 text-[0.8125rem] text-failure">{error}</li>}
          {!error && !loading && results.length === 0 && (
            <li className="px-3 py-2 text-[0.8125rem] text-ink-3">No repositories match. You can still type owner/repo.</li>
          )}
          {results.map((repo, index) => (
            <li
              key={repo.full_name}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              onMouseDown={(event) => {
                event.preventDefault()
                choose(repo)
              }}
              onMouseEnter={() => setActive(index)}
              className={cn('flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-[0.8125rem]', index === active && 'bg-sunken')}
            >
              <span className="flex min-w-0 items-center gap-2 font-mono text-ink">
                {repo.private && <Lock className="size-3.5 shrink-0 text-ink-3" aria-label="Private" />}
                <span className="truncate">{repo.full_name}</span>
              </span>
              <span className="flex shrink-0 items-center gap-2 text-[0.75rem] text-ink-3">
                {repo.can_push ? 'Can push' : <span className="text-human">Read only</span>}
                {repo.full_name === value && <Check className="size-3.5 text-fixed" aria-hidden />}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
