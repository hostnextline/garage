-- Fiche technique par moteur (« specs ») : toute l'équipe la lit ; les mécanos et le bureau la complètent.
-- Rien n'est effacé : on ajoute seulement « specs » aux règles d'accès.
create or replace function public.can_read_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when public.my_role() in ('owner','bureau','tresorier') then true
    when public.my_role() = 'mecano' then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
      or p_col in ('config','days','avail','specs')
    else false end
$$;

create or replace function public.can_write_doc(p_col text, p_id text, p_mech text) returns boolean language sql stable security definer set search_path = '' as $$
  select case
    when p_col = 'data/users/' || auth.uid()::text then public.my_role() is not null
    when p_col like 'data/%' then false
    when p_col = 'meta' then false                                   -- numéros de facture : seulement par next_invoice_number()
    when public.my_role() = 'owner' then true
    when public.my_role() = 'bureau' then p_col in ('jobs','clients','days','avail','specs')
    when public.my_role() = 'tresorier' then p_col in ('expenses','receipts')
    when public.my_role() = 'mecano' then
      (p_col = 'jobs' and p_mech is not null and p_mech = lower(btrim(public.my_mechanic())))
      or (p_col = 'clients' and p_id in (select public.mech_client_ids()))
      or p_col = 'specs'
    else false end
$$;
