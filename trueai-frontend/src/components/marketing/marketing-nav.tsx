'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { cn } from '@/lib/utils'

const LINKS = [
  { href: '/how-it-works', label: 'How it works' },
  { href: '/security', label: 'Security' },
  { href: '/docs', label: 'Docs' },
  { href: '/#faq', label: 'FAQ' },
]

/** The marketing pages' navigation; marks the page being viewed. */
export function MarketingNav({ className }: { className?: string }) {
  const pathname = usePathname()
  return (
    <nav aria-label="Main" className={cn('flex items-center gap-6 text-[0.8125rem] text-stage-ink-2', className)}>
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          aria-current={pathname === link.href ? 'page' : undefined}
          className="shrink-0 hover:text-stage-ink aria-[current=page]:font-medium aria-[current=page]:text-stage-ink"
        >
          {link.label}
        </Link>
      ))}
    </nav>
  )
}
