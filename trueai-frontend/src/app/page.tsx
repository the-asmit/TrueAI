'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { motion, AnimatePresence, type Variants } from 'framer-motion'
import {
  Menu, X, Zap, GitPullRequest, Search, GitBranch,
  Activity, FileText, Link as LinkIcon, Brain,
  ArrowRight,
} from 'lucide-react'

// ─── constants ────────────────────────────────────────────────────────────────

const TERMINAL_LINES = [
  { time: '14:23:01', tag: 'INFO',  tc: 'text-[#8a8f98]',  msg: 'Alert received: 574% spike in auth-service error-rate' },
  { time: '14:23:02', tag: 'WARN',  tc: 'text-[#f59e0b]',  msg: 'Analyzing recent deployments on auth-service...' },
  { time: '14:23:04', tag: 'INFO',  tc: 'text-[#8a8f98]',  msg: 'Identified anomaly in Redis connection pool — 0/50 free' },
  { time: '14:23:07', tag: 'INFO',  tc: 'text-[#8a8f98]',  msg: 'Root cause: pool_size not set on cold restart' },
  { time: '14:23:09', tag: 'FIXED', tc: 'text-[#22c55e]',  msg: 'PR #247 opened: fix: initialize Redis connection pool sizing' },
]

const COMPANIES = ['Stripe','Vercel','Notion','Linear','Shopify','GitHub','Cloudflare','Supabase','PlanetScale','Render']

const FEATURES = [
  { icon: Zap,            title: 'AI Incident Analysis',  desc: 'Instantly correlates logs, traces, and metrics to surface what actually broke.' },
  { icon: GitPullRequest, title: 'Auto-Fix Generation',   desc: 'Generates targeted code fixes and opens a PR directly to your repository.' },
  { icon: Search,         title: 'Root Cause Detection',  desc: 'Goes beyond symptoms. Identifies the exact line, config, or dependency at fault.' },
  { icon: GitBranch,      title: 'GitHub Integration',    desc: 'Connects to your repos in minutes. Works with any branch strategy or workflow.' },
  { icon: Activity,       title: 'Real-time Monitoring',  desc: 'Watches your services continuously. Triggers analysis the moment anomalies appear.' },
  { icon: FileText,       title: 'Audit Trail & Reports', desc: 'Every decision logged. Full incident timeline exported for post-mortems.' },
]

const STEPS = [
  { num: '01', icon: LinkIcon,       title: 'Connect', desc: 'Connect your GitHub repo and monitoring stack in under 2 minutes.' },
  { num: '02', icon: Brain,          title: 'Analyze', desc: 'AI detects the incident, pulls logs, traces the stack, and pinpoints root cause.' },
  { num: '03', icon: GitPullRequest, title: 'Fix',     desc: 'A fix is generated and a pull request is opened — ready for your review.' },
]

const TESTIMONIALS = [
  {
    quote: "We used to spend 45 minutes triaging every Sentry alert. TrueAI cuts that to under 3. The PRs it opens are genuinely good — we merge most of them straight to main.",
    name: 'Priya Nair', role: 'Staff SRE · Cloudflare', initials: 'PN',
  },
  {
    quote: "It caught a race condition we'd been chasing for two sprints. Opened the fix PR while I was still reading the Slack alert. Honestly unnerving how fast it is.",
    name: 'Marcus Webb', role: 'Platform Lead · Notion', initials: 'MW',
  },
]

// ─── fade-up variant ──────────────────────────────────────────────────────────

const fadeUp = (delay = 0): Variants => ({
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.45, delay, ease: [0.25, 0, 0, 1] } },
})

// ─── Navbar ────────────────────────────────────────────────────────────────────

function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 8)
    window.addEventListener('scroll', fn, { passive: true })
    return () => window.removeEventListener('scroll', fn)
  }, [])

  const links = [
    { label: 'Features', href: '#features' },
    { label: 'How it Works', href: '#how-it-works' },
    { label: 'Contact', href: '#contact' },
  ]

  return (
    <header className={`fixed inset-x-0 top-0 z-50 transition-all duration-200 ${scrolled ? 'bg-[#0a0a0a] border-b border-[#23252a]' : 'bg-transparent'}`}>
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 select-none">
          <Zap size={14} className="text-[#f7f8f8] fill-[#f7f8f8]" strokeWidth={2} />
          <span className="text-[15px] font-semibold tracking-tight text-[#f7f8f8]">TrueAI</span>
        </Link>

        {/* Desktop links */}
        <nav className="hidden md:flex items-center gap-7">
          {links.map(l => (
            <a key={l.href} href={l.href} className="text-[13px] text-[#8a8f98] hover:text-[#f7f8f8] transition-colors">{l.label}</a>
          ))}
        </nav>

        {/* Desktop CTA */}
        <Link href="/signup" className="hidden md:inline-flex items-center gap-1.5 border border-[#23252a] text-[#f7f8f8] text-[13px] px-4 py-2 rounded-lg hover:bg-[#0f1011] transition-colors">
          Get Started <ArrowRight size={12} />
        </Link>

        {/* Hamburger */}
        <button className="md:hidden text-[#8a8f98] hover:text-[#f7f8f8]" onClick={() => setOpen(v => !v)}>
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.15 }}
            className="md:hidden bg-[#0a0a0a] border-b border-[#23252a] px-6 py-4 flex flex-col gap-4">
            {links.map(l => (
              <a key={l.href} href={l.href} onClick={() => setOpen(false)} className="text-[13px] text-[#8a8f98] hover:text-[#f7f8f8] transition-colors">{l.label}</a>
            ))}
            <Link href="/signup" onClick={() => setOpen(false)}
              className="inline-flex items-center justify-center border border-[#23252a] text-[#f7f8f8] text-[13px] px-4 py-2 rounded-lg hover:bg-[#0f1011] transition-colors">
              Get Started →
            </Link>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  )
}

// ─── Terminal ─────────────────────────────────────────────────────────────────

function Terminal() {
  const [count, setCount] = useState(0)
  const [cursor, setCursor] = useState(false)
  const t = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let c = 0
    const tick = () => {
      if (c < TERMINAL_LINES.length) { c++; setCount(c); t.current = setTimeout(tick, 900) }
      else setCursor(true)
    }
    t.current = setTimeout(tick, 1200)
    return () => { if (t.current) clearTimeout(t.current) }
  }, [])

  return (
    <div className="mt-14 w-full max-w-2xl mx-auto">
      <div className="rounded-xl border border-[#23252a] bg-[#0a0b0d] overflow-hidden">
        {/* Title bar */}
        <div className="flex items-center gap-2 px-4 py-3 bg-[#0f1011] border-b border-[#23252a]">
          <span className="w-3 h-3 rounded-full bg-[#ff5f57]" />
          <span className="w-3 h-3 rounded-full bg-[#febc2e]" />
          <span className="w-3 h-3 rounded-full bg-[#28c840]" />
          <span className="ml-3 font-mono text-[11px] text-[#62666d]">trueai-agent · production</span>
        </div>
        {/* Lines */}
        <div className="p-5 font-mono text-[13px] space-y-2 min-h-[160px]">
          {TERMINAL_LINES.slice(0, count).map((l, i) => (
            <motion.div key={i} initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} className="flex flex-wrap gap-x-2">
              <span className="text-[#62666d] shrink-0">[{l.time}]</span>
              <span className={`${l.tc} shrink-0 w-12`}>[{l.tag}]</span>
              <span className="text-[#f7f8f8]/70">{l.msg}</span>
            </motion.div>
          ))}
          {cursor && (
            <motion.span animate={{ opacity: [1, 0, 1] }} transition={{ repeat: Infinity, duration: 1 }} className="text-[#8a8f98] font-mono">▌</motion.span>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Hero ─────────────────────────────────────────────────────────────────────



function HeroSection() {
  return (
    <section className="min-h-screen flex flex-col items-center justify-center pt-20 pb-24 px-6">
      {/* Badge */}
      <motion.div variants={fadeUp(0.1)} initial="hidden" animate="visible"
        className="mb-8 border border-[#23252a] text-[#62666d] font-mono text-[11px] tracking-widest uppercase px-3 py-1 rounded-full">
        AI-powered incident resolution
      </motion.div>

      {/* Headline */}
      <motion.h1
        variants={fadeUp(0.2)} initial="hidden" animate="visible"
        className="font-syne font-extrabold text-4xl md:text-5xl text-center leading-tight tracking-tight max-w-3xl"
      >
        Incidents resolved.<br />
        Before you wake up.
      </motion.h1>

      {/* Subtext */}
      <motion.p variants={fadeUp(0.75)} initial="hidden" animate="visible"
        className="mt-6 text-center text-[#8a8f98] text-[16px] max-w-xl leading-relaxed">
        TrueAI analyzes your production incidents, identifies root causes, and opens a fix PR —{' '}
        <span className="text-[#f7f8f8]">autonomously.</span>
      </motion.p>

      {/* CTAs */}
      <motion.div variants={fadeUp(0.88)} initial="hidden" animate="visible" className="mt-8 flex flex-wrap gap-3 justify-center">
        <Link href="/signup"
          className="bg-[#ededed] text-[#010102] text-[14px] font-medium px-5 py-2.5 rounded-lg hover:bg-white transition-colors">
          Get Started Free
        </Link>
        <a href="#how-it-works"
          className="border border-[#23252a] text-[#8a8f98] hover:text-[#f7f8f8] hover:border-[#34343a] text-[14px] px-5 py-2.5 rounded-lg transition-all">
          See how it works ↓
        </a>
      </motion.div>

      {/* Terminal */}
      <motion.div variants={fadeUp(1.0)} initial="hidden" animate="visible" className="w-full max-w-2xl">
        <Terminal />
      </motion.div>
    </section>
  )
}

// ─── Social Proof ─────────────────────────────────────────────────────────────

function SocialProofSection() {
  const items = [...COMPANIES, ...COMPANIES]
  return (
    <section id="social-proof" className="border-y border-[#23252a] py-10 overflow-hidden">
      <p className="text-center text-[#62666d] font-mono text-[11px] tracking-widest uppercase mb-7">
        Trusted by engineers at
      </p>
      <div className="overflow-hidden">
        <div className="animate-marquee flex gap-14 w-max">
          {items.map((name, i) => (
            <span key={i} className="font-mono text-[#34343a] hover:text-[#8a8f98] text-[13px] transition-colors cursor-default whitespace-nowrap">
              {name}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Features ─────────────────────────────────────────────────────────────────

function FeaturesSection() {
  return (
    <section id="features" className="py-24 px-6">
      <div className="max-w-6xl mx-auto">
        <motion.div variants={fadeUp(0)} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-60px' }}>
          <p className="text-[#62666d] font-mono text-[11px] tracking-widest uppercase mb-3">Features</p>
          <h2 className="font-syne font-bold text-[32px] text-[#f7f8f8] mb-3 max-w-xl">
            Everything your on-call rotation wishes it had.
          </h2>
          <p className="text-[#8a8f98] text-[15px] mb-16 max-w-2xl">
            From detection to deployed fix — TrueAI handles the entire incident lifecycle.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px bg-[#23252a] border border-[#23252a] rounded-xl overflow-hidden">
          {FEATURES.map(({ icon: Icon, title, desc }, i) => (
            <motion.div key={title}
              variants={fadeUp(i * 0.05)} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-40px' }}
              className="bg-[#0a0a0a] p-8 hover:bg-[#0f1011] hover:border-[#34343a] transition-all group cursor-default">
              <Icon size={24} strokeWidth={1.5} className="text-[#f7f8f8]/70 group-hover:text-[#f7f8f8] transition-colors mb-5" />
              <h3 className="font-semibold text-[#f7f8f8] text-[15px] mb-2">{title}</h3>
              <p className="text-[#8a8f98] text-[13px] leading-relaxed">{desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── How It Works ─────────────────────────────────────────────────────────────

function HowItWorksSection() {
  return (
    <section id="how-it-works" className="pt-24 pb-16 px-6 bg-[#0a0b0d] border-y border-[#23252a]">
      <div className="max-w-5xl mx-auto">
        <motion.div variants={fadeUp(0)} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-60px' }}>
          <p className="text-[#62666d] font-mono text-[11px] tracking-widest uppercase mb-3">How it Works</p>
          <h2 className="font-syne font-bold text-[32px] text-[#f7f8f8] mb-3">
            From alert to fix in minutes, not hours.
          </h2>
          <p className="text-[#8a8f98] text-[15px] mb-16">Three steps. Zero toil. No manual intervention required.</p>
        </motion.div>

        <div className="flex flex-col md:flex-row items-start">
          {STEPS.map(({ num, icon: Icon, title, desc }, i) => (
            <div key={num} className="flex md:flex-row flex-col items-start w-full">
              <motion.div
                variants={fadeUp(i * 0.15)} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-40px' }}
                className="flex-1">
                <p className="font-mono text-[#62666d] text-[11px] mb-3">{num}</p>
                <div className="w-10 h-10 flex items-center justify-center rounded-lg border border-[#23252a] bg-[#0a0a0a] text-[#8a8f98] mb-4">
                  <Icon size={16} strokeWidth={1.5} />
                </div>
                <h3 className="font-syne font-semibold text-[#f7f8f8] text-[18px] mb-2">{title}</h3>
                <p className="text-[#8a8f98] text-[13px] leading-relaxed max-w-xs">{desc}</p>
              </motion.div>
              {i < STEPS.length - 1 && (
                <>
                  <div className="hidden md:block flex-shrink-0 w-16 border-t border-dashed border-[#23252a] mt-9 mx-4" />
                  <div className="md:hidden w-px h-10 border-l border-dashed border-[#23252a] ml-5 my-4" />
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Testimonials ─────────────────────────────────────────────────────────────

function TestimonialsSection() {
  return (
    <section id="testimonials" className="py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <motion.div variants={fadeUp(0)} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-60px' }}>
          <p className="text-[#62666d] font-mono text-[11px] tracking-widest uppercase mb-3">Testimonials</p>
          <h2 className="font-syne font-bold text-[32px] text-[#f7f8f8] mb-16">What engineers say.</h2>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {TESTIMONIALS.map(({ quote, name, role, initials }, i) => (
            <motion.div key={name}
              variants={fadeUp(i * 0.1)} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-40px' }}
              className="bg-[#0f1011] border border-[#23252a] rounded-xl p-8 hover:border-[#34343a] transition-colors">
              <p className="text-[#8a8f98] text-[15px] italic leading-relaxed mb-7">&ldquo;{quote}&rdquo;</p>
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-[#ededed]/10 flex items-center justify-center shrink-0">
                  <span className="font-mono text-[11px] font-semibold text-[#f7f8f8]">{initials}</span>
                </div>
                <div>
                  <p className="text-[#f7f8f8] text-[13px] font-medium">{name}</p>
                  <p className="font-mono text-[#62666d] text-[11px]">{role}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Contact ──────────────────────────────────────────────────────────────────

function ContactSection() {
  const [form, setForm] = useState({ name: '', email: '', message: '' })
  const [sent, setSent] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setSent(true)
    setForm({ name: '', email: '', message: '' })
    setTimeout(() => setSent(false), 5000)
  }

  const inputCls = "w-full bg-[#0a0a0a] border border-[#23252a] rounded-lg px-4 py-2.5 text-[14px] text-[#f7f8f8] placeholder:text-[#62666d] focus:outline-none focus:border-[#34343a] transition-colors"

  return (
    <section id="contact" className="py-24 px-6 bg-[#0a0b0d] border-y border-[#23252a]">
      <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-16 items-start">
        {/* Left */}
        <motion.div variants={fadeUp(0)} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-60px' }}>
          <p className="text-[#62666d] font-mono text-[11px] tracking-widest uppercase mb-3">Contact</p>
          <h2 className="font-syne font-bold text-[28px] text-[#f7f8f8] mb-4">Get in touch.</h2>
          <p className="text-[#8a8f98] text-[14px] leading-relaxed">
            Have questions, feedback, or want a walkthrough? We&apos;d love to hear from you. Drop us a message and we&apos;ll get back within one business day.
          </p>
        </motion.div>

        {/* Right — form */}
        <motion.form variants={fadeUp(0.1)} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-60px' }}
          onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input required placeholder="Name" value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className={inputCls} />
          <input required type="email" placeholder="Email" value={form.email}
            onChange={e => setForm(f => ({ ...f, email: e.target.value }))} className={inputCls} />
          <textarea required placeholder="Message" rows={5} value={form.message}
            onChange={e => setForm(f => ({ ...f, message: e.target.value }))} className={`${inputCls} resize-none`} />

          <button type="submit"
            className="self-start bg-[#ededed] text-[#010102] text-[14px] font-medium px-5 py-2.5 rounded-lg hover:bg-white transition-colors">
            Send Message
          </button>

          <AnimatePresence>
            {sent && (
              <motion.p initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className="text-[#22c55e] font-mono text-[13px]">
                ✓ Message sent. We&apos;ll be in touch soon.
              </motion.p>
            )}
          </AnimatePresence>
        </motion.form>
      </div>
    </section>
  )
}

// ─── CTA Banner ───────────────────────────────────────────────────────────────

function CTABannerSection() {
  return (
    <section className="py-24 px-6 bg-[#111111] border-y border-[#23252a]">
      <motion.div variants={fadeUp(0)} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-60px' }}
        className="max-w-3xl mx-auto text-center">
        <h2 className="font-syne font-bold text-[40px] md:text-[48px] text-[#f7f8f8] leading-tight mb-4">
          Stop firefighting.<br />Start shipping.
        </h2>
        <p className="text-[#8a8f98] text-[15px] mb-8">
          Join engineering teams using TrueAI to eliminate incident toil.
        </p>
        <Link href="/signup"
          className="inline-flex items-center gap-2 bg-[#ededed] text-[#010102] text-[14px] font-medium px-6 py-3 rounded-lg hover:bg-white transition-colors">
          Get Started Free <ArrowRight size={14} />
        </Link>
      </motion.div>
    </section>
  )
}

// ─── Footer ───────────────────────────────────────────────────────────────────

function FooterSection() {
  const links = [
    { label: 'Features', href: '#features' },
    { label: 'How it Works', href: '#how-it-works' },
    { label: 'Contact', href: '#contact' },
  ]

  return (
    <footer className="bg-[#0a0b0d] border-t border-[#23252a] px-6 pt-10 pb-8">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-6 mb-8">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <Zap size={14} className="text-[#f7f8f8] fill-[#f7f8f8]" strokeWidth={2} />
          <span className="text-[15px] font-semibold tracking-tight text-[#f7f8f8]">TrueAI</span>
        </div>

        {/* Nav */}
        <nav className="flex items-center gap-6">
          {links.map(l => (
            <a key={l.href} href={l.href} className="text-[#62666d] text-[13px] hover:text-[#8a8f98] transition-colors">{l.label}</a>
          ))}
        </nav>

        {/* Socials */}
        <div className="flex items-center gap-4">
          <a href="https://github.com/the-asmit" target="_blank" rel="noopener noreferrer"
            className="font-mono text-xs text-white/40 hover:text-white/70 transition-colors">GitHub</a>
          <a href="https://www.linkedin.com/in/asmit-nayan/" target="_blank" rel="noopener noreferrer"
            className="font-mono text-xs text-white/40 hover:text-white/70 transition-colors">LinkedIn</a>
        </div>
      </div>

      <div className="max-w-6xl mx-auto border-t border-[#23252a] pt-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-[#34343a]">© {new Date().getFullYear()} TrueAI. All rights reserved.</span>
        <span className="font-mono text-[11px] text-[#34343a]">Built for the engineers who keep everything running.</span>
      </div>
    </footer>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <main className="bg-[#0a0a0a] text-[#f7f8f8] overflow-x-hidden">
      <Navbar />
      <HeroSection />
      <SocialProofSection />
      <FeaturesSection />
      <HowItWorksSection />
      <TestimonialsSection />
      <ContactSection />
      <CTABannerSection />
      <FooterSection />
    </main>
  )
}
