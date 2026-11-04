-- Les mécanos voient toutes les routes et peuvent tout faire sur n'importe quelle job (novembre 2026). Rien n'est effacé :
-- seulement qui peut lire et écrire.
--
-- Garage familial : chaque mécano voit les rendez-vous de tous les camions (et leurs clients, leurs photos), pour aller aider
-- un autre au besoin, et il peut faire les étapes de n'importe quelle job (en route, photos, terminer, facture, encaisser).
-- Ce qui reste fermé pour un mécano : les réglages, l'argent du garage (sauf la case « Trésorerie »), l'équipe.
-- (Avant : seulement ses propres jobs et les clients de ses jobs.)

create or replace function public.can_read_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when public.has_role('owner') or public.has_role('bureau') or public.has_role('tresorier') then true
    when public.has_role('mecano') then
      p_col in ('jobs','clients','photos','config','days','avail','specs','stock','hours')            -- toutes les routes
      or (p_col in ('expenses','receipts') and public.my_perm('tresor'))                             -- case « Trésorerie » donnée à un mécano
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
      or (public.has_role('mecano') and p_col in ('jobs','clients','photos','specs','stock'))  -- n'importe quelle job, n'importe quel client
      or (p_col in ('expenses','receipts') and public.my_perm('tresor'))                          -- case « Trésorerie »
      or (p_col in ('avail','days','hours') and public.my_perm('hours_others'))                   -- case « Changer l'horaire du garage et des autres »
      or (p_col = 'hours' and public.has_role('bureau') and coalesce(                              -- (le bureau l'a au départ : sauf si on la lui a enlevée)
           (select (m.perms ->> 'hours_others')::boolean from public.members m where m.user_id = auth.uid() and m.active and jsonb_typeof(m.perms -> 'hours_others') = 'boolean'),
           (select (d.data -> 'bureau' ->> 'hours_others')::boolean from public.docs d where d.path = 'config/roles' and jsonb_typeof(d.data -> 'bureau' -> 'hours_others') = 'boolean'),
           true))
  end
$$;

-- le trésorier ne change que la facture d'une job… sauf s'il est aussi mécano (un mécano fait tout sur n'importe quelle job)
create or replace function public.docs_tresorier_guard() returns trigger language plpgsql security definer set search_path = '' as $$
declare p text := coalesce(new.path, old.path);
begin
  if p not like 'jobs/%' or not public.has_role('tresorier') or public.has_role('owner') or public.has_role('bureau') or public.has_role('mecano') then return coalesce(new, old); end if;
  if tg_op in ('INSERT', 'DELETE') then raise exception 'tresorier_factures_seulement' using errcode = '42501'; end if;
  if (new.data - 'invoice' - 'updatedAt' - 'status') is distinct from (old.data - 'invoice' - 'updatedAt' - 'status')
     or ((new.data -> 'status') is distinct from (old.data -> 'status') and coalesce(new.data ->> 'status', '') <> 'termine') then
    raise exception 'tresorier_factures_seulement' using errcode = '42501';
  end if;
  return new;
end $$;
revoke execute on function public.docs_tresorier_guard() from public, anon;
