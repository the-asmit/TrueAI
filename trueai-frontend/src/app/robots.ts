import type { MetadataRoute } from 'next'

import { APP_URL } from '@/lib/site'

// The app itself is private. The password pages stay crawlable so search
// engines can read their noindex tag instead of guessing from a link.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: ['/dashboard', '/integrations', '/settings', '/onboarding', '/auth/', '/github/'],
    },
    sitemap: `${APP_URL}/sitemap.xml`,
  }
}
