-- Minimal Supabase-compatible environment for integration tests:
-- the roles and auth schema that TrueAI's migration and RLS policies expect.
-- Applied before supabase/migrations/*.sql by tests/integration/docker-compose.yml.

create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create role authenticator login password 'authenticator' noinherit;
grant anon, authenticated, service_role to authenticator;

create schema auth;
create table auth.users (
  id    uuid primary key,
  email text
);
create function auth.uid() returns uuid
language sql stable
as $$ select nullif(current_setting('request.jwt.claims', true)::json ->> 'sub', '')::uuid $$;

grant usage on schema auth to anon, authenticated, service_role;
grant select on auth.users to service_role;
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;

-- Test-only helper: create auth users through PostgREST (service role only).
create function public.test_create_user(p_id uuid, p_email text) returns void
language sql security definer set search_path = public, auth
as $$ insert into auth.users (id, email) values (p_id, p_email) on conflict do nothing $$;
revoke all on function public.test_create_user(uuid, text) from public, anon, authenticated;
grant execute on function public.test_create_user(uuid, text) to service_role;
