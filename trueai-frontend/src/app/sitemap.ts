import type { MetadataRoute } from 'next'

import { APP_URL } from '@/lib/site'

// Only the public pages: everything else needs an account.
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: APP_URL, changeFrequency: 'monthly', priority: 1 },
    { url: `${APP_URL}/how-it-works`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${APP_URL}/security`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${APP_URL}/docs`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${APP_URL}/signup`, changeFrequency: 'yearly', priority: 0.6 },
    { url: `${APP_URL}/login`, changeFrequency: 'yearly', priority: 0.4 },
  ]
}
