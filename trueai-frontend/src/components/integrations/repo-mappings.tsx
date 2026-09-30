'use client'

import { Trash2 } from 'lucide-react'
import { useState } from 'react'

import { deleteRepositoryMapping, saveRepositoryMapping } from '@/app/actions/integrations'
import { BranchSelect } from '@/components/integrations/branch-select'
import { RepoPicker } from '@/components/integrations/repo-picker'
import { Button } from '@/components/ui/button'
import { describedBy, Field, Input } from '@/components/ui/field'
import type { RepoMapping } from '@/lib/api/types'

/** Route specific Sentry projects to their own repositories (everything else uses the default). */
export function RepoMappings({ mappings, defaultRepo }: { mappings: RepoMapping[]; defaultRepo: string | null }) {
  const projectMappings = mappings.filter((mapping) => mapping.sentry_project)
  const [project, setProject] = useState('')
  const [repo, setRepo] = useState('')
  const [branch, setBranch] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)

  async function add(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    const result = await saveRepositoryMapping(project, repo, branch || undefined)
    setPending(false)
    if (!result.ok) {
      setError(result.error)
      return
    }
    setProject('')
    setRepo('')
    setBranch('')
  }

  async function remove(id: string) {
    setRemoving(id)
    const result = await deleteRepositoryMapping(id)
    setRemoving(null)
    if (!result.ok) setError(result.error)
  }

  return (
    <div className="space-y-5">
      <div className="overflow-hidden rounded-lg border border-rule">
        <table className="w-full border-collapse text-left text-[0.8125rem]">
          <thead className="border-b border-rule bg-sunken/60 text-[0.75rem] text-ink-3">
            <tr>
              <th scope="col" className="px-4 py-2 font-medium">Sentry project</th>
              <th scope="col" className="px-4 py-2 font-medium">Repository</th>
              <th scope="col" className="px-4 py-2">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className="bg-sheet">
            {projectMappings.map((mapping) => (
              <tr key={mapping.id} className="border-b border-rule last:border-b-0">
                <td className="px-4 py-2.5 font-mono text-ink">{mapping.sentry_project}</td>
                <td className="px-4 py-2.5 font-mono text-ink-2">
                  {mapping.repo_full_name}
                  {mapping.branch && <span className="text-ink-3">@{mapping.branch}</span>}
                </td>
                <td className="px-2 py-1.5 text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Remove mapping for ${mapping.sentry_project}`}
                    icon={<Trash2 />}
                    loading={removing === mapping.id}
                    onClick={() => remove(mapping.id)}
                  />
                </td>
              </tr>
            ))}
            <tr>
              <td className="px-4 py-2.5 text-ink-3">Every other project</td>
              <td className="px-4 py-2.5 font-mono text-ink-2" colSpan={2}>
                {defaultRepo ?? <span className="font-sans text-ink-3">No default repository yet</span>}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <form onSubmit={add} className="space-y-4 rounded-lg border border-dashed border-rule-strong p-4">
        <p className="text-[0.8125rem] font-medium text-ink">Add a project route</p>
        <div className="grid gap-4 md:grid-cols-[12rem_1fr_11rem]">
          <Field id="map-project" label="Sentry project slug" error={error}>
            <Input
              id="map-project"
              value={project}
              onChange={(event) => setProject(event.target.value)}
              placeholder="checkout-api"
              spellCheck={false}
              className="font-mono"
              aria-describedby={describedBy('map-project', error)}
              aria-invalid={Boolean(error) || undefined}
            />
          </Field>
          <Field id="map-repo" label="Repository">
            <RepoPicker id="map-repo" value={repo} onChange={(_, typed) => setRepo(typed)} />
          </Field>
          <Field id="map-branch" label="Branch">
            <BranchSelect id="map-branch" repo={repo} value={branch} onChange={setBranch} />
          </Field>
        </div>
        <Button type="submit" size="sm" variant="secondary" loading={pending} disabled={!project.trim() || !repo.trim()}>
          Add route
        </Button>
      </form>
    </div>
  )
}
