'use client'

import { Moon, Sun } from 'lucide-react'

import { cn } from '@/lib/utils'

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365

/**
 * One-click switch between the light and dark themes. The choice is saved in
 * the same "theme" cookie the dashboard's theme setting uses, so it carries
 * across the app. Everything happens in the browser, so the switch is instant.
 */
export function ThemeToggle({ className }: { className?: string }) {
  function toggle() {
    const root = document.documentElement
    const followsSystem = root.dataset.theme !== 'light' && root.dataset.theme !== 'dark'
    const isDark = followsSystem ? window.matchMedia('(prefers-color-scheme: dark)').matches : root.dataset.theme === 'dark'
    const next = isDark ? 'light' : 'dark'
    root.dataset.theme = next
    document.cookie = `theme=${next}; path=/; max-age=${ONE_YEAR_SECONDS}; samesite=lax`
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Switch between light and dark theme"
      title="Switch theme"
      className={cn(
        'inline-flex size-9 items-center justify-center rounded-md text-stage-ink-2 transition-colors hover:bg-stage-ink/5 hover:text-stage-ink focus-visible:outline-stage-ink',
        className,
      )}
    >
      {/* The stylesheet shows the icon of the theme a click switches to. */}
      <Moon className="size-4 [display:var(--light-only)]" aria-hidden />
      <Sun className="size-4 [display:var(--dark-only)]" aria-hidden />
    </button>
  )
}
