-- Ce que chaque rôle peut faire : le propriétaire coche des cases dans Équipe et accès (document config/roles).
-- Rien de coché = exactement comme avant. Une seule case donne plus de droits au serveur :
--   trésorier « Modifier les factures » → il peut changer la facture d'une job (et la mettre « terminée »), rien d'autre.
-- Les autres cases changent ce que l'écran montre (le serveur garde ses règles : un mécano ne lit et n'écrit que ses jobs).

create or replace function public.role_perm(p_role text, p_key text) returns boolean language sql stable security definer set search_path = '' as $$
  select coalesce((select (d.data -> p_role ->> p_key)::boolean from public.docs d
                   where d.path = 'config/roles' and jsonb_typeof(d.data -> p_role -> p_key) = 'boolean'), false)
$$;
revoke execute on function public.role_perm(text, text) from public, anon;
grant execute on function public.role_perm(text, text) to authenticated, service_role;

create or replace function public.can_write_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when p_col = 'meta' then false                                   -- numéros de facture : seulement par next_invoice_number()
    when public.my_role() = 'owner' then true
    when public.my_role() = 'bureau' then p_col in ('jobs','clients','days','avail','specs','photos','stock')
    when public.my_role() = 'tresorier' then p_col in ('expenses','receipts','stock')
      or (p_col = 'jobs' and public.role_perm('tresorier', 'editinv'))           -- la facture seulement (voir docs_tresorier_guard)
    when public.my_role() = 'mecano' then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
      or (p_col = 'photos' and split_part(p_id, '__', 1) in (select public.mech_job_ids()))
      or p_col in ('specs','stock')
    else false end
$$;

-- le trésorier qui peut « Modifier les factures » ne touche qu'à la facture : pas de nouvelle job, pas d'effacement, pas d'autre champ
create or replace function public.docs_tresorier_guard() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if public.my_role() is distinct from 'tresorier' then return coalesce(new, old); end if;
  if (tg_op = 'INSERT' and new.path like 'jobs/%') or (tg_op = 'DELETE' and old.path like 'jobs/%') then
    raise exception 'tresorier_factures_seulement' using errcode = '42501';
  end if;
  if tg_op = 'UPDATE' and old.path like 'jobs/%' then
    if (new.data - 'invoice' - 'updatedAt' - 'status') is distinct from (old.data - 'invoice' - 'updatedAt' - 'status')
       or ((new.data -> 'status') is distinct from (old.data -> 'status') and coalesce(new.data ->> 'status', '') <> 'termine') then
      raise exception 'tresorier_factures_seulement' using errcode = '42501';
    end if;
  end if;
  return coalesce(new, old);
end $$;
revoke execute on function public.docs_tresorier_guard() from public, anon;
drop trigger if exists docs_tresorier_guard on public.docs;
create trigger docs_tresorier_guard before insert or update or delete on public.docs for each row execute function public.docs_tresorier_guard();
