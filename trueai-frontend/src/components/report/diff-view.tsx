import { CopyButton } from '@/components/ui/copy-button'
import { cn } from '@/lib/utils'

interface DiffLine {
  kind: 'add' | 'del' | 'ctx' | 'hunk' | 'note'
  text: string
  oldNo: number | null
  newNo: number | null
}

interface DiffFile {
  path: string
  added: number
  removed: number
  lines: DiffLine[]
}

/** Parse a unified diff (as produced by TrueAI's patch engine) into files and numbered lines. */
export function parseDiff(diff: string): DiffFile[] {
  const files: DiffFile[] = []
  let current: DiffFile | null = null
  let oldNo = 0
  let newNo = 0

  for (const raw of diff.replace(/\r\n/g, '\n').split('\n')) {
    if (raw.startsWith('--- ')) continue
    if (raw.startsWith('+++ ')) {
      current = { path: raw.slice(4).replace(/^b\//, '').trim(), added: 0, removed: 0, lines: [] }
      files.push(current)
      continue
    }
    if (!current) continue
    const hunk = raw.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/)
    if (hunk) {
      oldNo = Number(hunk[1])
      newNo = Number(hunk[2])
      current.lines.push({ kind: 'hunk', text: raw, oldNo: null, newNo: null })
    } else if (raw.startsWith('+')) {
      current.added += 1
      current.lines.push({ kind: 'add', text: raw.slice(1), oldNo: null, newNo: newNo++ })
    } else if (raw.startsWith('-')) {
      current.removed += 1
      current.lines.push({ kind: 'del', text: raw.slice(1), oldNo: oldNo++, newNo: null })
    } else if (raw.startsWith('\\')) {
      current.lines.push({ kind: 'note', text: raw, oldNo: null, newNo: null })
    } else if (raw.length > 0 || current.lines.length > 0) {
      current.lines.push({ kind: 'ctx', text: raw.startsWith(' ') ? raw.slice(1) : raw, oldNo: oldNo++, newNo: newNo++ })
    }
  }
  // Drop a trailing empty context line produced by the final newline.
  for (const file of files) {
    const last = file.lines[file.lines.length - 1]
    if (last && last.kind === 'ctx' && last.text === '') file.lines.pop()
  }
  return files
}

const ROW: Record<DiffLine['kind'], string> = {
  add: 'bg-diff-add text-diff-add-ink',
  del: 'bg-diff-del text-diff-del-ink',
  ctx: 'text-ink-2',
  hunk: 'bg-review-tint/60 text-review',
  note: 'text-ink-3 italic',
}

export function DiffView({ diff, caption }: { diff: string; caption?: string }) {
  const files = parseDiff(diff)
  if (files.length === 0) {
    return <pre className="overflow-x-auto rounded-md border border-rule bg-sunken p-4 text-[0.8125rem] text-ink-2">{diff}</pre>
  }
  return (
    <figure className="space-y-3">
      {files.map((file) => (
        <div key={file.path} className="overflow-hidden rounded-lg border border-rule bg-sheet">
          <div className="flex items-center justify-between gap-3 border-b border-rule bg-sunken/70 px-3 py-2">
            <span className="min-w-0 truncate font-mono text-[0.8125rem] text-ink">{file.path}</span>
            <span className="tabular shrink-0 font-mono text-[0.75rem]">
              <span className="text-fixed">+{file.added}</span> <span className="text-failure">−{file.removed}</span>
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse font-mono text-[0.8125rem] leading-[1.6]">
              <tbody>
                {file.lines.map((line, index) => (
                  <tr key={index} className={ROW[line.kind]}>
                    <td className="w-[1%] select-none whitespace-nowrap px-2 text-right text-[0.75rem] text-ink-3/80">{line.oldNo ?? ''}</td>
                    <td className="w-[1%] select-none whitespace-nowrap px-2 text-right text-[0.75rem] text-ink-3/80">{line.newNo ?? ''}</td>
                    <td className="w-[1%] select-none px-1 text-center" aria-hidden>
                      {line.kind === 'add' ? '+' : line.kind === 'del' ? '−' : ''}
                    </td>
                    <td className={cn('whitespace-pre pr-4', line.kind === 'hunk' && 'py-0.5 text-[0.75rem]')}>
                      {line.kind === 'add' && <span className="sr-only">Added: </span>}
                      {line.kind === 'del' && <span className="sr-only">Removed: </span>}
                      {line.text || ' '}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      <figcaption className="flex flex-wrap items-center justify-between gap-3 text-[0.8125rem] text-ink-3">
        <span>{caption}</span>
        <CopyButton value={diff} label="Copy diff" />
      </figcaption>
    </figure>
  )
}
