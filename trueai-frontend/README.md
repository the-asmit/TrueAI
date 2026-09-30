# TrueAI dashboard

The web app for [TrueAI](../README.md): sign up, connect GitHub and Sentry, follow incidents and read the reports.

Built with Next.js, React, Tailwind CSS and Supabase Auth.

## Setup

```bash
cp .env.local.example .env.local   # Supabase URL and anon key, TrueAI API URL, this app's URL
npm install
npm run dev                        # http://localhost:3000
```

The TrueAI API must be running (see the [main README](../README.md)). In Supabase → Authentication → URL
Configuration, set the Site URL to this app's URL and add `<app URL>/auth/callback` to the redirect URLs.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Development server |
| `npm run build` / `npm start` | Production build and server |
| `npm run lint` | Lint |
| `npm run typecheck` | Type check |

## Structure

```
src/
  app/          pages: landing, sign-in, onboarding, incidents, integrations, settings
  components/   UI building blocks and page sections
  lib/          API client, Supabase clients and helpers
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
