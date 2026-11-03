-- Corrections rapides (novembre 2026). Rien n'est effacé : trois fonctions et une petite table de compteurs.
--
-- 1. doc_patch : enregistrer seulement les parties qui ont changé d'un document (les réglages du garage).
--    Ce que quelqu'un d'autre a changé entre-temps (une autre partie) reste.
-- 2. Réserver dans un bloc : un compteur par bloc (jour + matin / après-midi / soir). Une réservation passe
--    seulement si personne n'a réservé dans ce bloc depuis que l'app a compté la place ; sinon l'app recompte.
-- 3. number_invoice : une facture terminée sans réseau attend son numéro ; le premier appareil en ligne lui donne
--    le prochain numéro de la série, une seule fois (deux appareils en même temps : un seul numéro est pris).

-- ---------- 1. patch : seulement les parties données sont remplacées (au premier niveau) ----------
create or replace function public.doc_patch(p_path text, p_set jsonb, p_unset text[] default '{}') returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare out jsonb;
begin
  if p_set is null or jsonb_typeof(p_set) <> 'object' then raise exception 'bad_patch' using errcode = '22023'; end if;
  update public.docs set data = (data - coalesce(p_unset, '{}'::text[])) || p_set where path = p_path returning data into out;
  if out is null then
    if exists (select 1 from public.docs where path = p_path) then raise exception 'not_granted' using errcode = '42501'; end if;
    insert into public.docs (path, data) values (p_path, p_set) returning data into out;
  end if;
  return out;
end $$;

-- ---------- 2. les blocs : un compteur par bloc ----------
create table if not exists public.block_marks (
  key text primary key check (key ~ '^\d{4}-\d{2}-\d{2}\|(am|pm|eve)$'),
  n   bigint not null default 0,
  at  timestamptz not null default clock_timestamp()
);
alter table public.block_marks enable row level security;
revoke all on public.block_marks from anon, authenticated;

-- où en est le compteur d'un bloc (0 si personne n'y a encore réservé)
create or replace function public.block_mark(p_key text) returns bigint language plpgsql stable security definer set search_path = '' as $$
begin
  if public.my_role() is null then raise exception 'not_member' using errcode = '42501'; end if;
  return coalesce((select n from public.block_marks where key = p_key), 0);
end $$;

-- prend la place : -1 si le compteur a bougé depuis (p_mark) ; p_mark vide = sans vérifier (réservation faite hors ligne)
create or replace function public.block_take(p_key text, p_mark bigint) returns bigint language plpgsql security definer set search_path = '' as $$
declare cur bigint;
begin
  if public.my_role() is null then raise exception 'not_member' using errcode = '42501'; end if;
  if p_key is null or p_key !~ '^\d{4}-\d{2}-\d{2}\|(am|pm|eve)$' then raise exception 'bad_block' using errcode = '22023'; end if;
  insert into public.block_marks (key) values (p_key) on conflict (key) do nothing;
  select n into cur from public.block_marks where key = p_key for update;   -- (deux réservations du même bloc : une à la fois)
  if p_mark is not null and cur <> p_mark then return -1; end if;
  update public.block_marks set n = n + 1, at = clock_timestamp() where key = p_key;
  return cur + 1;
end $$;

-- la réservation elle-même : la job est écrite avec les droits de la personne (mêmes règles que d'habitude) ;
-- si elle n'a pas le droit, rien ne change, pas même le compteur
create or replace function public.block_book(p_key text, p_mark bigint, p_path text, p_data jsonb, p_merge boolean default false) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare m bigint; out jsonb;
begin
  if p_path is null or p_path !~ '^jobs/[A-Za-z0-9_-]+$' then raise exception 'bad_path' using errcode = '22023'; end if;
  m := public.block_take(p_key, p_mark);
  if m < 0 then return jsonb_build_object('ok', false, 'mark', public.block_mark(p_key)); end if;
  if coalesce(p_merge, false) then out := public.doc_merge(p_path, p_data);
  else perform public.doc_set(p_path, p_data); out := p_data; end if;
  return jsonb_build_object('ok', true, 'mark', m, 'data', out);
end $$;

-- ---------- 3. le numéro d'une facture terminée hors ligne ----------
create or replace function public.number_invoice(p_path text) returns text language plpgsql security definer set search_path = '' as $$
declare r public.docs%rowtype; conf jsonb; pre text; st int; n int; num text; inv jsonb; ms bigint;
begin
  if p_path is null or p_path !~ '^jobs/[A-Za-z0-9_-]+$' then raise exception 'bad_path' using errcode = '22023'; end if;
  select * into r from public.docs where path = p_path for update;          -- (deux appareils en même temps : un à la fois)
  if not found or not public.can_read_doc(r.col, r.id, r.mech) then raise exception 'not_found' using errcode = '42501'; end if;   -- (pas à lui : refusé)
  if not public.can_write_doc(r.col, r.id, r.mech) then raise exception 'not_granted' using errcode = '42501'; end if;
  inv := r.data -> 'invoice';
  if inv is null or jsonb_typeof(inv) <> 'object' then raise exception 'no_invoice' using errcode = '22023'; end if;
  num := inv ->> 'number';
  if coalesce(num, '') <> '' then return num; end if;                        -- déjà numérotée (par un autre appareil) : le même numéro
  if jsonb_typeof(inv -> 'toNumber') is distinct from 'boolean' or not (inv ->> 'toNumber')::boolean then
    raise exception 'not_finished' using errcode = '22023';                  -- un brouillon reste un brouillon
  end if;
  select data into conf from public.docs where path = 'config/main';
  pre := case when jsonb_typeof(conf -> 'prefix') = 'string' then conf ->> 'prefix' else 'F-' end;
  st := greatest(1, coalesce(substring(coalesce(conf ->> 'startNo', '') from '^\s*(\d{1,9})')::int, 1));
  n := public.next_invoice_number(st);
  num := pre || case when length(n::text) >= 4 then n::text else lpad(n::text, 4, '0') end;
  ms := (extract(epoch from clock_timestamp()) * 1000)::bigint;
  update public.docs set data = r.data || jsonb_build_object('invoice', (inv - 'toNumber') || jsonb_build_object('number', num, 'numberedAt', ms, 'updatedAt', ms), 'updatedAt', ms)
   where path = p_path;
  return num;
end $$;

grant execute on function public.doc_patch(text, jsonb, text[]), public.block_mark(text), public.block_take(text, bigint),
  public.block_book(text, bigint, text, jsonb, boolean), public.number_invoice(text) to authenticated, service_role;
