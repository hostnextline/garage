-- Camions (colonnes de l'horaire), disponibilités choisies par les mécanos, rôle « trésorier » (dépenses + reçus).
-- Rien n'est effacé : on élargit seulement les rôles et les règles d'accès.

-- 1. un 4e rôle : trésorier
alter table public.members drop constraint if exists members_role_check;
alter table public.members add constraint members_role_check check (role in ('owner','bureau','mecano','tresorier'));

-- 2. lire : le trésorier lit le carnet (pas les brouillons personnels des autres) ; les dispos sont lisibles par toute l'équipe
create or replace function public.can_read_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when public.my_role() in ('owner','bureau','tresorier') then true
    when public.my_role() = 'mecano' then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
      or p_col in ('config','days','avail')
    else false end
$$;

-- 3. écrire : le bureau gère aussi les dispos ; le trésorier écrit seulement les dépenses et leurs reçus
create or replace function public.can_write_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when p_col = 'meta' then false                                   -- numéros de facture : seulement par next_invoice_number()
    when public.my_role() = 'owner' then true
    when public.my_role() = 'bureau' then p_col in ('jobs','clients','days','avail')
    when public.my_role() = 'tresorier' then p_col in ('expenses','receipts')
    when public.my_role() = 'mecano' then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
    else false end
$$;

-- 4. un mécano choisit ses propres disponibilités : le document porte son nom, il ne peut pas toucher celles des autres
create or replace function public.own_avail(p_col text, p_data jsonb) returns boolean language sql stable security definer set search_path = '' as $$
  select p_col = 'avail' and public.my_role() = 'mecano' and p_data ? 'mechanic'
     and lower(btrim(p_data->>'mechanic')) = lower(btrim(public.my_mechanic()))
$$;
revoke execute on function public.own_avail(text, jsonb) from public, anon;
grant execute on function public.own_avail(text, jsonb) to authenticated, service_role;

drop policy if exists docs_insert on public.docs;
create policy docs_insert on public.docs for insert to authenticated
  with check (public.can_write_doc(col, id, mech) or (public.my_role() = 'mecano' and col = 'clients') or public.own_avail(col, data));
drop policy if exists docs_update on public.docs;
create policy docs_update on public.docs for update to authenticated
  using (public.can_write_doc(col, id, mech) or public.own_avail(col, data))
  with check (public.can_write_doc(col, id, mech) or public.own_avail(col, data));
