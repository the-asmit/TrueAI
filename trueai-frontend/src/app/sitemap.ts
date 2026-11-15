import type { MetadataRoute } from 'next'

import { APP_URL } from '@/lib/site'

// Only the public pages worth finding in search: the app needs an account, and sign-in has nothing to rank for.
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: APP_URL, changeFrequency: 'monthly', priority: 1 },
    { url: `${APP_URL}/how-it-works`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${APP_URL}/security`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${APP_URL}/docs`, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${APP_URL}/signup`, changeFrequency: 'yearly', priority: 0.6 },
    { url: `${APP_URL}/privacy`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${APP_URL}/terms`, changeFrequency: 'yearly', priority: 0.3 },
  ]
}
