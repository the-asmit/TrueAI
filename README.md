# TrueAI

**Stop debugging. Start merging.**

TrueAI turns production errors into reviewed fixes. When Sentry reports an error, TrueAI finds the root cause in your
code and opens a pull request with the fix, usually within a minute. When the problem isn't in the code (a database
that is down, a missing environment variable), it gives you clear next steps instead. Nothing is merged without you.

```
Sentry error  ──▶  TrueAI  ──▶  root cause + fix  ──▶  GitHub pull request  ──▶  you review and merge
                                        └──────────▶  next steps, when code isn't the answer
```

## Features

- **Automatic root-cause analysis** for every new Sentry error, based on the stack trace and your actual source code.
- **Fixes as pull requests**: a small, reviewed change opened on your repository, ready for you to merge.
- **Next steps for everything else**: configuration and infrastructure incidents get a checklist, not a risky patch.
- **A team of AI agents**, each with a focused job, checked by built-in safety rules before anything is opened.
- **Full visibility**: every incident has a timeline showing what happened and why.
- **Dashboard** to follow incidents, read reports and manage your Sentry and GitHub connections.

## Tech stack

| Area | Technology |
|---|---|
| Backend API | Python, FastAPI |
| Background jobs | Celery, Redis |
| AI agents | LangGraph, LangChain (Groq by default; OpenAI-compatible and Anthropic models supported) |
| Database and auth | Supabase (Postgres) |
| Integrations | Sentry webhooks, GitHub OAuth App |
| Dashboard | Next.js, React, Tailwind CSS |

## Project structure

```
app/               backend: API routes, agents, analysis pipeline, services, background workers
main.py            API entry point
supabase/          database migration
tests/             unit and integration tests
trueai-frontend/   Next.js dashboard
```

## Getting started

### Prerequisites

- Python 3.11+ and Node.js 20+
- Docker (for Redis)
- A [Supabase](https://supabase.com) project
- A [Groq](https://console.groq.com) API key (or another supported model provider)
- A [GitHub OAuth App](https://github.com/settings/developers) with the callback URL
  `http://localhost:8000/auth/github/callback`

### 1. Backend

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # fill in the values marked (required)
```

### 2. Database

Run [`supabase/migrations/20260929000000_trueai_v2.sql`](supabase/migrations/20260929000000_trueai_v2.sql) in the
Supabase SQL editor, or with the Supabase CLI:

```bash
npx supabase link --project-ref <your-project-ref>
npx supabase db push
```

### 3. Run the services

```bash
docker run -d --name trueai-redis -p 6379:6379 redis:7-alpine

uvicorn main:app --reload --port 8000                          # API
celery -A app.workers.celery_app worker --loglevel=info        # worker (add --pool=solo on Windows)
celery -A app.workers.celery_app beat --loglevel=info          # scheduled jobs
```

### 4. Dashboard

```bash
cd trueai-frontend
cp .env.local.example .env.local     # Supabase URL and anon key, API URL
npm install
npm run dev                          # http://localhost:3000
```

### 5. Connect Sentry and GitHub

Sign up in the dashboard and follow the setup steps: connect GitHub, choose a repository, and create your webhook URL.
Then, in Sentry, create an **Internal Integration** (Settings → Developer Settings → Custom Integrations), paste the
webhook URL, enable **Alert Rule Action**, and add an alert rule that sends new issues to it. The next error that
reaches Sentry will show up in your dashboard.

## Configuration

All settings are documented in [`.env.example`](.env.example). The model used by the agents can be changed with
`LLM_PROVIDER` and `LLM_MODEL`, and each agent can use its own model if needed.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -m "not integration"          # unit tests

# integration tests (Postgres, PostgREST and Redis in Docker)
docker compose -f tests/integration/docker-compose.yml -p trueai-test up -d
pytest
```

## Deployment

```bash
docker compose up --build            # API, worker, scheduler and Redis
```

The dashboard has its own [Dockerfile](trueai-frontend/Dockerfile) and can also be deployed to Vercel.

## License

MIT
