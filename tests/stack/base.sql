-- Minimal Supabase-like base (local test only)
create role anon nologin noinherit;
create role authenticated nologin noinherit;
create role service_role nologin noinherit bypassrls;
create role authenticator login password 'authpw' noinherit;
grant anon, authenticated, service_role to authenticator;
create role supabase_auth_admin login password 'authpw' superuser;
create schema if not exists auth authorization supabase_auth_admin;
grant usage on schema public to anon, authenticated, service_role;
grant usage on schema auth to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
create extension if not exists pgcrypto;
