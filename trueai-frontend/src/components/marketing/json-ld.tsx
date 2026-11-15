import { headers } from 'next/headers'

import { APP_URL } from '@/lib/site'

/**
 * Structured data for search engines. The Content-Security-Policy (src/proxy.ts)
 * only allows scripts carrying this request's nonce, so the tag carries it too.
 */
export async function JsonLd({ data }: { data: object }) {
  const nonce = (await headers()).get('x-nonce') ?? undefined
  return (
    <script
      type="application/ld+json"
      nonce={nonce}
      // '<' is escaped so no string in the data can close the script tag.
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, '\\u003c') }}
    />
  )
}

/** BreadcrumbList for a page one level below the homepage. */
export function breadcrumbs(name: string, path: string) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Home', item: APP_URL },
      { '@type': 'ListItem', position: 2, name, item: `${APP_URL}${path}` },
    ],
  }
}
