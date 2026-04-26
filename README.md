# TrueAI

**AI-powered incident analysis and auto-fix system.** TrueAI connects to Sentry, analyses runtime errors using Claude (Anthropic), fetches the relevant source code from GitHub, generates a code fix, and opens a pull request — fully automated.

---

## How It Works

```
Client App
    │
    ▼
  Sentry (error captured)
    │
    ▼ webhook (POST /webhook/sentry?key=<api_key_prefix>)
    │
  FastAPI
    │
    ├─ Authenticates request via API key prefix
    ├─ Enqueues job to Redis
    │
    ▼
  Celery Worker
    │
    ▼
  LangGraph Pipeline
    │
    ├─ parser_node       → normalise Sentry payload
    ├─ dedup_node        → skip duplicate events (Redis SET NX)
    ├─ classifier_node   → classify error type (Claude)
    ├─ context_node      → fetch source files from GitHub
    ├─ root_cause_node   → identify root cause (Claude)
    ├─ fix_generator_node → generate unified diff patch (Claude)
    ├─ validator_node    → validate patch (Claude)
    ├─ decision_node     → create_pr or flag_for_review
    └─ pr_creator_node   → apply diff + open GitHub PR
    │
    ▼
  GitHub Pull Request created
    │
    ▼
  Supabase (incident, fix, PR records persisted)
    │
    ▼
  Dashboard (query incidents + PRs via REST API)
```

---

## Tech Stack

| Component | Technology |
|---|---|
| API server | FastAPI (Python 3.11+) |
| Task queue | Celery |
| Broker / dedup cache | Redis |
| AI orchestration | LangGraph |
| LLM | Claude 3.5 Sonnet (Anthropic) |
| GitHub integration | PyGithub |
| Database | Supabase (PostgreSQL) |
| Schema validation | Pydantic v2 |
| Auth | Supabase JWT + HMAC-signed API keys |

---

## Project Structure

```
TrueAI/
├── main.py                          # FastAPI entry point
├── requirements.txt                 # Python dependencies
├── .env                             # Environment variables (never commit)
├── .gitignore
├── README.md
├── logs/
│   └── .gitkeep
├── app/
│   ├── api/
│   │   ├── dependencies.py          # Shared FastAPI dependencies (JWT, API key auth)
│   │   └── routes/
│   │       ├── auth.py              # Auth routes: API keys, GitHub OAuth, repo selection
│   │       ├── incidents.py         # Incident query routes
│   │       └── webhook.py           # POST /webhook/sentry
│   ├── auth/
│   │   ├── api_keys.py              # HMAC-SHA256 key generation, hashing, masking
│   │   └── jwt.py                   # Supabase JWT verification
│   ├── core/
│   │   ├── config.py                # Pydantic-settings config loader
│   │   ├── graph.py                 # LangGraph pipeline graph definition
│   │   ├── llm.py                   # Anthropic Claude client singleton
│   │   ├── logging.py               # Structured logger with sensitive data masking
│   │   └── state.py                 # IncidentState TypedDict + make_initial_state
│   ├── nodes/
│   │   ├── parser.py                # Parse and normalise Sentry webhook payload
│   │   ├── dedup.py                 # Redis-based duplicate event detection
│   │   ├── classifier.py            # Classify error type with Claude
│   │   ├── context.py               # Fetch GitHub source files for stack frames
│   │   ├── root_cause.py            # Root cause analysis with Claude
│   │   ├── fix_generator.py         # Generate unified diff patch with Claude
│   │   ├── validator.py             # Two-stage patch validation (syntax + Claude)
│   │   ├── decision.py              # Decide: create_pr or flag_for_review
│   │   └── pr_creator.py            # Apply diff + open GitHub PR
│   ├── pipelines/
│   │   └── incident_pipeline.py     # Pipeline entry point called by Celery
│   ├── schemas/
│   │   ├── webhook.py               # Sentry webhook Pydantic models
│   │   ├── incident.py              # Incident Pydantic models
│   │   ├── fix.py                   # Fix + PR Pydantic models + confidence thresholds
│   │   └── github.py                # GitHub file context + PR request models
│   ├── services/
│   │   ├── supabase.py              # Supabase client + all DB helper functions
│   │   ├── redis.py                 # Redis client + dedup + cache helpers
│   │   └── github/
│   │       ├── client.py            # PyGithub wrappers
│   │       ├── fetcher.py           # Fetch + slice source files from GitHub
│   │       └── pr.py                # PR creation helpers
│   └── workers/
│       ├── celery_app.py            # Celery app initialisation
│       └── tasks.py                 # Celery task: process_incident
└── tests/
    ├── test_webhook.py
    ├── test_nodes.py
    ├── test_github.py
    └── test_pipeline.py
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-org/trueai.git
cd trueai
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the template and fill in all values:

```bash
cp .env.example .env
```

See the [Environment Variables](#environment-variables) section below for a full description of every key.

### 5. Run Redis locally

```bash
# Docker (recommended)
docker run -d -p 6379:6379 redis:7-alpine

# Or via Homebrew (macOS)
brew services start redis
```

### 6. Run the FastAPI server

```bash
uvicorn app.main:app --reload --port 8000
```

### 7. Run the Celery worker

```bash
celery -A app.workers.tasks worker --loglevel=info
```

---

## Environment Variables

Create a `.env` file at the project root with the following keys:

| Variable | Required | Description |
|---|---|---|
| `BASE_URL` | ✅ | Public base URL of the TrueAI server, e.g. `https://trueai.example.com`. Used to construct OAuth callback URLs and webhook URLs. |
| `API_KEY_SECRET` | ✅ | Secret used to HMAC-sign API keys and OAuth state tokens. Use a cryptographically random 32+ char string. Never expose. |
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API key for Claude. Obtain from [console.anthropic.com](https://console.anthropic.com). |
| `SUPABASE_URL` | ✅ | Your Supabase project URL, e.g. `https://xyzxyz.supabase.co`. |
| `SUPABASE_ANON_KEY` | ✅ | Supabase anonymous/public key. Used for client-side auth flows. |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Supabase service-role key. Bypasses RLS — used server-side only. Never expose to clients. |
| `SUPABASE_JWT_SECRET` | ✅ | JWT secret from Supabase project settings. Used to verify Supabase-issued JWTs on authenticated routes. |
| `REDIS_URL` | ✅ | Redis connection URL, e.g. `redis://localhost:6379/0`. |
| `CELERY_BROKER_URL` | ✅ | Celery broker URL (typically same as `REDIS_URL`), e.g. `redis://localhost:6379/0`. |
| `CELERY_RESULT_BACKEND` | ✅ | Celery result backend URL, e.g. `redis://localhost:6379/1`. |
| `GITHUB_CLIENT_ID` | ✅ | GitHub OAuth App client ID. Create an OAuth App in GitHub Developer Settings. |
| `GITHUB_CLIENT_SECRET` | ✅ | GitHub OAuth App client secret. Never expose. |

**Example `.env`:**

```env
BASE_URL=https://trueai.example.com
API_KEY_SECRET=your-random-secret-here

ANTHROPIC_API_KEY=sk-ant-...

SUPABASE_URL=https://xyzxyz.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_JWT_SECRET=your-jwt-secret

REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

GITHUB_CLIENT_ID=Iv1.abc123
GITHUB_CLIENT_SECRET=abc123secret
```

---

## API Endpoints

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/api-keys` | JWT | Generate a new API key. Raw key returned once only. |
| `DELETE` | `/auth/api-keys/{key_id}` | JWT | Revoke an API key (soft-delete, sets `is_active=false`). |
| `GET` | `/auth/github/authorize` | JWT | Start GitHub OAuth flow. Returns `auth_url` to redirect browser to. |
| `GET` | `/auth/github/callback` | None (OAuth) | GitHub OAuth callback. Exchanges code for token, stores it, redirects to frontend. |
| `POST` | `/auth/github/repo` | JWT | Set the GitHub repository TrueAI will open PRs against. Body: `{"repo_name": "owner/repo"}`. |
| `GET` | `/auth/user/webhook-url` | JWT | Returns the user's personalised Sentry webhook URL (uses key prefix, never full key). |
| `GET` | `/auth/me` | JWT | Returns user info: `user_id`, `github_connected`, `github_username`, `github_repo`. |

### Webhooks

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/webhook/sentry` | API key (`?key=<prefix>`) | Sentry webhook entry point. Validates key, enqueues pipeline. |

### Incidents

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/incidents` | JWT or API key | List incidents for the authenticated user. |
| `GET` | `/incidents/{incident_id}` | JWT or API key | Get a single incident with its fix and PR details. |

---

## Pipeline — Step by Step

1. **Webhook received** (`POST /webhook/sentry?key=<prefix>`)
   - API key authenticated via prefix → full key hash looked up in `api_keys` table
   - Raw payload stored; Celery task enqueued

2. **`parser_node`**
   - Validates payload against `SentryWebhookPayload` Pydantic model
   - Extracts `error_type`, `error_message`, in-app stack frames, Sentry context
   - Fails fast if no user-code frames found

3. **`dedup_node`**
   - Checks Redis for `event_id` using atomic `SET NX EX 86400`
   - Duplicate → sets `status="duplicate"`, pipeline exits
   - Fail-open: Redis unavailable → continue processing

4. **`classifier_node`**
   - Sends error details to Claude
   - Returns one of: `code_bug`, `config_issue`, `infrastructure`, `data_issue`, `dependency`
   - Soft-fail: defaults to `code_bug` on any error

5. **`context_node`**
   - Fetches GitHub access token + repo from Supabase
   - For each in-app stack frame (up to 5 files): fetches source file via PyGithub
   - Extracts ±30-line window around the error line
   - Hard-fail only if ALL file fetches fail

6. **`root_cause_node`**
   - Sends all evidence (frames, source code, Sentry context) to Claude
   - Extracts `root_cause`, `explanation`, `confidence` from XML-tagged response
   - Confidence < 0.40 → sets `action="flag_for_review"` early
   - Any missing field → `status="failed"`

7. **`fix_generator_node`**
   - `config_issue` or `infrastructure` → skip LLM, set `action="flag_for_review"`
   - Otherwise: sends root cause + source code to Claude
   - Extracts unified diff patch and list of changed files
   - Any missing field → `status="failed"`

8. **`validator_node`**
   - Stage 1: structural diff syntax check (no LLM)
   - Stage 2: Claude semantic review — `is_valid`, `critique`, `updated_confidence`
   - On pass: persists fix to `fixes` table, stores `fix_id` in state
   - Never sets `status="failed"` — validation failure routes to `flag_for_review`

9. **`decision_node`**
   - `confidence >= 0.75` AND `validation_passed=True` → `action="create_pr"`
   - Otherwise → `action="flag_for_review"`

10. **`pr_creator_node`**
    - Creates feature branch: `trueai/fix-{incident_id[:8]}`
    - Applies unified diff file-by-file using pure-Python hunk applier
    - Opens GitHub PR with structured Markdown body
    - Persists PR record to `pull_requests` table
    - Updates fix status: `applied` on success, `failed` on error

11. **Pipeline complete**
    - `action="create_pr"` → incident `status="resolved"`
    - `action="flag_for_review"` → incident `status="flagged"`
    - Unhandled exception → incident `status="failed"`

---

## Database Schema

### `profiles`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK, matches Supabase Auth user id |
| `email` | text | |
| `created_at` | timestamptz | |

### `api_keys`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `user_id` | uuid | FK → profiles.id |
| `api_key` | text | HMAC-SHA256 hash of raw key |
| `key_prefix` | text | First 12 chars of raw key, safe to display |
| `is_active` | bool | False = revoked |
| `created_at` | timestamptz | |

### `incidents`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK, generated by pipeline |
| `user_id` | uuid | FK → profiles.id |
| `sentry_event_id` | text | Sentry's own event UUID |
| `error_type` | text | e.g. `KeyError`, `NullPointerException` |
| `error_message` | text | |
| `stack_trace` | jsonb | Raw Sentry exception object |
| `environment` | text | e.g. `production`, `staging` |
| `status` | text | `pending`, `processing`, `resolved`, `flagged`, `failed`, `duplicate` |
| `created_at` | timestamptz | |

### `fixes`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `incident_id` | uuid | FK → incidents.id |
| `root_cause` | text | |
| `explanation` | text | |
| `fix_diff` | text | Unified diff patch |
| `confidence` | float | 0.0 – 1.0 |
| `status` | text | `pending`, `applied`, `failed` |
| `created_at` | timestamptz | |

### `github_tokens`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `user_id` | uuid | FK → profiles.id, unique |
| `access_token` | text | GitHub OAuth access token |
| `github_username` | text | |
| `repo_name` | text | `owner/repo` format |
| `created_at` | timestamptz | |

### `pull_requests`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `fix_id` | uuid | FK → fixes.id |
| `pr_url` | text | Full GitHub PR URL |
| `pr_number` | int | GitHub PR number |
| `branch_name` | text | e.g. `trueai/fix-a1b2c3d4` |
| `status` | text | `open`, `merged`, `closed` |
| `created_at` | timestamptz | |

---

## How to Connect as a Client

A step-by-step guide for a developer integrating TrueAI into their project.

### Step 1 — Sign up

Create an account via Supabase Auth. Use the Supabase client in your frontend:

```js
const { data, error } = await supabase.auth.signUp({ email, password })
```

### Step 2 — Generate an API key

```http
POST /auth/api-keys
Authorization: Bearer <supabase_jwt>
```

Response:
```json
{
  "id": "uuid",
  "raw_key": "tai_xxxxxxxxxxxx...",
  "key_prefix": "tai_xxxx",
  "message": "Store this key immediately — it will not be shown again."
}
```

Store `raw_key` securely. It is shown **once only**.

### Step 3 — Connect GitHub

```http
GET /auth/github/authorize
Authorization: Bearer <supabase_jwt>
```

Response:
```json
{ "auth_url": "https://github.com/login/oauth/authorize?..." }
```

Redirect your browser to `auth_url`. After authorising, GitHub redirects back to TrueAI and the token is stored automatically.

### Step 4 — Set your repository

```http
POST /auth/github/repo
Authorization: Bearer <supabase_jwt>
Content-Type: application/json

{ "repo_name": "your-org/your-repo" }
```

### Step 5 — Get your webhook URL

```http
GET /auth/user/webhook-url
Authorization: Bearer <supabase_jwt>
```

Response:
```json
{
  "webhook_url": "https://trueai.example.com/webhook/sentry?key=tai_xxxx...",
  "key_prefix": "tai_xxxx"
}
```

### Step 6 — Add to Sentry

1. Go to your Sentry project → **Settings → Integrations → Webhooks**
2. Add the `webhook_url` from Step 5
3. Select events: **Issue Created** (and optionally **Issue Resolved**)
4. Save

TrueAI will now receive every new error from your Sentry project and attempt to auto-fix it.

---

## Current Limitations

- **No branch configuration** — base branch is hardcoded to `main`. Repos using `master` or another default branch will fail PR creation.
- **Single repo per user** — each GitHub account can only target one repository at a time. Multi-repo support requires schema changes.
- **No PR merge tracking** — `pull_requests.status` is set to `open` and never updated. Merge webhooks from GitHub are not implemented.
- **No rate limit handling for Anthropic** — if the Claude API returns 429, the pipeline fails. No retry logic with backoff is implemented at the LLM layer.
- **Stack trace column is raw JSON** — `incidents.stack_trace` stores the raw Sentry exception object. Full-text search or structured queries require additional indexing.
- **Celery task retry not configured** — failed pipeline tasks are not automatically retried. Manual re-triggering requires a new webhook event from Sentry.
- **No webhook signature verification** — Sentry supports sending a `sentry-hook-signature` header. TrueAI does not currently verify it (relies on API key auth only).
- **No multitenancy isolation at DB layer** — Row Level Security (RLS) is bypassed via the service-role key. API-layer isolation is enforced, but a misconfigured route could leak data.

---

## Future Improvements

- [ ] **Branch configuration** — allow users to set a default base branch per repo
- [ ] **Multi-repo support** — store multiple repos per user; route incidents to the correct repo by project/DSN
- [ ] **GitHub webhook for PR merge tracking** — update `pull_requests.status` when PRs are merged or closed
- [ ] **Anthropic retry with exponential backoff** — handle 429/503 from Claude gracefully
- [ ] **Sentry webhook signature verification** — validate `sentry-hook-signature` on every inbound request
- [ ] **RLS enforcement** — move tenant isolation into Supabase RLS policies and use the anon key for row-scoped queries
- [ ] **Celery retry policy** — auto-retry transient failures (network errors, rate limits) with configurable backoff
- [ ] **Dashboard UI** — React frontend for viewing incidents, fixes, PR status, and confidence scores
- [ ] **Slack / PagerDuty notifications** — alert on `status="flagged"` incidents that need human review
- [ ] **Confidence calibration** — collect feedback on merged vs. closed PRs to fine-tune confidence thresholds
- [ ] **Support for JavaScript / TypeScript repos** — extend diff application and GitHub context fetching to handle source maps

---

## License

MIT
