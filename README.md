# TrueAI

**Sentry reports the error. TrueAI writes the fix.**

TrueAI receives errors from Sentry, reads the code behind them at the commit you deployed, and hands each incident to a
team of five AI agents. When the root cause is clear and the change is safe, it opens a pull request for you to review.
When code isn't the fix (a database that is down, a missing environment variable), it writes the exact next steps
instead. Every decision is recorded on the incident's timeline.

```
Sentry ──webhook──▶ FastAPI ──queue──▶ Celery worker ──▶ LangGraph pipeline ──▶ GitHub pull request
                       │                                        │                        or next steps
                       └──────────── Supabase (Postgres, Auth) ◀┘
                                              ▲
                                  Next.js dashboard (trueai-frontend/)
```

---

## The agents

Each agent is a separate role with its own prompt, output contract and model. They share one model today, but any agent
can be moved to a different provider or model with environment variables alone (see [Models](#models)).

| Agent | Job | Output |
|---|---|---|
| **Triage** | Classifies the incident: code bug, configuration, infrastructure, data or dependency, plus severity. | category, severity, one-line summary |
| **Investigator** | Finds the root cause from the stack trace, the Sentry context and the source files. Can ask for more files when the evidence is incomplete (up to `MAX_INVESTIGATION_ROUNDS`). | root cause, explanation, confidence, whether code can fix it |
| **Fix Engineer** | Writes the smallest safe change as exact search/replace edits. | edits, summary, rationale, risk |
| **Reviewer** | Reviews the applied diff independently. | approve / revise (with feedback) / reject, confidence |
| **Remediation** | When no pull request is opened, writes concrete next steps for the on-call engineer. | steps, how to verify, how to prevent a repeat |

### Pipeline

```
parser ─▶ triage ─▶ context ─▶ investigator ─┬─▶ (needs more files) ─▶ context ─▶ investigator
                                              │
                                              ├─▶ fix_engineer ─▶ reviewer ─┬─▶ (revise) ─▶ fix_engineer
                                              │                             │
                                              │                             └─▶ decision ─┬─▶ pr_creator ─▶ finalize
                                              │                                           └─▶ remediation ─▶ finalize
                                              └─▶ (not fixable in code / low confidence) ─▶ remediation ─▶ finalize
```

- **Deterministic patching.** The Fix Engineer never writes a diff by hand. Its edits are applied by a patch engine
  (exact match, then whitespace-tolerant, then indentation-aware), the result is syntax-checked (Python, JSON, YAML,
  TOML) and checked against a safety policy. If an edit does not apply, the agent is told exactly why and tries again
  (up to `MAX_FIX_ATTEMPTS`).
- **Safety policy.** Edits to CI workflows, lockfiles, Dockerfiles, infrastructure-as-code and secrets are blocked, as
  are `eval`/shell execution, disabled TLS verification, embedded credentials and oversized changes.
- **Decision gates.** A pull request opens only when the root cause **and** the review both reach
  `CONFIDENCE_AUTO_PR_THRESHOLD` (default 75%), the Reviewer approved, the policy passed and the GitHub token can push.
  Otherwise the incident is marked **Needs you** with the diagnosis, the reason, and the patch as a suggestion.
- **Atomic pull requests.** All files are committed in one commit through the Git Data API, on a new branch from the
  exact commit that was analysed. TrueAI never pushes to existing branches and never merges.
- **Merge tracking.** A scheduled job (and a button on the incident) syncs pull request state; merging moves the
  incident to **Resolved**.

### Incident lifecycle

`queued` → `processing` → `pr_open` → `resolved`, or `flagged` (needs you), `failed` (can be re-run) or `ignored`.
Repeats of the same Sentry issue are grouped into one incident (by Sentry issue id, or a stack fingerprint) and counted.

---

## Security

- **Webhooks** are authenticated with a per-user API key (only an HMAC-SHA256 hash is stored) and, once the user saves
  their Sentry Client Secret, an HMAC signature check. Deliveries are size-capped, rate-limited per key and per IP, and
  de-duplicated by event id.
- **Untrusted input.** Everything that comes from Sentry or a repository is treated as data: it is fenced in the
  prompts, reserved tags are neutralised, and agents are told never to follow instructions inside it.
- **PII scrubbing.** Cookies, authorisation headers, emails, request bodies and local variables are removed before
  anything is stored or sent to a model. Logs are redacted on the way out.
- **Secrets at rest.** GitHub tokens and Sentry credentials are encrypted with Fernet; comma-separated keys in
  `GITHUB_TOKEN_ENCRYPTION_KEY` allow rotation (the first key encrypts, all keys decrypt).
- **GitHub OAuth.** Signed state, a single-use nonce, and a one-time hand-off code that the signed-in dashboard must
  redeem, so an authorisation can't be attached to someone else's account.
- **Auth.** Supabase JWTs are verified with the project's JWKS (ES256/RS256), with HS256 kept for legacy projects.
- **Outbound requests.** Sentry API hosts are allow-listed (SSRF guard). Row level security is enabled on every table.
- **Dashboard.** Per-request CSP nonce, strict security headers, open-redirect-safe `?next=` handling, and a server-only
  API client (the browser never talks to the backend directly).

---

## Tech stack

| Area | Technology |
|---|---|
| API | FastAPI, Pydantic v2 |
| Jobs | Celery + Redis (worker, and beat for scheduled jobs) |
| Agents | LangGraph, LangChain chat models (Groq by default; OpenAI-compatible and Anthropic supported) |
| Data & auth | Supabase (Postgres, Auth, RLS) |
| GitHub | OAuth App, REST + Git Data API |
| Dashboard | Next.js 16 (App Router, server components), Tailwind CSS v4, Radix |

---

## Running it locally

**Requirements:** Python 3.11+, Node 20+, Docker (for Redis), a Supabase project, a Groq API key and a GitHub OAuth App.

### 1. Backend

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # fill in the values marked (required)
```

Create a GitHub OAuth App with the callback URL `<BASE_URL>/auth/github/callback`
(`http://localhost:8000/auth/github/callback` locally).

### 2. Database

Apply [`supabase/migrations/20260929000000_trueai_v2.sql`](supabase/migrations/20260929000000_trueai_v2.sql) in the
Supabase SQL editor, or with the CLI:

```bash
npx supabase link --project-ref <your-project-ref>
npx supabase db push
```

The migration is idempotent and upgrades a v1 database in place: it keeps existing rows, maps old status values to the
new ones, converts timestamps to `timestamptz`, and adds the new tables (`repo_mappings`, `sentry_integrations`,
`pipeline_steps`), functions and RLS policies.

### 3. Start the services

```bash
docker run -d --name trueai-redis -p 6379:6379 redis:7-alpine

uvicorn main:app --reload --port 8000
celery -A app.workers.celery_app worker --loglevel=info            # add --pool=solo on Windows
celery -A app.workers.celery_app beat --loglevel=info              # PR sync + stuck-incident recovery
```

On Windows, use `127.0.0.1` rather than `localhost` in `.env` URLs; `localhost` resolution adds seconds per connection.

On startup the API checks its configuration, the encryption key, Supabase and Redis, and warns if a configured model
is not available to your API key.

### 4. Dashboard

```bash
cd trueai-frontend
cp .env.local.example .env.local     # Supabase URL + anon key, API URL
npm install
npm run dev                          # http://localhost:3000
```

Sign up, then follow the setup steps: connect GitHub, choose a repository, and create the webhook URL. In Sentry:

1. **Settings → Developer Settings → Custom Integrations** → create an **Internal Integration**.
2. Paste the URL into **Webhook URL**, turn on **Alert Rule Action**, and give **Issue & Event** read access.
3. Add an alert rule to your project: **A new issue is created** → **Send a notification via** the integration.
4. Optional: copy the integration's **Client Secret** into Integrations → Signing secret, so every delivery is verified.

Sentry's older WebHooks plugin works too (Project Settings → Legacy Integrations → WebHooks).

---

## Models

Every agent uses the `LLM_*` defaults unless it has its own override:

```env
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
LLM_FALLBACK_MODEL=qwen/qwen3.8-27b      # tried once if the primary model is unavailable

AGENT_TRIAGE_MODEL=openai/gpt-oss-20b    # a smaller model is plenty for triage
AGENT_FIX_ENGINEER_PROVIDER=openai
AGENT_FIX_ENGINEER_MODEL=gpt-4.1
AGENT_REVIEWER_PROVIDER=anthropic        # pip install langchain-anthropic
AGENT_REVIEWER_MODEL=claude-sonnet-5
```

Agents: `TRIAGE`, `INVESTIGATOR`, `FIX_ENGINEER`, `REVIEWER`, `REMEDIATION`. Each also accepts `_TEMPERATURE` and
`_MAX_TOKENS`. The model each agent runs on is shown on the incident timeline and in Settings.

All configuration is documented in [`.env.example`](.env.example).

---

## Tests

```bash
pip install -r requirements-dev.txt

pytest -m "not integration"          # unit tests, no services needed

# Integration tests run the real Supabase client against the real migration
# (Postgres + PostgREST) and a real Redis:
docker compose -f tests/integration/docker-compose.yml -p trueai-test up -d
pytest
```

Integration tests are skipped automatically when that stack is not running.

---

## Deployment

```bash
docker compose up --build            # redis, api, worker, beat
```

The API image runs as a non-root user. Behind a reverse proxy, set `TRUST_PROXY_HEADERS=true` so rate limits use the
client address, and set `ENV=production` (this also disables `/docs`). The dashboard has its own
[Dockerfile](trueai-frontend/Dockerfile) (Next.js standalone output) and deploys equally well to Vercel.

Health checks: `GET /health` (liveness) and `GET /health/ready` (Supabase + Redis).

---

## API

All routes except the webhook and GitHub callback take a Supabase JWT (`Authorization: Bearer …`). Interactive docs are
at `/docs` outside production.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/webhook/sentry?key=…` | Sentry deliveries (API key; signature when configured) |
| `GET` | `/incidents` | List, with `status`, `classification`, `q`, `page`, `page_size` |
| `GET` | `/incidents/stats` | Counts per status |
| `GET` | `/incidents/{id}` | Full report: analysis, pull request, timeline, stack trace |
| `PATCH` | `/incidents/{id}` | Resolve, ignore or reopen |
| `POST` | `/incidents/{id}/reanalyze` | Run the pipeline again |
| `POST` | `/incidents/{id}/sync-pr` | Refresh the pull request state from GitHub |
| `DELETE` | `/incidents/{id}` | Delete an incident |
| `GET` | `/auth/me` | User, setup and integration status, agent models |
| `POST` | `/auth/profile` | Save display name |
| `GET` `POST` `DELETE` | `/auth/api-keys` | List, create (raw key shown once), revoke |
| `DELETE` | `/auth/account` | Delete the account and all data; revokes the GitHub grant |
| `GET` | `/auth/github/authorize` | Start connecting GitHub |
| `POST` | `/auth/github/complete` | Attach the authorised GitHub account (one-time code) |
| `GET` | `/auth/github/repos`, `/auth/github/branches` | Repositories and branches for the pickers |
| `POST` | `/auth/github/repo`, `/auth/github/branch` | Default repository and branch |
| `DELETE` | `/auth/github` | Disconnect GitHub |
| `GET` `POST` `DELETE` | `/integrations/repositories` | Map Sentry projects to repositories |
| `GET` `PUT` `DELETE` | `/integrations/sentry` | Signing secret and Sentry API access (stored encrypted) |

---

## Project structure

```
app/
  agents/          one module per agent: prompt, output contract, parsing
  api/routes/      webhook, incidents, auth, github, integrations
  auth/            JWT verification, API keys
  core/            config, LLM routing, graph, state, security helpers, rate limits, logging
  nodes/           LangGraph nodes: parser, triage, context, investigator, fix_engineer,
                   reviewer, decision, pr_creator, remediation, finalize
  pipelines/       pipeline runner and timeline recording
  services/        Supabase, Redis, Sentry, GitHub, patch engine, encryption, PR sync
  workers/         Celery app, tasks, scheduled jobs
supabase/          migrations and local config
tests/             unit and integration tests
trueai-frontend/   Next.js dashboard
```

---

## Scope

- TrueAI works from what Sentry captures and the code in your repository. It does not read your logs, metrics or traces.
- It proposes changes; it never merges, deploys or rolls back.
- It analyses any language Sentry reports. Syntax is verified automatically for Python, JSON, YAML and TOML; for other
  languages the Reviewer Agent and your CI are the check.

## License

MIT
