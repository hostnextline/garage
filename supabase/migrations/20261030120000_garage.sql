-- Garage mobile : base de données (projet Supabase à part, jamais mélangé avec un autre projet).
-- Rôles : owner (propriétaire, tout), bureau (agenda, clients, factures, carte, pas les réglages),
--         mecano (seulement ses jobs, bouton En route, facture sur place).

-- ---------- Équipe ----------
create table public.members (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  role       text not null check (role in ('owner','bureau','mecano')),
  name       text not null check (length(btrim(name)) between 1 and 60),
  mechanic   text check (mechanic is null or length(btrim(mechanic)) between 1 and 60),
  active     boolean not null default true,
  created_at timestamptz not null default now(),
  constraint mecano_needs_mechanic check (role <> 'mecano' or mechanic is not null)
);
create unique index members_mechanic_uq on public.members (lower(btrim(mechanic))) where mechanic is not null and active;
alter table public.members enable row level security;

create function public.my_role() returns text language sql stable security definer set search_path = '' as $$
  select m.role from public.members m where m.user_id = auth.uid() and m.active
$$;
create function public.my_mechanic() returns text language sql stable security definer set search_path = '' as $$
  select m.mechanic from public.members m where m.user_id = auth.uid() and m.active
$$;
create function public.is_staff() returns boolean language sql stable security definer set search_path = '' as $$
  select coalesce((select m.role in ('owner','bureau') from public.members m where m.user_id = auth.uid() and m.active), false)
$$;

create policy members_read on public.members for select to authenticated using (public.my_role() is not null);
create policy members_owner_update on public.members for update to authenticated
  using (public.my_role() = 'owner') with check (public.my_role() = 'owner');

-- the garage always keeps at least one active owner
create function public.keep_an_owner() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if (tg_op = 'DELETE' and old.role = 'owner' and old.active)
     or (tg_op = 'UPDATE' and old.role = 'owner' and old.active and (new.role <> 'owner' or not new.active)) then
    if not exists (select 1 from public.members m where m.role = 'owner' and m.active and m.user_id <> old.user_id) then
      raise exception 'Il faut garder au moins un propriétaire actif.' using errcode = 'P0001';
    end if;
  end if;
  return coalesce(new, old);
end $$;
create trigger members_keep_owner before update or delete on public.members for each row execute function public.keep_an_owner();

-- ---------- Carnet : mêmes documents que l'app (jobs, clients, days, config, meta, brouillons) ----------
create table public.docs (
  path       text primary key check (path ~ '^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)+$' and length(path) <= 300),
  col        text generated always as (regexp_replace(path, '/[^/]*$', '')) stored,
  id         text generated always as (regexp_replace(path, '^.*/', '')) stored,
  data       jsonb not null default '{}'::jsonb check (jsonb_typeof(data) = 'object'),
  mech       text generated always as (case when path like 'jobs/%' then lower(btrim(data->>'mechanic')) end) stored,
  client_id  text generated always as (case when path like 'jobs/%' then data->>'clientId' end) stored,
  updated_at timestamptz not null default clock_timestamp(),
  updated_by uuid default auth.uid(),
  constraint docs_size check (pg_column_size(data) < 400000)
);
create index docs_col_updated on public.docs (col, updated_at);
create index docs_jobs_mech on public.docs (mech) where mech is not null;
create index docs_jobs_client on public.docs (client_id) where client_id is not null;
alter table public.docs enable row level security;

create table public.docs_deleted (
  path       text not null,
  col        text not null,
  deleted_at timestamptz not null default clock_timestamp(),
  primary key (path, deleted_at)
);
create index docs_deleted_col on public.docs_deleted (col, deleted_at);
alter table public.docs_deleted enable row level security;

create function public.docs_touch() returns trigger language plpgsql set search_path = '' as $$
begin
  new.updated_at := clock_timestamp();
  new.updated_by := auth.uid();
  return new;
end $$;
create trigger docs_touch before insert or update on public.docs for each row execute function public.docs_touch();

create function public.docs_tombstone() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.docs_deleted (path, col) values (old.path, old.col);
  return old;
end $$;
create trigger docs_tombstone after delete on public.docs for each row execute function public.docs_tombstone();

-- clients a mechanic may see: the ones on his own jobs
create function public.mech_client_ids() returns setof text language sql stable security definer set search_path = '' as $$
  select distinct d.client_id from public.docs d
  where d.mech is not null and d.mech = lower(btrim(public.my_mechanic())) and d.client_id is not null
$$;

create function public.can_read_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when public.my_role() in ('owner','bureau') then true
    when public.my_role() = 'mecano' then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
      or p_col in ('config','days')
    else false end
$$;
create function public.can_write_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when p_col = 'meta' then false                                   -- numéros de facture : seulement par next_invoice_number()
    when public.my_role() = 'owner' then true
    when public.my_role() = 'bureau' then p_col in ('jobs','clients','days')
    when public.my_role() = 'mecano' then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
    else false end
$$;

create policy docs_read on public.docs for select to authenticated using (public.can_read_doc(col, id, mech));
-- a mechanic may create his own jobs (facture sur place) and new client fiches, nothing else
create policy docs_insert on public.docs for insert to authenticated
  with check (public.can_write_doc(col, id, mech) or (public.my_role() = 'mecano' and col = 'clients'));
create policy docs_update on public.docs for update to authenticated
  using (public.can_write_doc(col, id, mech)) with check (public.can_write_doc(col, id, mech));
create policy docs_delete on public.docs for delete to authenticated
  using (public.can_write_doc(col, id, mech) and (public.my_role() <> 'mecano' or col like 'data/users/%'));

create policy docs_deleted_read on public.docs_deleted for select to authenticated using (
  case when col like 'data/%' then col = 'data/users/' || auth.uid()::text
       else public.my_role() is not null end);

-- deep merge, like the app's update(): nested objects are merged, everything else is replaced
create function public.jsonb_merge_deep(a jsonb, b jsonb) returns jsonb language sql immutable set search_path = '' as $$
  select coalesce(jsonb_object_agg(k,
    case when jsonb_typeof(a -> k) = 'object' and jsonb_typeof(b -> k) = 'object' then public.jsonb_merge_deep(a -> k, b -> k)
         when b ? k then b -> k else a -> k end), '{}'::jsonb)
  from (select jsonb_object_keys(coalesce(a, '{}'::jsonb)) as k union select jsonb_object_keys(coalesce(b, '{}'::jsonb))) keys
$$;

-- update() of one document, in one step on the server (no lost updates between two phones)
create function public.doc_merge(p_path text, p_patch jsonb) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare out jsonb;
begin
  update public.docs set data = public.jsonb_merge_deep(data, p_patch) where path = p_path returning data into out;
  if out is null then raise exception 'not_found' using errcode = 'P0002'; end if;
  return out;
end $$;

-- set(): replaces the whole document (update if it exists, otherwise create it)
create function public.doc_set(p_path text, p_data jsonb) returns void language plpgsql security invoker set search_path = '' as $$
begin
  update public.docs set data = p_data where path = p_path;
  if not found then
    if exists (select 1 from public.docs where path = p_path) then raise exception 'not_granted' using errcode = '42501'; end if;
    insert into public.docs (path, data) values (p_path, p_data);
  end if;
end $$;

-- delete(): refused (instead of silently doing nothing) when the document exists but this person may not delete it
create function public.doc_delete(p_path text) returns boolean language plpgsql security invoker set search_path = '' as $$
begin
  delete from public.docs where path = p_path;
  if found then return true; end if;
  if exists (select 1 from public.docs where path = p_path) then raise exception 'not_granted' using errcode = '42501'; end if;
  return false;
end $$;

-- invoice numbers: one at a time for the whole garage
create function public.next_invoice_number(p_start int) returns int language plpgsql security definer set search_path = '' as $$
declare n int; s int := greatest(coalesce(p_start, 1), 1);
begin
  if public.my_role() is null then raise exception 'not_member' using errcode = '42501'; end if;
  insert into public.docs (path, data) values ('meta/invoices', jsonb_build_object('next', s + 1))
  on conflict (path) do update
    set data = jsonb_set(public.docs.data, '{next}', to_jsonb(greatest(coalesce((public.docs.data->>'next')::int, s), s) + 1))
  returning (data->>'next')::int - 1 into n;
  return n;
end $$;

-- ---------- Position des mécanos (seulement pendant leur journée de travail) ----------
create table public.mech_live (
  user_id          uuid primary key references public.members(user_id) on delete cascade,
  name             text,
  mechanic         text,
  on_shift         boolean not null default false,
  shift_started_at timestamptz,
  lat double precision, lon double precision, acc real, speed real, heading real,
  at               timestamptz,
  job_id           text
);
alter table public.mech_live enable row level security;
create policy mech_live_read on public.mech_live for select to authenticated using (public.is_staff() or user_id = auth.uid());

create table public.mech_positions (
  id      bigint generated always as identity primary key,
  user_id uuid not null references public.members(user_id) on delete cascade,
  at      timestamptz not null default now(),
  lat     double precision not null check (lat between -90 and 90),
  lon     double precision not null check (lon between -180 and 180),
  acc     real,
  speed   real
);
create index mech_positions_user_at on public.mech_positions (user_id, at);
create index mech_positions_at on public.mech_positions (at);
alter table public.mech_positions enable row level security;
create policy mech_positions_read on public.mech_positions for select to authenticated using (public.is_staff() or user_id = auth.uid());

-- ---------- Suivi « en route » envoyé au client ----------
create table public.tracks (
  token       text primary key check (length(token) >= 20),
  job_id      text not null,
  user_id     uuid references public.members(user_id) on delete set null,
  mech_name   text,
  client_first text,
  garage      text,
  dest_lat double precision, dest_lon double precision,
  status      text not null default 'active' check (status in ('active','arrived','cancelled')),
  created_by  uuid,
  created_at  timestamptz not null default now(),
  expires_at  timestamptz not null default now() + interval '4 hours',
  ended_at    timestamptz,
  route       jsonb,
  route_at    timestamptz,
  route_src   text,
  km          real,
  minutes     real,
  eta_at      timestamptz,
  sms_status  text,
  sms_error   text,
  sms_at      timestamptz
);
create unique index tracks_one_active on public.tracks (job_id) where status = 'active';
create index tracks_created on public.tracks (created_at);
alter table public.tracks enable row level security;
create policy tracks_read on public.tracks for select to authenticated using (public.is_staff() or user_id = auth.uid());

-- keeps 30 days of positions and links, nothing older
create function public.purge_old() returns void language sql security definer set search_path = '' as $$
  delete from public.mech_positions where at < now() - interval '30 days';
  delete from public.tracks where created_at < now() - interval '30 days';
  delete from public.docs_deleted where deleted_at < now() - interval '30 days';
$$;

create function public.shift_start() returns jsonb language plpgsql security definer set search_path = '' as $$
declare m public.members;
begin
  select * into m from public.members where user_id = auth.uid() and active;
  if m.user_id is null then raise exception 'not_member' using errcode = '42501'; end if;
  insert into public.mech_live (user_id, name, mechanic, on_shift, shift_started_at)
  values (m.user_id, m.name, m.mechanic, true, now())
  on conflict (user_id) do update set name = excluded.name, mechanic = excluded.mechanic, on_shift = true,
    shift_started_at = case when public.mech_live.on_shift then public.mech_live.shift_started_at else now() end;
  perform public.purge_old();
  return (select to_jsonb(l) from public.mech_live l where l.user_id = m.user_id);
end $$;

create function public.shift_end() returns void language plpgsql security definer set search_path = '' as $$
begin
  update public.mech_live set on_shift = false, shift_started_at = null, lat = null, lon = null, acc = null,
    speed = null, heading = null, at = null, job_id = null where user_id = auth.uid();
end $$;

-- the phone reports where it is; refused outside the workday
create function public.report_position(p_lat double precision, p_lon double precision, p_acc real default null,
  p_speed real default null, p_heading real default null) returns jsonb language plpgsql security definer set search_path = '' as $$
declare l public.mech_live; last_p public.mech_positions; moved double precision; stored boolean := false;
begin
  if p_lat is null or p_lon is null or p_lat not between -90 and 90 or p_lon not between -180 and 180 then
    raise exception 'bad_position' using errcode = '22023';
  end if;
  select * into l from public.mech_live where user_id = auth.uid() for update;
  if l.user_id is null or not l.on_shift or public.my_role() is null then return jsonb_build_object('ok', false, 'reason', 'off_shift'); end if;
  update public.mech_live set lat = p_lat, lon = p_lon, acc = p_acc, speed = p_speed, heading = p_heading, at = now()
  where user_id = auth.uid();
  select * into last_p from public.mech_positions where user_id = auth.uid() order by at desc limit 1;
  moved := case when last_p.id is null then 1e9 else
    6371000 * 2 * asin(sqrt(power(sin(radians(p_lat - last_p.lat) / 2), 2)
      + cos(radians(p_lat)) * cos(radians(last_p.lat)) * power(sin(radians(p_lon - last_p.lon) / 2), 2))) end;
  if last_p.id is null or moved >= 25 or last_p.at < now() - interval '60 seconds' then
    insert into public.mech_positions (user_id, lat, lon, acc, speed) values (auth.uid(), p_lat, p_lon, p_acc, p_speed);
    stored := true;
  end if;
  return jsonb_build_object('ok', true, 'stored', stored);
end $$;

-- what the client's tracking page may see: the mechanic's first name and position, only while he is on the way
create function public.get_track(p_token text) returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare t public.tracks; l public.mech_live; st text;
begin
  if p_token is null or length(p_token) < 20 then return null; end if;
  select * into t from public.tracks where token = p_token;
  if t.token is null then return null; end if;
  st := case when t.status = 'active' and now() > t.expires_at then 'expired' else t.status end;
  if st = 'active' then select * into l from public.mech_live where user_id = t.user_id and on_shift; end if;
  return jsonb_build_object(
    'status', st, 'mech', split_part(btrim(coalesce(t.mech_name, '')), ' ', 1), 'client', t.client_first, 'garage', t.garage,
    'dest', case when t.dest_lat is null then null else jsonb_build_object('lat', t.dest_lat, 'lon', t.dest_lon) end,
    'route', case when st = 'active' then t.route end, 'route_at', t.route_at, 'km', t.km, 'minutes', t.minutes, 'eta_at', t.eta_at,
    'created_at', t.created_at, 'ended_at', t.ended_at, 'now', now(),
    'pos', case when st = 'active' and l.lat is not null and l.at > now() - interval '15 minutes'
                then jsonb_build_object('lat', l.lat, 'lon', l.lon, 'at', l.at, 'heading', l.heading, 'speed', l.speed, 'acc', l.acc) end);
end $$;

-- ---------- Première mise en route + secrets du serveur ----------
create table public.setup_codes (
  code_hash  text primary key,
  expires_at timestamptz not null default now() + interval '7 days'
);
alter table public.setup_codes enable row level security;

create function public.setup_needed() returns boolean language sql stable security definer set search_path = '' as $$
  select not exists (select 1 from public.members where role = 'owner' and active)
$$;

-- GoHighLevel token, routing key… readable only by the server functions (no policy = nobody through the API)
create table public.app_secrets (
  name       text primary key,
  value      text not null,
  updated_at timestamptz not null default now()
);
alter table public.app_secrets enable row level security;

-- ---------- Droits ----------
revoke all on public.setup_codes, public.app_secrets from anon, authenticated;
revoke all on public.members, public.docs, public.docs_deleted, public.mech_live, public.mech_positions, public.tracks from anon;
revoke insert, update, delete on public.mech_live, public.mech_positions, public.tracks, public.docs_deleted from authenticated;
revoke insert, delete on public.members from authenticated;

-- explicit access (works whether or not the project exposes new tables automatically)
grant usage on schema public to anon, authenticated, service_role;
grant select, insert, update, delete on public.docs to authenticated;
grant select on public.members, public.docs_deleted, public.mech_live, public.mech_positions, public.tracks to authenticated;
grant update on public.members to authenticated;
grant all on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;

-- Supabase gives these by default (truncate, references, trigger, maintain): not needed by the app
revoke truncate, references, trigger on all tables in schema public from anon, authenticated;
do $$ begin
  if current_setting('server_version_num')::int >= 170000 then
    execute 'revoke maintain on all tables in schema public from anon, authenticated';
  end if;
end $$;

revoke execute on all functions in schema public from public, anon, authenticated;
grant execute on function public.get_track(text), public.setup_needed() to anon, authenticated;
grant execute on function public.my_role(), public.my_mechanic(), public.is_staff(), public.mech_client_ids(),
  public.can_read_doc(text, text, text), public.can_write_doc(text, text, text), public.jsonb_merge_deep(jsonb, jsonb),
  public.doc_merge(text, jsonb), public.doc_set(text, jsonb), public.doc_delete(text), public.next_invoice_number(int), public.shift_start(), public.shift_end(),
  public.report_position(double precision, double precision, real, real, real) to authenticated;
grant execute on all functions in schema public to service_role;
alter default privileges in schema public revoke execute on functions from public, anon;

-- instant updates between phones (when the realtime service exists)
do $$ begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.docs, public.mech_live, public.tracks;
  end if;
end $$;

-- new tables are not opened to the API by themselves: each table gets its rights explicitly, like above
alter default privileges in schema public revoke select, insert, update, delete, truncate, references, trigger on tables from anon, authenticated;
do $$ begin
  if current_setting('server_version_num')::int >= 170000 then
    execute 'alter default privileges in schema public revoke maintain on tables from anon, authenticated';
  end if;
end $$;
