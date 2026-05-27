# TrueAI

**AI-powered incident analysis and auto-fix system.** TrueAI connects to Sentry, analyses runtime errors using Groq (LLaMA 3.3 70B), fetches the relevant source code from GitHub, generates a code fix, and opens a pull request — fully automated. A Next.js dashboard lets you monitor incidents, view root cause analysis, and track generated fixes in real time.

---

## How It Works

```
Client App
    │
    ▼
  Sentry (error captured)
    │
    ▼ webhook (POST /webhook/sentry?key=<full_api_key>)
    │
  FastAPI
    │
    ├─ Verifies HMAC-SHA256 webhook signature (sentry-hook-signature header)
    ├─ Authenticates request via API key lookup
    ├─ Rate limits per API key (20 req/min by default)
    ├─ Enqueues job to Celery via Redis
    │
    ▼
  Celery Worker
    │
    ▼
  LangGraph Pipeline
    │
    ├─ parser_node        → normalise Sentry payload
    ├─ dedup_node         → skip duplicate events (Redis SET NX)
    ├─ classifier_node    → classify error type (Groq LLaMA)
    ├─ context_node       → fetch source files from GitHub
    ├─ root_cause_node    → identify root cause (Groq LLaMA)
    ├─ fix_generator_node → generate unified diff patch (Groq LLaMA)
    ├─ validator_node     → validate patch (Groq LLaMA)
    ├─ decision_node      → create_pr or flag_for_review
    └─ pr_creator_node    → apply diff + open GitHub PR
    │
    ▼
  GitHub Pull Request created
    │
    ▼
  Supabase (incident, fix, PR records persisted)
    │
    ▼
  Next.js Dashboard (view incidents, fixes, PR status, flagged guidance)
```

---

## Tech Stack

| Component | Technology |
|---|---|
| API server | FastAPI (Python 3.11+) |
| Task queue | Celery with exponential-backoff retry |
| Broker / dedup cache | Redis |
| AI orchestration | LangGraph |
| LLM | Groq — LLaMA 3.3 70B Versatile |
| LLM resilience | Tenacity retry with exponential backoff (429/502/503) |
| GitHub integration | PyGithub |
| Token encryption | Fernet symmetric encryption (cryptography library) |
| Database | Supabase (PostgreSQL) |
| Schema validation | Pydantic v2 |
| Auth | Supabase JWT (ES256 / ECDSA P-256 via hardcoded public JWK — no network call) + HMAC-SHA256 API keys + Sentry webhook HMAC-SHA256 signature |
| Frontend | Next.js 14 (App Router) + Supabase Auth |

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
├── trueai-frontend/                 # Next.js dashboard (separate package)
├── app/
│   ├── api/
│   │   ├── dependencies.py          # Shared FastAPI dependencies (JWT, API key auth)
│   │   └── routes/
│   │       ├── auth.py              # Auth routes: API keys, GitHub OAuth, repo/branch selection, profile, account deletion
│   │       ├── incidents.py         # Incident CRUD routes: list, get, update, fix, PR sub-resources
│   │       └── webhook.py           # POST /webhook/sentry (HMAC sig verify + rate limit)
│   ├── auth/
│   │   ├── api_keys.py              # HMAC-SHA256 key generation, hashing, masking
│   │   └── jwt.py                   # Supabase JWT verification (ES256 / ECDSA P-256 via hardcoded public JWK); rejects service_role tokens
│   ├── core/
│   │   ├── config.py                # Pydantic-settings config loader
│   │   ├── graph.py                 # LangGraph pipeline graph definition
│   │   ├── llm.py                   # Groq LLaMA client singleton + retry wrapper
│   │   ├── logging.py               # Structured logger with sensitive data masking
│   │   └── state.py                 # IncidentState TypedDict + make_initial_state
│   ├── nodes/
│   │   ├── parser.py                # Parse and normalise Sentry webhook payload
│   │   ├── dedup.py                 # Redis-based duplicate event detection
│   │   ├── classifier.py            # Classify error type with Groq LLaMA
│   │   ├── context.py               # Fetch GitHub source files for stack frames
│   │   ├── root_cause.py            # Root cause analysis with Groq LLaMA
│   │   ├── fix_generator.py         # Generate unified diff patch with Groq LLaMA; persists manual guidance for flagged incidents
│   │   ├── validator.py             # Two-stage patch validation (syntax + Groq LLaMA)
│   │   ├── decision.py              # Decide: create_pr or flag_for_review
│   │   └── pr_creator.py            # Apply diff + open GitHub PR
│   ├── pipelines/
│   │   └── incident_pipeline.py     # Pipeline entry point called by Celery
│   ├── schemas/
│   │   ├── fix.py                   # Fix + PR Pydantic models + confidence thresholds
│   │   ├── github.py                # GitHub file context + PR request models
│   │   ├── incident.py              # Incident Pydantic models (status enum, list/response schemas)
│   │   └── webhook.py               # Sentry webhook Pydantic models
│   ├── services/
│   │   ├── crypto.py                # Fernet encrypt/decrypt for GitHub OAuth tokens
│   │   ├── redis.py                 # Redis client + dedup + cache helpers
│   │   ├── sentry.py                # Sentry REST API client — fetches full event by event_id (parser fallback)
│   │   ├── supabase.py              # Supabase client + all DB helper functions
│   │   └── github/
│   │       ├── client.py            # PyGithub wrappers + dynamic default branch resolver
│   │       ├── fetcher.py           # Fetch + slice source files from GitHub
│   │       └── pr.py                # PR creation helpers
│   └── workers/
│       ├── celery_app.py            # Celery app initialisation
│       └── tasks.py                 # Celery task: process_incident (with retry policy)
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
git clone https://github.com/the-asmit/trueai.git
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

### 5. Configure Supabase RLS

The `incidents` table requires a service-role policy to allow server-side inserts. Run this in the **Supabase SQL Editor**:

```sql
CREATE POLICY "service_role_full_access_incidents" ON public.incidents
FOR ALL TO service_role USING (true) WITH CHECK (true);
```

> **Note:** TrueAI uses the service-role key for all server-side DB operations. Without this policy, incident row inserts will be rejected by RLS and the pipeline will fail silently.

### 6. Run Redis locally

```bash
# Docker (recommended)
docker run -d -p 6379:6379 redis:7-alpine

# Or via Homebrew (macOS)
brew services start redis
```

### 7. Run the FastAPI server

```bash
uvicorn main:app --reload --port 8000
```

### 8. Run the Celery worker

```bash
celery -A app.workers.tasks worker --loglevel=info
```

---

## Environment Variables

Create a `.env` file at the project root with the following keys:

| Variable | Required | Description |
|---|---|---|
| `BASE_URL` | ✅ | Public base URL of the TrueAI server, e.g. `https://trueai.example.com`. Used to construct OAuth callback URLs and webhook URLs. |
| `ENV` | ✅ | Deployment environment. Set to `production` to disable OpenAPI docs (`/docs`, `/redoc`) and enforce `SENTRY_WEBHOOK_SECRET`. Defaults to `development`. |
| `API_KEY_SECRET` | ✅ | Secret used to HMAC-SHA256-sign API keys and OAuth state tokens. Must be a cryptographically random 32+ char string. Generate with: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Never expose. |
| `CORS_ORIGINS` | ✅ | Comma-separated list of allowed frontend origins. e.g. `https://app.trueai.com,http://localhost:3000`. Defaults to `http://localhost:3000` in development. |
| `GROQ_API_KEY` | ✅ | Groq API key for LLaMA 3.3 70B. Obtain from [console.groq.com](https://console.groq.com). |
| `SUPABASE_URL` | ✅ | Your Supabase project URL, e.g. `https://xyzxyz.supabase.co`. |
| `SUPABASE_ANON_KEY` | ✅ | Supabase anonymous/public key. Used for client-side auth flows. |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Supabase service-role key. Bypasses RLS — used server-side only. Never expose to clients. |
| `REDIS_URL` | ✅ | Redis connection URL, e.g. `redis://localhost:6379/0`. |
| `CELERY_BROKER_URL` | ✅ | Celery broker URL (typically same as `REDIS_URL`). |
| `CELERY_RESULT_BACKEND` | ✅ | Celery result backend URL, e.g. `redis://localhost:6379/1`. |
| `GITHUB_CLIENT_ID` | ✅ | GitHub OAuth App client ID. Create an OAuth App in GitHub Developer Settings. |
| `GITHUB_CLIENT_SECRET` | ✅ | GitHub OAuth App client secret. Never expose. |
| `GITHUB_TOKEN_ENCRYPTION_KEY` | ✅ | Fernet symmetric key used to encrypt GitHub OAuth tokens at rest. Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SENTRY_AUTH_TOKEN` | ⚠️ Optional | Sentry API auth token. Required for the parser's Sentry API fallback when the inbound webhook carries no exception frames. |
| `SENTRY_ORG_SLUG` | ⚠️ Optional | Sentry organisation slug (e.g. `my-org`). Used to construct the Sentry REST API URL. |
| `SENTRY_WEBHOOK_SECRET` | ⚠️ Required in production | HMAC-SHA256 secret for verifying the `sentry-hook-signature` header. App refuses to start with `ENV=production` if not set. Get it from Sentry → Settings → Integrations → Webhooks → Signing Secret. |
| `RATE_LIMIT_PER_MINUTE` | ⚠️ Optional | Maximum webhook requests per API key per minute. Defaults to `20`. |

**Example `.env`:**

```env
# APP
BASE_URL=https://trueai.example.com
ENV=production
API_KEY_SECRET=<48-byte random string>
CORS_ORIGINS=https://app.trueai.com

# LLM
GROQ_API_KEY=gsk_...

# SUPABASE
SUPABASE_URL=https://xyzxyz.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# REDIS / CELERY
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# GITHUB
GITHUB_CLIENT_ID=Iv1.abc123
GITHUB_CLIENT_SECRET=abc123secret
GITHUB_TOKEN_ENCRYPTION_KEY=<base64-fernet-key>

# SENTRY
SENTRY_AUTH_TOKEN=sntrys_...
SENTRY_ORG_SLUG=my-org
SENTRY_WEBHOOK_SECRET=<sentry-signing-secret>
RATE_LIMIT_PER_MINUTE=20
```

---

## Security

TrueAI is built with production security in mind:

- **API key storage** — raw keys are never stored. Only the HMAC-SHA256 digest is persisted. Constant-time comparison (`hmac.compare_digest`) prevents timing attacks.
- **JWT verification** — ES256 / ECDSA P-256 signature verification using Supabase's public JWK. No shared secrets. Algorithm confusion attacks (HS256, `alg: none`) are explicitly rejected.
- **GitHub token encryption** — OAuth access tokens are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256) before being stored in Supabase.
- **OAuth state** — CSRF-resistant: state is a Base64-encoded JSON blob signed with HMAC-SHA256 (128-bit signature) and has a 15-minute expiry.
- **Webhook signature** — Sentry webhook payloads are verified with HMAC-SHA256 using `sentry-hook-signature`. Required in production; app refuses to start without it.
- **CORS** — restricted to explicit origins via `CORS_ORIGINS` env var. Wildcard `*` is never used.
- **Log redaction** — `SensitiveDataFilter` strips API keys, JWTs, GitHub tokens, and Supabase keys from all log output before they reach the console or log files.
- **Error responses** — all unhandled exceptions return generic 500 messages. No stack traces, file paths, or internal error details are ever sent to clients.
- **OpenAPI docs** — `/docs`, `/redoc`, and `/openapi.json` are disabled when `ENV=production`.

---

## Quick Test

Once the server and worker are running, verify the pipeline end-to-end:

```bash
curl -X POST "http://localhost:8000/webhook/sentry?key=<your_full_api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-event-001",
    "event_id": "test-event-001",
    "project": "my-project",
    "environment": "production",
    "exception": {
      "values": [
        {
          "type": "KeyError",
          "value": "'\''user_id'\'' not found in session",
          "stacktrace": {
            "frames": [
              {
                "filename": "app/views/dashboard.py",
                "lineno": 42,
                "function": "get_dashboard",
                "in_app": true,
                "context_line": "    user = session['\''user_id'\'']"
              }
            ]
          }
        }
      ]
    }
  }'
```

Expected response (`HTTP 202`):
```json
{ "accepted": true, "event_id": "test-event-001", "task_id": "<celery-task-uuid>" }
```

The Celery worker processes the incident asynchronously. Query the result:

```bash
curl "http://localhost:8000/incidents/<incident_id>" \
  -H "Authorization: Bearer <supabase_jwt>"
```

> **Note:** Each `event_id` is deduplicated via Redis. Re-sending the same test payload is silently skipped. Use a unique `event_id` for each test.

---

## API Endpoints

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/api-keys` | JWT | Generate a new API key. Raw key returned once only. |
| `DELETE` | `/auth/api-keys/{key_id}` | JWT | Revoke an API key (soft-delete, sets `is_active=false`). |
| `POST` | `/auth/profile` | JWT | Save user profile info. Body: `{"full_name": "..."}`. |
| `GET` | `/auth/github/authorize` | JWT | Start GitHub OAuth flow. Returns `auth_url` to redirect browser to. |
| `GET` | `/auth/github/callback` | None (OAuth) | GitHub OAuth callback. Exchanges code for token, encrypts and stores it, redirects to frontend. |
| `POST` | `/auth/github/repo` | JWT | Set the GitHub repository TrueAI will open PRs against. Body: `{"repo_name": "owner/repo"}`. |
| `POST` | `/auth/github/branch` | JWT | Set the production branch for the connected repo. Body: `{"branch_name": "main"}`. |
| `GET` | `/auth/user/webhook-url` | JWT | Returns the user's personalised Sentry webhook URL (uses key prefix, never full key). |
| `GET` | `/auth/me` | JWT | Returns user info: `user_id`, `full_name`, `github_connected`, `github_username`, `github_repo`, `github_branch`. |
| `DELETE` | `/auth/account` | JWT | Permanently delete the authenticated user's account and all associated data. Irreversible. |

### Webhooks

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/webhook/sentry` | API key (`?key=<full_api_key>`) + HMAC signature | Sentry webhook entry point. Verifies signature, validates key, enforces rate limit, enqueues pipeline. |

### Incidents

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/incidents` | JWT or API key | List incidents for the authenticated user. Supports `?status=`, `?classification=`, `?page=`, `?page_size=` filters. |
| `GET` | `/incidents/{incident_id}` | JWT or API key | Get a single incident record. |
| `PATCH` | `/incidents/{incident_id}` | JWT or API key | Partially update an incident's `status`, `issue_classification`, or `pipeline_error`. |
| `GET` | `/incidents/{incident_id}/fix` | JWT or API key | Get the generated code fix (diff) or manual remediation guidance for an incident. |
| `GET` | `/incidents/{incident_id}/pr` | JWT or API key | Get the GitHub pull request record for an incident. |

### Health

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Liveness probe. Returns `{"status": "ok"}`. |
| `GET` | `/health/ready` | None | Readiness probe. Checks Redis + Supabase. Returns 503 if any dependency is down. |

---

## Pipeline — Step by Step

1. **Webhook received** (`POST /webhook/sentry?key=<full_api_key>`)
   - HMAC-SHA256 signature verified against `sentry-hook-signature` header
   - API key authenticated via full key hash lookup in `api_keys` table
   - Per-key rate limit enforced (default: 20 req/min)
   - Raw payload stored; Celery task enqueued; HTTP 202 returned immediately

2. **`parser_node`**
   - Validates payload against `SentryWebhookPayload` Pydantic model
   - Extracts `error_type`, `error_message`, in-app stack frames, Sentry context
   - **Sentry API fallback:** if the webhook payload carries no exception frames, fetches the full event from the Sentry API by `event_id` + `project_slug`
   - Falls back from in-app frames → all frames when `in_app` flag is absent (path heuristic)
   - Builds `frame_contexts` dict keyed by `filename:lineno` for inline source context
   - Sets `status="processing"` on success; fails fast if no frames found after fallback

3. **`dedup_node`**
   - Checks Redis for `event_id` using atomic `SET NX EX 86400`
   - Duplicate → sets `status="duplicate"`, pipeline exits immediately
   - Fail-open: Redis unavailable → continue processing

4. **`classifier_node`**
   - Sends error details to Groq LLaMA 3.3 70B
   - Returns one of: `code_bug`, `config_issue`, `infrastructure`, `data_issue`, `dependency`
   - Soft-fail: defaults to `code_bug` on any error

5. **`context_node`**
   - Fetches decrypted GitHub access token (Fernet-encrypted at rest) + repo from Supabase
   - For each in-app stack frame (up to 5 files): fetches source file via PyGithub
   - Extracts ±30-line window around the error line, annotated with line numbers
   - Each frame fetched independently — a single file failure never aborts the enrichment pass
   - **Non-fatal all-fail:** if every frame fails, continues with empty `github_context`

6. **`root_cause_node`**
   - Sends all evidence (frames, source code, Sentry context) to Groq LLaMA
   - Extracts `root_cause`, `explanation`, `confidence` from XML-tagged response
   - Confidence < 0.40 → sets `action="flag_for_review"` early
   - Any missing field → `status="failed"`

7. **`fix_generator_node`**
   - `config_issue` or `infrastructure` classification → skip LLM, set `action="flag_for_review"`, persist manual remediation guidance to `fixes` table
   - Otherwise: sends root cause + source code to Groq LLaMA
   - Extracts unified diff patch and list of changed files
   - For flagged paths: persists `root_cause`, `explanation`, `confidence=0`, `fix_diff=""` to `fixes` table so the dashboard can display guidance

8. **`validator_node`**
   - Stage 1: structural diff syntax check (no LLM, no cost)
   - Stage 2: Groq LLaMA semantic review — `is_valid`, `critique`, `updated_confidence`
   - On pass: persists fix to `fixes` table, stores `fix_id` in state
   - Validation failure routes to `flag_for_review` — never sets `status="failed"`

9. **`decision_node`**
   - `confidence >= 0.75` AND `validation_passed=True` → `action="create_pr"`
   - Otherwise → `action="flag_for_review"`

10. **`pr_creator_node`**
    - Resolves repository's actual default branch dynamically via GitHub API
    - Creates feature branch: `trueai/fix-{incident_id[:8]}`
    - Applies unified diff file-by-file using pure-Python hunk applier (no subprocess, no temp files)
    - Opens GitHub PR with structured Markdown body
    - Persists PR record to `pull_requests` table
    - Updates fix status: `applied` on success, `failed` on error

11. **Pipeline complete**
    - `action="create_pr"` → incident `status="resolved"`
    - `action="flag_for_review"` → incident `status="flagged"` (dashboard shows root cause + manual remediation guidance)
    - Unhandled exception → incident `status="failed"`

12. **Celery retry policy**
    - Transient failures (network errors, upstream 5xx) → auto-retry up to 3 times
    - Backoff: 30 s → 60 s → 120 s (exponential: `30 × 2^n`)
    - `status="failed"` or `status="duplicate"` → no retry (permanent states)

---

## Database Schema

### `profiles`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK, matches Supabase Auth user id |
| `email` | text | |
| `created_at` | timestamptz | |

### `user_profiles`
| Column | Type | Notes |
|---|---|---|
| `user_id` | uuid | PK / FK → profiles.id |
| `full_name` | text | Display name (max 100 chars); set via `POST /auth/profile` |

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
| `environment` | text | e.g. `production`, `staging` |
| `level` | text | Sentry severity level: `debug`, `info`, `warning`, `error`, `fatal` |
| `platform` | text | Runtime platform: `python`, `javascript`, etc. |
| `raw_payload` | jsonb | Complete original Sentry webhook payload for audit / re-processing |
| `status` | text | `processing`, `resolved`, `flagged`, `failed`, `duplicate` |
| `issue_classification` | text | `code_bug`, `config_issue`, `infrastructure`, `data_issue`, `dependency`, `unknown` |
| `pipeline_error` | text | Error message captured when the pipeline fails; NULL on success |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | Updated automatically on any row change |

### `fixes`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `incident_id` | uuid | FK → incidents.id |
| `root_cause` | text | |
| `explanation` | text | LLM explanation or manual remediation guidance for flagged incidents |
| `fix_diff` | text | Unified diff patch; empty string for flagged/unfixable incidents |
| `confidence` | float | 0.0 – 1.0; 0.0 for flagged incidents |
| `status` | text | `pending`, `applied`, `failed` |
| `created_at` | timestamptz | |

### `github_tokens`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `user_id` | uuid | FK → profiles.id, unique |
| `access_token` | text | GitHub OAuth token, **Fernet-encrypted at rest** |
| `github_username` | text | |
| `repo_name` | text | `owner/repo` format |
| `branch_name` | text | Production branch to target for PRs (e.g. `main`); set via `POST /auth/github/branch` |
| `created_at` | timestamptz | |

### `pull_requests`
| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `fix_id` | uuid | FK → fixes.id |
| `pr_url` | text | Full GitHub PR URL |
| `pr_number` | int | GitHub PR number |
| `branch_name` | text | e.g. `trueai/fix-a1b2c3d4` |
| `status` | text | `open`, `merged`, `closed` — set to `open` on creation |
| `created_at` | timestamptz | |

---

## How to Connect as a Client

A step-by-step guide for a developer integrating TrueAI into their project.

### Step 1 — Sign up

Create an account via Supabase Auth (through the TrueAI dashboard or directly):

```js
const { data, error } = await supabase.auth.signUp({ email, password })
```

### Step 2 — Save your profile (optional)

```http
POST /auth/profile
Authorization: Bearer <supabase_jwt>
Content-Type: application/json

{ "full_name": "Your Name" }
```

### Step 3 — Generate an API key

```http
POST /auth/api-keys
Authorization: Bearer <supabase_jwt>
```

Response:
```json
{
  "id": "uuid",
  "raw_key": "tai_xxxxxxxxxxxx...",
  "key_prefix": "tai_xxxxxxxxxxxx",
  "message": "Store this key immediately — it will not be shown again."
}
```

Store `raw_key` securely. It is shown **once only**. If the `API_KEY_SECRET` is rotated on the server, all existing keys are invalidated and must be regenerated.

### Step 4 — Connect GitHub

```http
GET /auth/github/authorize
Authorization: Bearer <supabase_jwt>
```

Response:
```json
{ "auth_url": "https://github.com/login/oauth/authorize?..." }
```

Redirect your browser to `auth_url`. After authorising, GitHub redirects back to TrueAI, and the token is encrypted and stored automatically.

### Step 5 — Set your repository

```http
POST /auth/github/repo
Authorization: Bearer <supabase_jwt>
Content-Type: application/json

{ "repo_name": "your-org/your-repo" }
```

### Step 6 — Set your production branch (optional)

```http
POST /auth/github/branch
Authorization: Bearer <supabase_jwt>
Content-Type: application/json

{ "branch_name": "main" }
```

If not set, TrueAI resolves the repository's default branch dynamically at PR creation time.

### Step 7 — Get your webhook URL

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

### Step 8 — Add to Sentry

1. Go to your Sentry project → **Settings → Legacy Integrations → Webhooks**
2. Paste the `webhook_url` from Step 7 into **Callback URLs**
3. Click **Save Changes**, then **Test Plugin** to verify the connection
4. In **Sentry → Settings → Integrations → Webhooks → Signing Secret**, copy the secret and set it as `SENTRY_WEBHOOK_SECRET` in your `.env`

TrueAI will now receive every new error from your Sentry project and attempt to auto-fix it.

---

## Current Limitations

- **Single repo per user** — each GitHub account can only target one repository at a time. Multi-repo support requires schema changes.
- **No PR merge tracking** — `pull_requests.status` is set to `open` on creation and never updated. GitHub merge webhooks are not implemented.
- **No multitenancy isolation at DB layer** — RLS is bypassed via the service-role key. Tenant isolation is enforced at the application layer (all queries filter on `user_id`), but moving this into Supabase RLS is recommended for defence-in-depth.
- **Hardcoded Supabase JWK** — the ES256 public key used for JWT verification is embedded in `app/auth/jwt.py`. Rotating the Supabase signing key requires a code change.

---

## Future Improvements

- [ ] **Multi-repo support** — store multiple repos per user; route incidents to the correct repo by project/DSN
- [ ] **GitHub webhook for PR merge tracking** — update `pull_requests.status` when PRs are merged or closed
- [ ] **RLS enforcement** — move tenant isolation into Supabase RLS policies and use the anon key for row-scoped queries
- [ ] **Slack / PagerDuty notifications** — alert on `status="flagged"` incidents that need human review
- [ ] **Confidence calibration** — collect feedback on merged vs. closed PRs to fine-tune confidence thresholds
- [ ] **Support for JavaScript / TypeScript repos** — extend diff application and GitHub context fetching to handle source maps

---

## License

MIT
