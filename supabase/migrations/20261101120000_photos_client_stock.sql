-- Photos avant/après + signature, page du client (facture, paiement Stripe, travaux à approuver), stock des camions.
-- Rien n'est effacé : on élargit les règles d'accès et on ajoute deux tables lisibles seulement par le serveur.

-- 1. update() d'un document qu'on n'a pas le droit de changer : « pas permis » (au lieu de « n'existe pas »)
create or replace function public.doc_merge(p_path text, p_patch jsonb) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare out jsonb;
begin
  update public.docs set data = public.jsonb_merge_deep(data, p_patch) where path = p_path returning data into out;
  if out is null then
    if exists (select 1 from public.docs where path = p_path) then raise exception 'not_granted' using errcode = '42501'; end if;
    raise exception 'not_found' using errcode = 'P0002';
  end if;
  return out;
end $$;

-- 2. une photo (photos/<job>__<n>) appartient à sa job : le mécano voit et ajoute seulement celles de ses jobs
create or replace function public.mech_job_ids() returns setof text language sql stable security definer set search_path = '' as $$
  select d.id from public.docs d where d.col = 'jobs' and d.mech is not null and d.mech = lower(btrim(public.my_mechanic()))
$$;
revoke execute on function public.mech_job_ids() from public, anon;
grant execute on function public.mech_job_ids() to authenticated, service_role;

create or replace function public.can_read_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when public.my_role() in ('owner','bureau','tresorier') then true
    when public.my_role() = 'mecano' then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
      or (p_col = 'photos' and split_part(p_id, '__', 1) in (select public.mech_job_ids()))
      or p_col in ('config','days','avail','specs','stock')
    else false end
$$;

create or replace function public.can_write_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when p_col = 'meta' then false                                   -- numéros de facture : seulement par next_invoice_number()
    when public.my_role() = 'owner' then true
    when public.my_role() = 'bureau' then p_col in ('jobs','clients','days','avail','specs','photos','stock')
    when public.my_role() = 'tresorier' then p_col in ('expenses','receipts','stock')
    when public.my_role() = 'mecano' then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
      or (p_col = 'photos' and split_part(p_id, '__', 1) in (select public.mech_job_ids()))
      or p_col in ('specs','stock')
    else false end
$$;

-- un mécano peut retirer une photo de ses jobs (rien d'autre)
drop policy if exists docs_delete on public.docs;
create policy docs_delete on public.docs for delete to authenticated
  using (public.can_write_doc(col, id, mech) and (public.my_role() <> 'mecano' or col like 'data/users/%' or col = 'photos'));

-- 3. liens secrets de la page du client (lus et écrits seulement par le serveur : aucune règle = personne par l'API)
create table if not exists public.client_links (
  token        text primary key check (length(token) >= 20),
  job_id       text not null,
  created_by   uuid,
  base         text,
  created_at   timestamptz not null default now(),
  expires_at   timestamptz not null default now() + interval '120 days',
  revoked      boolean not null default false,
  last_session text
);
create index if not exists client_links_job on public.client_links (job_id, created_at desc);
alter table public.client_links enable row level security;

-- paiements Stripe déjà traités (Stripe peut renvoyer le même avis plusieurs fois)
create table if not exists public.stripe_events (
  id      text primary key,
  type    text,
  at      timestamptz not null default now()
);
alter table public.stripe_events enable row level security;

-- personne d'autre que le serveur : pas même un accès vide par l'API
revoke all on public.client_links, public.stripe_events from anon, authenticated;
grant all on public.client_links, public.stripe_events to service_role;
