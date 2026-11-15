import { ArrowRight } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { MergePanel, PrivacyPanel, RecordPanel } from '@/components/landing/exhibits'

/*
 * Building blocks shared by the marketing pages (home, How it works, Security, Docs),
 * so every page uses the same section rhythm, headings and type.
 */

// Buttons on the stage (the header and heroes, which follow the theme) and on the closing band (always dark).
export const STAGE_BUTTON =
  'inline-flex h-11 items-center gap-2 rounded-md bg-stage-ink px-5 text-[0.9375rem] font-medium text-stage transition-opacity hover:opacity-90 focus-visible:outline-stage-ink [&_svg]:size-4'
export const STAGE_BUTTON_SMALL =
  'inline-flex h-8 items-center rounded-md bg-stage-ink px-3 text-[0.8125rem] font-medium text-stage transition-opacity hover:opacity-90 focus-visible:outline-stage-ink'
export const NIGHT_BUTTON =
  'inline-flex h-11 items-center gap-2 rounded-md bg-night-ink px-5 text-[0.9375rem] font-medium text-night transition-opacity hover:opacity-90 focus-visible:outline-night-ink [&_svg]:size-4'

// Anchored sections clear the sticky header (two rows on phones, one from md up).
const SCROLL_OFFSET = 'scroll-mt-28 md:scroll-mt-16'

/** A page section: a rule, an H2 and its content, optionally ending with a link to the full page. */
export function Section({
  id,
  title,
  lede,
  more,
  children,
}: {
  id: string
  title: string
  lede?: string
  more?: { href: string; label: string }
  children: ReactNode
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={`${SCROLL_OFFSET} border-t border-rule`}>
      <div className="mx-auto max-w-[1240px] px-4 py-20 sm:px-8 lg:py-28">
        <h2 id={`${id}-title`} className="max-w-[22ch] text-balance text-[2rem] font-bold leading-[1.1] tracking-[-0.03em] text-ink sm:text-[2.5rem]">
          {title}
        </h2>
        {lede && <p className="mt-5 max-w-[60ch] text-pretty text-[1.0625rem] leading-[1.65] text-ink-2">{lede}</p>}
        <div className="mt-10 lg:mt-12">{children}</div>
        {more && <LearnMore {...more} />}
      </div>
    </section>
  )
}

/** "Learn more →" to a page that covers a homepage section in full; `label` completes the link text for screen readers. */
export function LearnMore({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="mt-10 inline-flex items-center gap-1.5 text-[0.9375rem] font-medium text-ink underline-offset-4 hover:underline [&_svg]:size-4"
    >
      Learn more<span className="sr-only"> {label}</span> <ArrowRight aria-hidden />
    </Link>
  )
}

/** The top of a page below the homepage: breadcrumb, the page's one H1 and a short lede, on the stage. */
export function PageHero({ name, title, lede, children }: { name: string; title: string; lede: string; children?: ReactNode }) {
  return (
    <section className="overflow-hidden border-b border-rule bg-stage text-stage-ink">
      <div className="mx-auto max-w-[1240px] px-4 pb-16 pt-12 sm:px-8 lg:pb-20 lg:pt-16">
        <nav aria-label="Breadcrumb">
          <ol className="flex items-center gap-2 text-[0.8125rem] text-stage-ink-2">
            <li>
              <Link href="/" className="hover:text-stage-ink">Home</Link>
            </li>
            <li aria-hidden>/</li>
            <li aria-current="page" className="text-stage-ink">{name}</li>
          </ol>
        </nav>
        <h1 className="mt-6 max-w-[20ch] text-balance text-[2.5rem] font-bold leading-[1.02] tracking-[-0.04em] sm:text-[3.5rem]">{title}</h1>
        <p className="mt-6 max-w-[56ch] text-pretty text-[1.0625rem] leading-[1.6] text-stage-ink-2 sm:text-[1.125rem]">{lede}</p>
        {children}
      </div>
    </section>
  )
}

/** Labelled rows: a short heading on the left, the detail on the right (stacked on phones). */
export function Rows({ children }: { children: ReactNode }) {
  return <div className="border-b border-rule">{children}</div>
}

export function Row({ id, title, children }: { id?: string; title: ReactNode; children: ReactNode }) {
  return (
    <div
      id={id}
      className={`${SCROLL_OFFSET} grid grid-cols-[minmax(0,1fr)] gap-3 border-t border-rule py-8 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:gap-16`}
    >
      <h3 className="text-[1.125rem] font-semibold leading-snug text-ink">{title}</h3>
      {/* Long file paths in inline code may break anywhere, so they never push the page wider on phones. */}
      <div className="max-w-[62ch] space-y-3 text-[1.0625rem] leading-[1.65] text-ink-2 [&_a]:font-medium [&_a]:text-ink [&_a]:underline [&_a]:underline-offset-4 [&_code]:rounded [&_code]:bg-sunken [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.875em] [&_code]:text-ink [&_code]:[overflow-wrap:anywhere] [&_li]:pl-1 [&_strong]:font-semibold [&_strong]:text-ink [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:space-y-1.5 [&_ol]:pl-5">
        {children}
      </div>
    </div>
  )
}

/** Long-form text such as the legal pages: one readable column with H2 sections. */
export function Prose({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-[1240px] px-4 py-16 sm:px-8 lg:py-20">
      <div className="max-w-[70ch] space-y-4 text-[1.0625rem] leading-[1.7] text-ink-2 [&_a]:font-medium [&_a]:text-ink [&_a]:underline [&_a]:underline-offset-4 [&_code]:font-mono [&_code]:text-[0.875em] [&_code]:text-ink [&_h2]:mt-14 [&_h2]:scroll-mt-28 [&_h2]:text-[1.5rem] [&_h2]:font-bold [&_h2]:leading-tight [&_h2]:tracking-[-0.02em] [&_h2]:text-ink [&_h2:first-child]:mt-0 md:[&_h2]:scroll-mt-16 [&_li]:pl-1 [&_strong]:font-semibold [&_strong]:text-ink [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5">
        {children}
      </div>
    </div>
  )
}

const CONTROLS = [
  { title: 'Nothing merges without you.', panel: <MergePanel /> },
  { title: 'Every step is on the record.', panel: <RecordPanel /> },
  { title: 'Private data stays private.', panel: <PrivacyPanel /> },
]

/** The three controls, each shown as a small panel with its promise underneath. */
export function ControlPanels() {
  return (
    <ul className="grid gap-x-8 gap-y-12 md:grid-cols-3">
      {CONTROLS.map((item) => (
        <li key={item.title}>
          {item.panel}
          <p className="mt-5 text-[1.0625rem] font-semibold text-ink">{item.title}</p>
        </li>
      ))}
    </ul>
  )
}
