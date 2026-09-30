'use client'

import { FileText, Menu, Monitor, Moon, Plug, Settings2, Sun, X } from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Dialog } from 'radix-ui'
import { useState, useTransition, type ReactNode } from 'react'

import { setTheme } from '@/app/actions/account'
import { Wordmark } from '@/components/brand'
import { cn } from '@/lib/utils'

interface ShellProps {
  displayName: string
  email: string | null
  needsYou: number
  theme: 'light' | 'dark' | 'system'
  children: ReactNode
}

const NAV = [
  { href: '/dashboard', label: 'Incidents', icon: FileText },
  { href: '/integrations', label: 'Integrations', icon: Plug },
  { href: '/settings', label: 'Settings', icon: Settings2 },
]

export function AppShell({ displayName, email, needsYou, theme, children }: ShellProps) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="min-h-dvh bg-paper lg:grid lg:grid-cols-[232px_1fr]">
      {/* ---- Desktop rail ---- */}
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-rule bg-paper lg:flex">
        <div className="px-5 pb-6 pt-5">
          <Wordmark href="/dashboard" />
        </div>
        <Navigation needsYou={needsYou} />
        <AccountFooter displayName={displayName} email={email} theme={theme} />
      </aside>

      {/* ---- Mobile bar ---- */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-rule bg-paper/95 px-4 backdrop-blur-sm lg:hidden">
        <Wordmark href="/dashboard" />
        <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
          <Dialog.Trigger className="inline-flex size-9 items-center justify-center rounded-md text-ink-2 hover:bg-sunken" aria-label="Open navigation">
            <Menu className="size-5" />
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/30" />
            <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-[272px] flex-col border-r border-rule bg-paper focus:outline-none">
              <div className="flex items-center justify-between px-5 pb-6 pt-4">
                <Dialog.Title asChild>
                  <span>
                    <Wordmark href="/dashboard" />
                  </span>
                </Dialog.Title>
                <Dialog.Close className="inline-flex size-9 items-center justify-center rounded-md text-ink-2 hover:bg-sunken" aria-label="Close navigation">
                  <X className="size-5" />
                </Dialog.Close>
              </div>
              <Dialog.Description className="sr-only">Main navigation</Dialog.Description>
              <Navigation needsYou={needsYou} onNavigate={() => setMenuOpen(false)} />
              <AccountFooter displayName={displayName} email={email} theme={theme} />
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </header>

      <main id="main" className="min-w-0">
        {children}
      </main>
    </div>
  )
}

function Navigation({ needsYou, onNavigate }: { needsYou: number; onNavigate?: () => void }) {
  const pathname = usePathname()
  return (
    <nav aria-label="Main" className="flex-1 px-3">
      <ul className="space-y-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === '/dashboard' ? pathname === '/dashboard' || pathname.startsWith('/dashboard/') : pathname.startsWith(href)
          return (
            <li key={href}>
              <Link
                href={href}
                onClick={onNavigate}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex h-9 items-center gap-3 rounded-md px-2.5 text-sm transition-colors duration-150',
                  active ? 'bg-sheet font-medium text-ink shadow-[inset_0_0_0_1px_var(--rule)]' : 'text-ink-2 hover:bg-sunken hover:text-ink',
                )}
              >
                <Icon className="size-4 shrink-0" aria-hidden />
                <span className="flex-1">{label}</span>
                {href === '/dashboard' && needsYou > 0 && (
                  <span className="tabular rounded-sm bg-human-tint px-1.5 text-[0.75rem] font-semibold text-human" title={`${needsYou} need you`}>
                    {needsYou}
                    <span className="sr-only"> incidents need you</span>
                  </span>
                )}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

function AccountFooter({ displayName, email, theme }: { displayName: string; email: string | null; theme: 'light' | 'dark' | 'system' }) {
  return (
    <div className="space-y-3 border-t border-rule px-4 py-4">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-ink">{displayName}</p>
        {email && <p className="truncate text-[0.8125rem] text-ink-3">{email}</p>}
      </div>
      <ThemeSwitch current={theme} />
      <form action="/auth/signout" method="post">
        <button type="submit" className="text-[0.8125rem] text-ink-2 underline-offset-4 hover:text-ink hover:underline">
          Sign out
        </button>
      </form>
    </div>
  )
}

function ThemeSwitch({ current }: { current: 'light' | 'dark' | 'system' }) {
  const [pending, startTransition] = useTransition()
  const options = [
    { value: 'light' as const, label: 'Light', icon: Sun },
    { value: 'system' as const, label: 'System', icon: Monitor },
    { value: 'dark' as const, label: 'Dark', icon: Moon },
  ]
  return (
    <div role="radiogroup" aria-label="Theme" className={cn('inline-flex rounded-md border border-rule p-0.5', pending && 'opacity-60')}>
      {options.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={current === value}
          aria-label={label}
          title={label}
          onClick={() => startTransition(() => setTheme(value))}
          className={cn(
            'inline-flex size-7 items-center justify-center rounded-[4px] text-ink-3 transition-colors hover:text-ink',
            current === value && 'bg-sunken text-ink',
          )}
        >
          <Icon className="size-3.5" />
        </button>
      ))}
    </div>
  )
}
