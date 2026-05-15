import { createClient } from '@/lib/supabase/server'
import { apiClient } from '@/lib/api/client'
import { Sidebar } from '@/components/layout/sidebar'
import { TopNav } from '@/components/layout/top-nav'

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  // Fetch display name from /auth/me; fall back silently on error
  let fullName: string | null = null
  try {
    const me = await apiClient.get<{ full_name?: string }>('/auth/me')
    fullName = me.full_name || null
  } catch {
    // non-fatal — sidebar will fall back to email prefix
  }

  return (
    <div className="flex h-screen bg-[#0a0a0a] overflow-hidden">
      <Sidebar userEmail={user?.email ?? null} fullName={fullName} />
      <div className="flex flex-col flex-1 md:ml-56 min-w-0 overflow-hidden">
        <TopNav userEmail={user?.email ?? null} />
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
