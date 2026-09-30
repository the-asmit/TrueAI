# TrueAI dashboard

The web app for [TrueAI](../README.md): sign up, connect GitHub and Sentry, and read the incident reports the agents
write.

Next.js 16 (App Router, server components), Tailwind CSS v4, Supabase Auth.

## Setup

```bash
cp .env.local.example .env.local   # Supabase URL + anon key, TrueAI API URL, this app's URL
npm install
npm run dev                        # http://localhost:3000
```

The TrueAI API (see the root README) must be running. In Supabase → Authentication → URL Configuration, set the Site
URL to this app's URL and add `<app URL>/auth/callback` to the redirect URLs (used by email confirmation and password
reset).

## Scripts

| Command | |
|---|---|
| `npm run dev` | Development server (Turbopack) |
| `npm run build` / `npm start` | Production build and server |
| `npm run lint` | ESLint |
| `npm run typecheck` | TypeScript |

## How it is put together

- **Server-first.** Pages are server components that call the TrueAI API through `src/lib/api/client.ts`, which is
  server-only: the browser never holds an API token or talks to the backend directly. Mutations are server actions in
  `src/app/actions/`.
- **Auth.** `src/proxy.ts` refreshes the Supabase session, protects the app routes (sending visitors to `/login?next=…`,
  checked by `src/lib/redirect.ts` against open redirects) and sets a per-request CSP nonce.
- **Live updates.** Incident pages poll quickly while the agents are working and slowly otherwise
  (`src/components/auto-refresh.tsx`), pausing while the tab is hidden.
- **Design.** A dark stage for the landing page, paper and ink for the app, and colour used only for incident state
  (fixed, in review, needs you, failure). Public Sans with JetBrains Mono for code; light and dark themes. Design
  tokens live in `src/app/globals.css`.

```
src/
  app/
    (auth)/          login, signup, forgot and reset password
    (dashboard)/     incidents, incident report, integrations, settings
    onboarding/      first-run setup
    actions/         server actions
    auth/, github/   auth callback, sign-out and GitHub hand-off route handlers
  components/
    ui/              buttons, fields, notices, status marks, dialogs
    report/          diff view, timeline, prose, incident actions
    integrations/    GitHub, repository picker, Sentry settings, webhook URL
  lib/               API client and types, Supabase clients, formatting
```

## Docker

```bash
docker build \
  --build-arg NEXT_PUBLIC_SUPABASE_URL=… \
  --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY=… \
  --build-arg NEXT_PUBLIC_API_BASE_URL=… \
  --build-arg NEXT_PUBLIC_APP_URL=… \
  -t trueai-frontend .
docker run -p 3000:3000 trueai-frontend
```

`NEXT_PUBLIC_*` values are compiled into the build, so they are build arguments.
