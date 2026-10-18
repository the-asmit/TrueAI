-- ════════════════════════════════════════════════════════════════════════
-- TrueAI v2 schema
--
-- Idempotent: safe to run on a fresh project AND on an existing TrueAI v1
-- database (it only adds/relaxes; it never drops user data).
--
-- Run it in the Supabase SQL editor (or `supabase db push`) BEFORE starting
-- the v2 API and worker.
-- ════════════════════════════════════════════════════════════════════════

create extension if not exists pgcrypto;

-- ------------------------------------------------------------------------
-- Shared trigger: keep updated_at current
-- ------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ------------------------------------------------------------------------
-- Helper: drop every CHECK constraint on a table that mentions a column
-- (v1 databases may have auto-named constraints we cannot predict).
-- ------------------------------------------------------------------------
create or replace function public._trueai_drop_checks(p_table text, p_column text)
returns void
language plpgsql
set search_path = public
as $$
declare
  c record;
begin
  for c in
    select conname
    from pg_constraint
    where conrelid = format('public.%I', p_table)::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%' || p_column || '%'
  loop
    execute format('alter table public.%I drop constraint %I', p_table, c.conname);
  end loop;
end;
$$;

-- ════════════════════════════════════════════════════════════════════════
-- user_profiles
-- ════════════════════════════════════════════════════════════════════════
create table if not exists public.user_profiles (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  full_name  text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.user_profiles add column if not exists created_at timestamptz not null default now();
alter table public.user_profiles add column if not exists updated_at timestamptz not null default now();

-- ════════════════════════════════════════════════════════════════════════
-- api_keys
-- ════════════════════════════════════════════════════════════════════════
create table if not exists public.api_keys (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users (id) on delete cascade,
  api_key      text not null,                       -- HMAC-SHA256 digest, never the raw key
  key_prefix   text not null,
  name         text,
  is_active    boolean not null default true,
  last_used_at timestamptz,
  revoked_at   timestamptz,
  created_at   timestamptz not null default now()
);
alter table public.api_keys add column if not exists name text;
alter table public.api_keys add column if not exists last_used_at timestamptz;
alter table public.api_keys add column if not exists revoked_at timestamptz;
do $$
begin
  -- v1 declared api_key UNIQUE already; a second unique index would only duplicate it.
  if not exists (
    select 1 from pg_index i
    join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
    where i.indrelid = 'public.api_keys'::regclass and i.indisunique and i.indnatts = 1 and a.attname = 'api_key'
  ) then
    create unique index api_keys_api_key_uidx on public.api_keys (api_key);
  end if;
end $$;
create index if not exists api_keys_user_idx on public.api_keys (user_id, created_at desc);

-- ════════════════════════════════════════════════════════════════════════
-- github_tokens  (one GitHub connection per user; token is Fernet-encrypted)
-- ════════════════════════════════════════════════════════════════════════
create table if not exists public.github_tokens (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null unique references auth.users (id) on delete cascade,
  access_token    text not null,
  github_username text,
  github_user_id  bigint,
  scopes          text,
  repo_name       text,          -- legacy (v1); superseded by repo_mappings
  branch_name     text,          -- legacy (v1); superseded by repo_mappings
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
alter table public.github_tokens add column if not exists github_user_id bigint;
alter table public.github_tokens add column if not exists scopes text;
alter table public.github_tokens add column if not exists repo_name text;
alter table public.github_tokens add column if not exists branch_name text;
alter table public.github_tokens add column if not exists updated_at timestamptz not null default now();
do $$
begin
  -- v1 already enforces uniqueness on user_id (its upserts rely on it); add it only when missing.
  if not exists (
    select 1 from pg_index i
    join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
    where i.indrelid = 'public.github_tokens'::regclass and i.indisunique and i.indnatts = 1 and a.attname = 'user_id'
  ) then
    create unique index github_tokens_user_uidx on public.github_tokens (user_id);
  end if;
end $$;

-- ════════════════════════════════════════════════════════════════════════
-- repo_mappings  (Sentry project → repository; NULL project = default)
-- ════════════════════════════════════════════════════════════════════════
create table if not exists public.repo_mappings (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users (id) on delete cascade,
  sentry_project text,
  repo_full_name text not null check (repo_full_name ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
  branch         text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create unique index if not exists repo_mappings_user_project_uidx
  on public.repo_mappings (user_id, coalesce(sentry_project, ''));

-- Carry v1 repository selections over as each user's default mapping.
insert into public.repo_mappings (user_id, sentry_project, repo_full_name, branch)
select g.user_id, null, g.repo_name, g.branch_name
from public.github_tokens g
where g.repo_name ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'
on conflict do nothing;

-- ════════════════════════════════════════════════════════════════════════
-- sentry_integrations  (optional per-user Sentry API + webhook secret)
-- ════════════════════════════════════════════════════════════════════════
create table if not exists public.sentry_integrations (
  user_id            uuid primary key references auth.users (id) on delete cascade,
  org_slug           text,
  base_url           text not null default 'https://sentry.io',
  auth_token_enc     text,
  webhook_secret_enc text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

-- ════════════════════════════════════════════════════════════════════════
-- incidents
-- ════════════════════════════════════════════════════════════════════════
create table if not exists public.incidents (
  id                   uuid primary key default gen_random_uuid(),
  user_id              uuid not null references auth.users (id) on delete cascade,
  sentry_event_id      text,
  error_type           text,
  error_message        text,
  environment          text,
  level                text,
  platform             text,
  raw_payload          jsonb,
  status               text not null default 'queued',
  issue_classification text,
  pipeline_error       text,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);

-- v1 stored stack_trace in a column of unknown type; v2 uses jsonb.
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'incidents'
      and column_name = 'stack_trace' and data_type <> 'jsonb'
  ) then
    alter table public.incidents rename column stack_trace to stack_trace_legacy;
  end if;
end $$;

alter table public.incidents add column if not exists stack_trace       jsonb;
alter table public.incidents add column if not exists raw_payload       jsonb;
alter table public.incidents add column if not exists level             text;
alter table public.incidents add column if not exists platform          text;
alter table public.incidents add column if not exists pipeline_error    text;
alter table public.incidents add column if not exists issue_classification text;
alter table public.incidents add column if not exists updated_at        timestamptz not null default now();
alter table public.incidents add column if not exists fingerprint       text;
alter table public.incidents add column if not exists occurrence_count  integer not null default 1;
alter table public.incidents add column if not exists last_seen_at      timestamptz;
alter table public.incidents add column if not exists sentry_project    text;
alter table public.incidents add column if not exists sentry_issue_id   text;
alter table public.incidents add column if not exists sentry_issue_url  text;
alter table public.incidents add column if not exists culprit           text;
alter table public.incidents add column if not exists severity          text;
alter table public.incidents add column if not exists repo_full_name    text;
alter table public.incidents add column if not exists branch            text;
alter table public.incidents add column if not exists current_step      text;
alter table public.incidents add column if not exists confidence        double precision;
alter table public.incidents add column if not exists analysis_run      integer not null default 1;
alter table public.incidents add column if not exists attempts          integer not null default 0;
alter table public.incidents add column if not exists started_at        timestamptz;
alter table public.incidents add column if not exists completed_at      timestamptz;
alter table public.incidents add column if not exists llm_input_tokens  integer not null default 0;
alter table public.incidents add column if not exists llm_output_tokens integer not null default 0;

update public.incidents set last_seen_at = created_at where last_seen_at is null;

-- v1 made sentry_event_id globally UNIQUE.  v2 groups repeats itself, and a
-- delivery replayed after the grouping window must not fail on another row,
-- so the uniqueness becomes a plain per-user lookup index.
do $$
declare
  c record;
begin
  for c in
    select conname from pg_constraint
    where conrelid = 'public.incidents'::regclass and contype = 'u'
      and pg_get_constraintdef(oid) ilike '%(sentry_event_id)%'
  loop
    execute format('alter table public.incidents drop constraint %I', c.conname);
  end loop;
end $$;
create index if not exists incidents_user_event_idx on public.incidents (user_id, sentry_event_id);

-- v1 kept Sentry's exception interface ({"values": [...]}) in stack_trace and
-- stored no payload.  Keep that same data as the payload, so "Run analysis
-- again" works on old incidents ...
update public.incidents
set raw_payload = jsonb_build_object(
      'event_id', sentry_event_id,
      'environment', environment,
      'exception', case
        when jsonb_typeof(stack_trace -> 'values') = 'array' then stack_trace
        else jsonb_build_object('values', jsonb_build_array(jsonb_build_object('type', error_type, 'value', error_message)))
      end)
where raw_payload is null
  and (stack_trace is null or jsonb_typeof(stack_trace) = 'object');

-- ... and store the frame list v2 shows: the primary (last) exception's
-- application frames (all frames when none is marked in-app), crash site last.
update public.incidents i
set stack_trace = (
  with frames as (
    select fr.value as f, fr.ordinality as ord
    from jsonb_array_elements(
           case when jsonb_typeof(i.stack_trace -> 'values') = 'array' then i.stack_trace -> 'values' else '[]'::jsonb end
         ) with ordinality as ex(value, ordinality)
    cross join lateral jsonb_array_elements(
           case when jsonb_typeof(ex.value -> 'stacktrace' -> 'frames') = 'array' then ex.value -> 'stacktrace' -> 'frames' else '[]'::jsonb end
         ) with ordinality as fr(value, ordinality)
    where ex.ordinality = case when jsonb_typeof(i.stack_trace -> 'values') = 'array'
                               then jsonb_array_length(i.stack_trace -> 'values') end
      and jsonb_typeof(fr.value) = 'object'
  ),
  shown as (
    select f, ord from frames
    where f -> 'in_app' = 'true'::jsonb
       or not exists (select 1 from frames x where x.f -> 'in_app' = 'true'::jsonb)
    order by ord desc
    limit 25
  )
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'filename', f ->> 'filename',
        'function', f ->> 'function',
        'lineno', case when f ->> 'lineno' ~ '^[0-9]{1,9}$' then (f ->> 'lineno')::int end,
        'context_line', left(f ->> 'context_line', 500),
        'in_app', coalesce(f -> 'in_app' = 'true'::jsonb, false)
      ) order by ord),
    '[]'::jsonb)
  from shown
)
where jsonb_typeof(i.stack_trace) = 'object';

-- Drop v1 CHECK constraints first so the value remapping below cannot violate them.
select public._trueai_drop_checks('incidents', 'status');
select public._trueai_drop_checks('incidents', 'issue_classification');

-- v1 runs that never finished were abandoned by the old worker.  Fail them
-- explicitly: left as-is, the v2 recovery job would re-run them unasked (and
-- could open pull requests for errors nobody is looking at any more).
update public.incidents
set status = 'failed',
    pipeline_error = 'This analysis was interrupted before TrueAI was upgraded. Use "Run analysis again" to analyse it with the new agents.'
where status in ('pending', 'received', 'processing')
  and started_at is null
  and created_at < now() - interval '1 hour';

-- Map v1 statuses onto the v2 lifecycle.
update public.incidents set status = 'queued'  where status in ('pending', 'received');
update public.incidents set status = 'ignored' where status = 'duplicate';
update public.incidents set status = 'flagged' where status = 'pr_created';

update public.incidents set status = 'failed'
where status not in ('queued', 'processing', 'pr_open', 'resolved', 'flagged', 'failed', 'ignored');

alter table public.incidents
  add constraint incidents_status_check
  check (status in ('queued', 'processing', 'pr_open', 'resolved', 'flagged', 'failed', 'ignored'));

update public.incidents set issue_classification = null
where issue_classification not in ('code_bug', 'config_issue', 'infrastructure', 'data_issue', 'dependency');
alter table public.incidents
  add constraint incidents_issue_classification_check
  check (issue_classification is null
         or issue_classification in ('code_bug', 'config_issue', 'infrastructure', 'data_issue', 'dependency'));

create index if not exists incidents_user_created_idx     on public.incidents (user_id, created_at desc);
create index if not exists incidents_user_last_seen_idx   on public.incidents (user_id, last_seen_at desc nulls last);
create index if not exists incidents_user_status_idx      on public.incidents (user_id, status);
create index if not exists incidents_user_fingerprint_idx on public.incidents (user_id, fingerprint, created_at desc);
create index if not exists incidents_status_updated_idx   on public.incidents (status, updated_at);

-- ════════════════════════════════════════════════════════════════════════
-- fixes  (one analysis per incident: root cause, patch, review, remediation)
-- ════════════════════════════════════════════════════════════════════════
create table if not exists public.fixes (
  id          uuid primary key default gen_random_uuid(),
  incident_id uuid not null references public.incidents (id) on delete cascade,
  root_cause  text not null default '',
  explanation text not null default '',
  fix_diff    text,
  confidence  double precision not null default 0,
  status      text not null default 'pending',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
alter table public.fixes alter column fix_diff drop not null;
alter table public.fixes add column if not exists updated_at        timestamptz not null default now();
alter table public.fixes add column if not exists fix_confidence    double precision;
alter table public.fixes add column if not exists files_changed     jsonb not null default '[]'::jsonb;
alter table public.fixes add column if not exists summary           text;
alter table public.fixes add column if not exists rationale         text;
alter table public.fixes add column if not exists risk              text;
alter table public.fixes add column if not exists validation_passed boolean not null default false;
alter table public.fixes add column if not exists review_verdict    text;
alter table public.fixes add column if not exists review_notes      text;
alter table public.fixes add column if not exists remediation       jsonb;
alter table public.fixes add column if not exists flag_reason       text;
alter table public.fixes add column if not exists policy_violations jsonb not null default '[]'::jsonb;

select public._trueai_drop_checks('fixes', 'status');

-- v1 wrote a text placeholder instead of an empty diff for "no patch" rows.
update public.fixes set fix_diff = '' where fix_diff like '# No patch%';

update public.fixes set status = 'pending'
where status not in ('pending', 'applied', 'failed', 'rejected', 'not_applicable');

alter table public.fixes
  add constraint fixes_status_check
  check (status in ('pending', 'applied', 'failed', 'rejected', 'not_applicable'));

create index if not exists fixes_incident_idx on public.fixes (incident_id, created_at desc);

-- ════════════════════════════════════════════════════════════════════════
-- pull_requests
-- ════════════════════════════════════════════════════════════════════════
create table if not exists public.pull_requests (
  id          uuid primary key default gen_random_uuid(),
  fix_id      uuid references public.fixes (id) on delete set null,
  pr_url      text not null,
  pr_number   integer not null,
  branch_name text not null,
  status      text not null default 'open',
  created_at  timestamptz not null default now()
);
alter table public.pull_requests alter column fix_id drop not null;

-- v1 declared pull_requests.fix_id ON DELETE CASCADE, so re-analysing an
-- incident (which replaces its analysis row) deleted the record of its open
-- pull request.  The PR record must outlive the analysis that produced it.
do $$
declare
  c record;
begin
  for c in
    select conname from pg_constraint
    where conrelid = 'public.pull_requests'::regclass and contype = 'f'
      and pg_get_constraintdef(oid) ilike 'FOREIGN KEY (fix_id)%'
      and pg_get_constraintdef(oid) not ilike '%ON DELETE SET NULL%'
  loop
    execute format('alter table public.pull_requests drop constraint %I', c.conname);
  end loop;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.pull_requests'::regclass and contype = 'f'
      and pg_get_constraintdef(oid) ilike 'FOREIGN KEY (fix_id)%'
  ) then
    alter table public.pull_requests
      add constraint pull_requests_fix_id_fkey foreign key (fix_id) references public.fixes (id) on delete set null;
  end if;
end $$;
alter table public.pull_requests add column if not exists incident_id    uuid references public.incidents (id) on delete cascade;
alter table public.pull_requests add column if not exists repo_full_name text;
alter table public.pull_requests add column if not exists title          text;
alter table public.pull_requests add column if not exists merged_at      timestamptz;
alter table public.pull_requests add column if not exists closed_at      timestamptz;
alter table public.pull_requests add column if not exists last_synced_at timestamptz;
alter table public.pull_requests add column if not exists updated_at     timestamptz not null default now();

select public._trueai_drop_checks('pull_requests', 'status');

-- Link v1 PR rows to their incident and repository.
update public.pull_requests p
set incident_id = f.incident_id
from public.fixes f
where p.fix_id = f.id and p.incident_id is null;

update public.pull_requests
set repo_full_name = substring(pr_url from '^https://github\.com/([^/]+/[^/]+)/pull/')
where repo_full_name is null and pr_url ~ '^https://github\.com/[^/]+/[^/]+/pull/';

-- v1 marked "PR opened" as resolved; v2 calls that pr_open until the PR is merged.
update public.incidents i
set status = 'pr_open'
where i.status = 'resolved'
  and exists (select 1 from public.pull_requests p where p.incident_id = i.id and p.status = 'open');

update public.pull_requests set status = 'open' where status not in ('open', 'merged', 'closed');

alter table public.pull_requests
  add constraint pull_requests_status_check
  check (status in ('open', 'merged', 'closed'));

create index if not exists pull_requests_incident_idx on public.pull_requests (incident_id, created_at desc);
create index if not exists pull_requests_fix_idx      on public.pull_requests (fix_id);
create index if not exists pull_requests_open_idx     on public.pull_requests (status, last_synced_at nulls first);

-- ════════════════════════════════════════════════════════════════════════
-- pipeline_steps  (agent / tool timeline shown on the dashboard)
-- ════════════════════════════════════════════════════════════════════════
create table if not exists public.pipeline_steps (
  id            uuid primary key default gen_random_uuid(),
  incident_id   uuid not null references public.incidents (id) on delete cascade,
  user_id       uuid not null references auth.users (id) on delete cascade,
  run           integer not null default 1,
  step          text not null,
  kind          text not null default 'agent' check (kind in ('agent', 'tool', 'system')),
  status        text not null check (status in ('running', 'ok', 'warning', 'error', 'skipped')),
  summary       text,
  detail        jsonb,
  provider      text,
  model         text,
  duration_ms   integer,
  input_tokens  integer,
  output_tokens integer,
  created_at    timestamptz not null default now()
);
create index if not exists pipeline_steps_incident_idx on public.pipeline_steps (incident_id, created_at);
create index if not exists pipeline_steps_user_idx     on public.pipeline_steps (user_id);

-- ════════════════════════════════════════════════════════════════════════
-- Timestamps: v1 used "timestamp without time zone" holding UTC values.
-- Convert to timestamptz so every API response carries an explicit offset.
-- ════════════════════════════════════════════════════════════════════════
do $$
declare
  c record;
begin
  for c in
    select table_name, column_name
    from information_schema.columns
    where table_schema = 'public'
      and data_type = 'timestamp without time zone'
      and table_name in ('user_profiles', 'api_keys', 'github_tokens', 'incidents', 'fixes', 'pull_requests', 'profiles')
  loop
    execute format(
      'alter table public.%I alter column %I type timestamptz using %I at time zone ''UTC''',
      c.table_name, c.column_name, c.column_name
    );
  end loop;
end $$;

-- ════════════════════════════════════════════════════════════════════════
-- updated_at triggers
-- ════════════════════════════════════════════════════════════════════════
do $$
declare
  t text;
begin
  foreach t in array array['user_profiles', 'github_tokens', 'repo_mappings', 'sentry_integrations',
                           'incidents', 'fixes', 'pull_requests']
  loop
    execute format('drop trigger if exists %I on public.%I', t || '_set_updated_at', t);
    execute format(
      'create trigger %I before update on public.%I for each row execute function public.set_updated_at()',
      t || '_set_updated_at', t
    );
  end loop;
end $$;

-- ════════════════════════════════════════════════════════════════════════
-- RPCs (service role only — they take a user id as a parameter)
-- ════════════════════════════════════════════════════════════════════════
create or replace function public.increment_incident_occurrence(
  p_incident_id uuid,
  p_user_id uuid,
  p_seen_at timestamptz
)
returns integer
language sql
set search_path = public
as $$
  update public.incidents
  set occurrence_count = occurrence_count + 1,
      last_seen_at     = greatest(coalesce(last_seen_at, p_seen_at), p_seen_at)
  where id = p_incident_id and user_id = p_user_id
  returning occurrence_count;
$$;

create or replace function public.incident_status_counts(p_user_id uuid)
returns table (status text, count bigint)
language sql
stable
set search_path = public
as $$
  select i.status, count(*)::bigint
  from public.incidents i
  where i.user_id = p_user_id
  group by i.status;
$$;

revoke all on function public.increment_incident_occurrence(uuid, uuid, timestamptz) from public, anon, authenticated;
revoke all on function public.incident_status_counts(uuid) from public, anon, authenticated;
grant execute on function public.increment_incident_occurrence(uuid, uuid, timestamptz) to service_role;
grant execute on function public.incident_status_counts(uuid) to service_role;

-- v1's signup trigger function runs as SECURITY DEFINER.  Pin its search_path
-- so objects in other schemas can never shadow the ones it uses, and stop it
-- being callable over the REST API (/rpc/handle_new_user): a trigger does not
-- need EXECUTE to fire.
do $$
begin
  if to_regprocedure('public.handle_new_user()') is not null then
    execute 'alter function public.handle_new_user() set search_path = public';
    execute 'revoke execute on function public.handle_new_user() from public, anon, authenticated';
  end if;
end $$;

-- ════════════════════════════════════════════════════════════════════════
-- Row Level Security
--
-- The API uses the service role (bypasses RLS) and filters by user itself.
-- Users never read these tables directly: the dashboard reads everything
-- through the TrueAI API, which returns only what a user should see (the
-- internal run record, models and token usage stay server-side).  So RLS is
-- on everywhere with NO user policies, and the browser-facing roles have no
-- table privileges at all.
-- ════════════════════════════════════════════════════════════════════════
alter table public.user_profiles       enable row level security;
alter table public.api_keys            enable row level security;
alter table public.github_tokens       enable row level security;
alter table public.repo_mappings       enable row level security;
alter table public.sentry_integrations enable row level security;
alter table public.incidents           enable row level security;
alter table public.fixes               enable row level security;
alter table public.pull_requests       enable row level security;
alter table public.pipeline_steps      enable row level security;

do $$
begin
  if to_regclass('public.profiles') is not null then
    execute 'alter table public.profiles enable row level security';
    execute 'drop policy if exists "profiles: read own" on public.profiles';
  end if;
end $$;

-- v1 created FOR ALL policies for every role (reads AND writes through the
-- public REST API, secrets tables included).  All v2 writes go through the
-- TrueAI API.
drop policy if exists "users_own_profile"            on public.profiles;
drop policy if exists "Users can manage own profile" on public.user_profiles;
drop policy if exists "users_own_api_keys"           on public.api_keys;
drop policy if exists "users_own_github_tokens"      on public.github_tokens;
drop policy if exists "users_own_incidents"          on public.incidents;
drop policy if exists "users_own_fixes"              on public.fixes;
drop policy if exists "users_own_pull_requests"      on public.pull_requests;
drop policy if exists "user_profiles: insert own"    on public.user_profiles;
drop policy if exists "user_profiles: update own"    on public.user_profiles;

-- Belt and braces: the browser-facing roles cannot read or write TrueAI tables.
do $$
declare
  t text;
begin
  foreach t in array array['profiles', 'user_profiles', 'api_keys', 'github_tokens', 'repo_mappings', 'sentry_integrations',
                           'incidents', 'fixes', 'pull_requests', 'pipeline_steps']
  loop
    if to_regclass(format('public.%I', t)) is not null then
      execute format('revoke select, insert, update, delete, truncate on public.%I from anon, authenticated', t);
    end if;
  end loop;
end $$;

-- Earlier versions of this migration gave users read access to their own rows.
drop policy if exists "user_profiles: read own"  on public.user_profiles;
drop policy if exists "incidents: read own"      on public.incidents;
drop policy if exists "repo_mappings: read own"  on public.repo_mappings;
drop policy if exists "pipeline_steps: read own" on public.pipeline_steps;
drop policy if exists "fixes: read own"          on public.fixes;
drop policy if exists "pull_requests: read own"  on public.pull_requests;

-- v1 installs were told to add this; service_role bypasses RLS anyway.
drop policy if exists "service_role_full_access_incidents" on public.incidents;

-- The CHECK-constraint helper is only needed while migrating.
drop function if exists public._trueai_drop_checks(text, text);
