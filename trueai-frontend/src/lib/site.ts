/** The public address of this dashboard, without a trailing slash. Used for metadata, the sitemap and structured data. */
export const APP_URL = (process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000').replace(/\/+$/, '')

/** TrueAI's source code. */
export const REPO_URL = 'https://github.com/the-asmit/TrueAI'
