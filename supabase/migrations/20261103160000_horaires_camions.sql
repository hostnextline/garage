-- Un horaire par camion (novembre 2026). Rien n'est effacé : seulement qui peut lire et écrire les horaires des camions.
--
-- L'horaire de chaque camion est un document « hours/<camion> » ({week, dates}) : sa semaine habituelle et ses changements
-- pour certains jours. Il est changé par le propriétaire et par ceux qui ont la case « Changer l'horaire du garage et des
-- autres » (le bureau l'a au départ). Tout le monde le lit (un mécano aussi : son agenda en dépend).
-- Mettre un camion en service ou le retirer pour de bon reste dans les réglages (le propriétaire seulement).

create or replace function public.can_read_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when public.has_role('owner') or public.has_role('bureau') or public.has_role('tresorier') then true
    when public.has_role('mecano') then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
      or (p_col = 'photos' and split_part(p_id, '__', 1) in (select public.mech_job_ids()))
      or p_col in ('config','days','avail','specs','stock','hours')
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
      or (p_col in ('avail','days','hours') and public.my_perm('hours_others'))                   -- case « Changer l'horaire du garage et des autres »
      or (p_col = 'hours' and public.has_role('bureau') and coalesce(                              -- (le bureau l'a au départ : sauf si on la lui a enlevée)
           (select (m.perms ->> 'hours_others')::boolean from public.members m where m.user_id = auth.uid() and m.active and jsonb_typeof(m.perms -> 'hours_others') = 'boolean'),
           (select (d.data -> 'bureau' ->> 'hours_others')::boolean from public.docs d where d.path = 'config/roles' and jsonb_typeof(d.data -> 'bureau' -> 'hours_others') = 'boolean'),
           true))
  end
$$;
