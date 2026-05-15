'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useRouter } from 'next/navigation'
import { LayoutDashboard, Settings, Zap, Menu, X, Link2 } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'

interface SidebarProps {
  userEmail: string | null
  fullName: string | null
}

const navItems = [
  { label: 'Dashboard',    href: '/dashboard',    icon: LayoutDashboard },
  { label: 'Integrations', href: '/integrations', icon: Link2 },
  { label: 'Settings',     href: '/settings',     icon: Settings },
]

export function Sidebar({ userEmail, fullName }: SidebarProps) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const pathname = usePathname()
  const router = useRouter()
  const supabase = createClient()

  const handleSignOut = async () => {
    await supabase.auth.signOut()
    router.push('/login')
  }

  const isActive = (href: string) => {
    if (href === '/dashboard') return pathname === '/dashboard'
    return pathname.startsWith(href)
  }

  // Display name: prefer fullName from API, fall back to email prefix
  const emailPrefix = userEmail ? userEmail.split('@')[0] : 'user'
  const displayName = (fullName && fullName.trim()) ? fullName.trim() : emailPrefix
  const initials = displayName.slice(0, 2).toUpperCase()

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center gap-2 py-5 px-4 border-b border-white/8">
        <Zap size={16} className="text-white fill-white shrink-0" strokeWidth={2} />
        <span className="text-sm font-medium text-white tracking-tight">TrueAI</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 pt-1 overflow-y-auto">
        <p className="px-5 pt-4 pb-1 text-[10px] tracking-widest text-white/25 font-mono uppercase">
          Workspace
        </p>
        <div className="mt-1 space-y-px mx-2">
          {navItems.map(({ label, href, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center gap-2.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
                isActive(href)
                  ? 'bg-white/8 text-white'
                  : 'text-white/50 hover:bg-white/5 hover:text-white/80'
              }`}
            >
              <Icon size={15} strokeWidth={1.5} className="shrink-0" />
              {label}
            </Link>
          ))}
        </div>
      </nav>

      {/* User footer */}
      <div className="mt-auto border-t border-white/8 p-3">
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-md">
          <div className="w-7 h-7 rounded-full bg-white/10 flex items-center justify-center shrink-0">
            <span className="text-xs font-mono text-white/70">{initials}</span>
          </div>
          <span className="text-sm text-white/70 truncate">{displayName}</span>
        </div>
      </div>
    </div>
  )

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-56 bg-[#0a0a0a] border-r border-white/8 fixed inset-y-0 left-0 z-30">
        <SidebarContent />
      </aside>

      {/* Mobile hamburger */}
      <button
        className="md:hidden fixed top-3 left-4 z-50 text-white/50 hover:text-white transition-colors"
        onClick={() => setMobileOpen(!mobileOpen)}
        aria-label="Toggle menu"
      >
        {mobileOpen ? <X size={18} /> : <Menu size={18} />}
      </button>

      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-black/60"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Mobile drawer */}
      <aside
        className={`md:hidden fixed inset-y-0 left-0 z-50 w-56 bg-[#0a0a0a] border-r border-white/8 transition-transform duration-200 ease-in-out ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <SidebarContent />
      </aside>
    </>
  )
}
