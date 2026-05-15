import type { Metadata } from 'next'
import { Inter, JetBrains_Mono, Syne } from 'next/font/google'
import './globals.css'

const inter = Inter({ variable: '--font-inter', subsets: ['latin'], display: 'swap' })
const jetbrainsMono = JetBrains_Mono({ variable: '--font-jetbrains-mono', subsets: ['latin'], display: 'swap' })
const syne = Syne({ variable: '--font-syne', subsets: ['latin'], display: 'swap', weight: ['400','600','700','800'] })

export const metadata: Metadata = {
  title: 'TrueAI — AI-Powered Incident Analysis & Auto-Fix',
  description: 'TrueAI analyzes your production incidents, identifies root causes, and opens a fix PR — autonomously.',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} ${syne.variable} h-full antialiased dark`}>
      <body className="min-h-full bg-[#0a0a0a] text-[#f7f8f8] flex flex-col">
        {children}
      </body>
    </html>
  )
}

