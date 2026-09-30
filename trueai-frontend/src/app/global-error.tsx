'use client'

// Last-resort boundary (the root layout itself failed), so it renders its own document.
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: 'system-ui, sans-serif', background: '#f8f8f5', color: '#121417', margin: 0 }}>
        <main style={{ maxWidth: 420, margin: '20vh auto', padding: '0 24px' }}>
          <h1 style={{ fontSize: 24, margin: 0 }}>TrueAI is having trouble</h1>
          <p style={{ color: '#3a3e45', lineHeight: 1.6 }}>The page could not be loaded. Please try again in a moment.</p>
          <button
            onClick={reset}
            style={{ height: 36, padding: '0 16px', borderRadius: 5, border: 0, background: '#121417', color: '#fff', cursor: 'pointer' }}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  )
}
