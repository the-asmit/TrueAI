import Link from 'next/link'

import { cn } from '@/lib/utils'

/*
 * TrueAI mark: a "T" drawn as a merge. The crossbar is the main branch, the stem is
 * the fix branch sweeping into it, and the green dot at its base is the fix itself.
 * The colours are fixed (it is a logo, not UI), and the faint edge keeps the badge
 * visible on dark backgrounds. app/icon.svg, app/favicon.ico and app/apple-icon.png
 * use the same drawing.
 */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn('size-6 shrink-0', className)}>
      <rect x="0.5" y="0.5" width="31" height="31" rx="8" fill="#121417" stroke="#ffffff" strokeOpacity="0.14" />
      <path fill="#f1f0eb" d="M8.4 8.3h15.2a1.85 1.85 0 0 1 0 3.7h-.9a5.6 5.6 0 0 0-5.6 5.6v2.6h-3.7V12H8.4a1.85 1.85 0 0 1 0-3.7z" />
      <circle cx="15.25" cy="22.6" r="3.6" fill="#56c98f" />
    </svg>
  )
}

export function Wordmark({ href = '/', className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn('inline-flex items-center gap-2 text-ink', className)} aria-label="TrueAI home">
      <Mark />
      <span className="text-[1rem] font-bold tracking-[-0.025em]">TrueAI</span>
    </Link>
  )
}

/** Sentry's mark, drawn from its published path (Simple Icons). */
export function SentryMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={cn('size-4', className)} fill="currentColor">
      <path d="M13.91 2.505c-.873-1.448-2.972-1.448-3.844 0L6.904 7.92a15.478 15.478 0 0 1 8.53 12.811h-2.221A13.301 13.301 0 0 0 5.784 9.814l-2.926 5.06a7.65 7.65 0 0 1 4.435 5.848H2.194a.365.365 0 0 1-.298-.534l1.413-2.402a5.16 5.16 0 0 0-1.614-.913L.296 19.275a2.182 2.182 0 0 0 .812 2.999 2.24 2.24 0 0 0 1.086.288h6.983a9.322 9.322 0 0 0-3.845-8.318l1.11-1.922a11.47 11.47 0 0 1 4.95 10.24h5.915a17.242 17.242 0 0 0-7.885-15.28l2.244-3.845a.37.37 0 0 1 .504-.13c.255.14 9.75 16.708 9.928 16.9a.365.365 0 0 1-.327.543h-2.287c.029.612.029 1.223 0 1.831h2.297a2.206 2.206 0 0 0 1.922-3.31z" />
    </svg>
  )
}

/** GitHub's mark, drawn from its published path (lucide no longer ships brand icons). */
export function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden className={cn('size-4', className)} fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}
