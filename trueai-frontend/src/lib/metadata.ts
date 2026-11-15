import type { Metadata } from 'next'

type OpenGraph = NonNullable<Metadata['openGraph']>

/*
 * A page that sets its own `openGraph` or `twitter` replaces the parent's whole
 * object rather than merging with it, and loses the root's opengraph-image.png
 * with it. So every page builds both from these shared defaults, which name
 * that image explicitly. `url: './'` resolves against each page's own path,
 * like the canonical URL in the root layout.
 */
const SHARE_IMAGE = {
  url: '/opengraph-image.png',
  width: 1200,
  height: 630,
  alt: 'TrueAI: Stop debugging. Start merging. Every Sentry error becomes a reviewed fix, opened as a pull request.',
}

export const OPEN_GRAPH_DEFAULTS: OpenGraph = { type: 'website', siteName: 'TrueAI', url: './', images: [SHARE_IMAGE] }
export const TWITTER_CARD = 'summary_large_image'

/**
 * Metadata for one page: its title and description, repeated in the social
 * preview. `title` goes through the root template ("… · TrueAI") unless it is
 * `{ absolute }`; `socialTitle` is what link previews show.
 */
export function pageMetadata({
  title,
  socialTitle,
  description,
  noindex = false,
}: {
  title: string | { absolute: string }
  socialTitle: string
  description: string
  noindex?: boolean
}): Metadata {
  return {
    title,
    description,
    openGraph: { ...OPEN_GRAPH_DEFAULTS, title: socialTitle, description },
    twitter: { card: TWITTER_CARD, title: socialTitle, description, images: [SHARE_IMAGE] },
    ...(noindex && { robots: { index: false, follow: false } }),
  }
}
