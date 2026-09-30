import { Fragment, type ReactNode } from 'react'

const CODE_SPAN = /`([^`\n]+)`/g

/**
 * Agent-written text. The agents mark file names, identifiers and commands
 * with `backticks`; those spans are shown as code. Everything else is plain
 * text (React escapes it), so no model output is ever rendered as HTML.
 */
export function Prose({ text }: { text: string }) {
  const parts: ReactNode[] = []
  let last = 0
  for (const match of text.matchAll(CODE_SPAN)) {
    const start = match.index ?? 0
    if (start > last) parts.push(text.slice(last, start))
    parts.push(
      <code key={start} className="rounded-sm bg-sunken px-1 py-px font-mono text-[0.875em] text-ink">
        {match[1]}
      </code>,
    )
    last = start + match[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <Fragment>{parts}</Fragment>
}
