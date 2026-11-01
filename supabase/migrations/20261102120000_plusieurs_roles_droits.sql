-- Plusieurs rôles par personne + droits par personne.
-- members.roles : la liste des rôles (ex. {mecano,tresorier}) ; members.role reste le rôle « principal »
--   (propriétaire > bureau > mécano > trésorier) pour tout ce qui l'utilisait déjà.
-- members.perms : les droits ajoutés ou enlevés pour CETTE personne ({"book": true, "clients": false}…).
-- Rien ne change pour les comptes actuels : roles = {leur rôle}, perms = {}.
-- Le serveur vérifie aussi ces cases : « Trésorerie » (dépenses, reçus), « Changer l'horaire du garage et des autres »,
-- « Modifier les factures » (trésorier, la facture seulement) ; « Voir la carte » est dans team_map().

alter table public.members add column if not exists roles text[] not null default '{}';
alter table public.members add column if not exists perms jsonb not null default '{}'::jsonb;
update public.members set roles = array[role] where roles = '{}' or roles is null;
alter table public.members drop constraint if exists members_roles_check;
alter table public.members add constraint members_roles_check check (roles <@ array['owner','bureau','mecano','tresorier']::text[] and cardinality(roles) >= 1);
alter table public.members drop constraint if exists members_perms_check;
alter table public.members add constraint members_perms_check check (jsonb_typeof(perms) = 'object');
alter table public.members drop constraint if exists mecano_needs_mechanic;
alter table public.members add constraint mecano_needs_mechanic check (not ('mecano' = any(roles)) or mechanic is not null);

-- the main role always follows the list
create or replace function public.members_main_role() returns trigger language plpgsql set search_path = '' as $$
begin
  -- an older screen or function that only changes « role » (one role): the list follows
  if tg_op = 'UPDATE' and new.role is distinct from old.role and new.roles is not distinct from old.roles then new.roles := array[new.role]; end if;
  if new.roles is null or cardinality(new.roles) = 0 then new.roles := array[new.role]; end if;
  new.roles := array(select distinct r from unnest(new.roles) r order by 1);
  new.role := case when 'owner' = any(new.roles) then 'owner' when 'bureau' = any(new.roles) then 'bureau'
                   when 'mecano' = any(new.roles) then 'mecano' else 'tresorier' end;
  return new;
end $$;
drop trigger if exists members_a_main_role on public.members;
-- « members_a_… » runs before « members_keep_owner » (same moment: name order), so the owner check sees the new main role
create trigger members_a_main_role before insert or update on public.members for each row execute function public.members_main_role();

create or replace function public.has_role(p_role text) returns boolean language sql stable security definer set search_path = '' as $$
  select coalesce((select p_role = any(m.roles) or m.role = p_role from public.members m where m.user_id = auth.uid() and m.active), false)
$$;
-- a right of this person: what was set for HIM, otherwise what his roles give (boxes of « Ce que chaque rôle peut faire »)
create or replace function public.my_perm(p_key text) returns boolean language sql stable security definer set search_path = '' as $$
  select coalesce(
    (select (m.perms ->> p_key)::boolean from public.members m where m.user_id = auth.uid() and m.active and jsonb_typeof(m.perms -> p_key) = 'boolean'),
    (select bool_or(public.role_perm(r, p_key)) from public.members m, unnest(m.roles) r where m.user_id = auth.uid() and m.active),
    false)
$$;
revoke execute on function public.has_role(text), public.my_perm(text) from public, anon;
grant execute on function public.has_role(text), public.my_perm(text) to authenticated, service_role;

create or replace function public.is_staff() returns boolean language sql stable security definer set search_path = '' as $$
  select public.has_role('owner') or public.has_role('bureau')
$$;

create or replace function public.can_read_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when public.has_role('owner') or public.has_role('bureau') or public.has_role('tresorier') then true
    when public.has_role('mecano') then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
      or (p_col = 'photos' and split_part(p_id, '__', 1) in (select public.mech_job_ids()))
      or p_col in ('config','days','avail','specs','stock')
      or (p_col in ('expenses','receipts') and public.my_perm('tresor'))                        -- case « Trésorerie » donnée à un mécano
    else false end
$$;

create or replace function public.can_write_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when p_col = 'meta' then false                                   -- numéros de facture : seulement par next_invoice_number()
    when public.has_role('owner') then true
    else
      (public.has_role('bureau') and p_col in ('jobs','clients','days','avail','specs','photos','stock'))
      or (public.has_role('tresorier') and (p_col in ('expenses','receipts','stock')
          or (p_col = 'jobs' and public.my_perm('editinv'))))                                   -- la facture seulement (docs_tresorier_guard)
      or (public.has_role('mecano') and (
          (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
          or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
          or (p_col = 'photos' and split_part(p_id, '__', 1) in (select public.mech_job_ids()))
          or p_col in ('specs','stock')))
      or (p_col in ('expenses','receipts') and public.my_perm('tresor'))                          -- case « Trésorerie »
      or (p_col in ('avail','days') and public.my_perm('hours_others'))                           -- case « Changer l'horaire du garage et des autres »
  end
$$;

create or replace function public.own_avail(p_col text, p_data jsonb) returns boolean language sql stable security definer set search_path = '' as $$
  select p_col = 'avail' and public.has_role('mecano') and p_data ? 'mechanic'
     and lower(btrim(p_data->>'mechanic')) = lower(btrim(public.my_mechanic()))
$$;

drop policy if exists docs_insert on public.docs;
create policy docs_insert on public.docs for insert to authenticated
  with check (public.can_write_doc(col, id, mech) or (public.has_role('mecano') and col = 'clients') or public.own_avail(col, data));
drop policy if exists docs_delete on public.docs;
create policy docs_delete on public.docs for delete to authenticated
  using (public.can_write_doc(col, id, mech) and (public.my_role() <> 'mecano' or col like 'data/users/%' or col = 'photos'
         or (public.has_role('tresorier') and col in ('expenses','receipts','stock'))
         or (col in ('expenses','receipts') and public.my_perm('tresor'))));

-- the treasurer side of a person only touches invoices; what his other roles allow stays allowed
create or replace function public.docs_tresorier_guard() returns trigger language plpgsql security definer set search_path = '' as $$
declare p text := coalesce(new.path, old.path); mine boolean;
begin
  if p not like 'jobs/%' or not public.has_role('tresorier') or public.has_role('owner') or public.has_role('bureau') then return coalesce(new, old); end if;
  mine := public.has_role('mecano') and lower(btrim(public.my_mechanic())) is not distinct from coalesce(old.mech, new.mech)
          and (tg_op <> 'UPDATE' or new.mech is not distinct from old.mech);
  if mine then return coalesce(new, old); end if;
  if tg_op in ('INSERT', 'DELETE') then raise exception 'tresorier_factures_seulement' using errcode = '42501'; end if;
  if (new.data - 'invoice' - 'updatedAt' - 'status') is distinct from (old.data - 'invoice' - 'updatedAt' - 'status')
     or ((new.data -> 'status') is distinct from (old.data -> 'status') and coalesce(new.data ->> 'status', '') <> 'termine') then
    raise exception 'tresorier_factures_seulement' using errcode = '42501';
  end if;
  return new;
end $$;
revoke execute on function public.docs_tresorier_guard() from public, anon;
