-- Le mécano choisit son camion (novembre 2026). Rien n'est effacé : une fonction de plus.
--
-- Personne n'assigne les mécanos aux camions. Le matin, chaque mécano choisit dans son app « Je conduis : … ».
-- Son choix va dans l'équipe du jour (days/<date> → crew {camion: mécano}), et les rendez-vous prévus de ce camion ce
-- jour-là deviennent les siens (il les voit, il part « en route », il encaisse). Ceux du camion qu'il quitte reviennent à
-- celui qui a pris ce camion, sinon à personne.
-- Un mécano ne peut pas écrire ces documents lui-même : cette fonction le fait pour lui, seulement pour lui, seulement pour
-- aujourd'hui et les jours à venir, seulement les rendez-vous pas encore commencés.

create or replace function public.pick_truck(p_date text, p_truck text) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  me text := btrim(coalesce(public.my_mechanic(), ''));
  k text := btrim(coalesce(p_truck, ''));
  cfg jsonb; crew jsonb; x record; n int := 0; m int := 0; mine int := 0;
  ts bigint := (extract(epoch from clock_timestamp()) * 1000)::bigint;
begin
  if public.my_role() is null or me = '' then raise exception 'not_mechanic' using errcode = '42501'; end if;
  if p_date is null or p_date !~ '^\d{4}-\d{2}-\d{2}$' then raise exception 'bad_date' using errcode = '22023'; end if;
  if p_date < to_char((now() at time zone 'America/Toronto')::date, 'YYYY-MM-DD') then raise exception 'past_day' using errcode = '22023'; end if;
  -- a truck of the garage (the ones saved in the settings; before any is saved, the 3 trucks the app starts with)
  select data into cfg from public.docs where path = 'config/main';
  if k <> '' and not (
       (jsonb_typeof(cfg->'trucks') = 'array' and exists (select 1 from jsonb_array_elements(cfg->'trucks') t where t->>'id' = k))
    or (jsonb_typeof(cfg->'trucks') is distinct from 'array' and k in ('c1', 'c2', 'c3'))) then
    raise exception 'no_truck' using errcode = '22023';
  end if;

  -- that day's crew: he leaves the truck he had, takes this one (whoever had it before is replaced)
  select case when jsonb_typeof(data->'crew') = 'object' then data->'crew' end into crew from public.docs where path = 'days/' || p_date;
  crew := coalesce(crew, '{}'::jsonb);
  for x in select key from jsonb_each_text(crew) where lower(btrim(value)) = lower(me) loop crew := crew - x.key; end loop;
  if k <> '' then crew := crew || jsonb_build_object(k, me); end if;
  insert into public.docs (path, data) values ('days/' || p_date, jsonb_build_object('date', p_date, 'opened', '[]'::jsonb, 'blocked', '[]'::jsonb, 'crew', crew, 'updatedAt', ts))
  on conflict (path) do update set data = public.docs.data || jsonb_build_object('crew', crew, 'updatedAt', ts);

  -- the planned appointments of that truck that day: his
  if k <> '' then
    update public.docs set data = data || jsonb_build_object('mechanic', me, 'updatedAt', ts)
     where col = 'jobs' and data->>'date' = p_date and coalesce(data->>'truck', '') = k
       and coalesce(data->>'status', 'planifie') = 'planifie' and coalesce(mech, '') <> lower(me);
    get diagnostics n = row_count;
  end if;
  -- those of the truck he left: to whoever has that truck now, otherwise nobody
  update public.docs d set data = d.data || jsonb_build_object('mechanic', coalesce(crew->>(d.data->>'truck'), ''), 'updatedAt', ts)
   where d.col = 'jobs' and d.data->>'date' = p_date and d.mech = lower(me)
     and coalesce(d.data->>'truck', '') not in ('', k) and coalesce(d.data->>'status', 'planifie') = 'planifie';
  get diagnostics m = row_count;

  if k <> '' then
    select count(*) into mine from public.docs
     where col = 'jobs' and data->>'date' = p_date and coalesce(data->>'truck', '') = k and mech = lower(me)
       and coalesce(data->>'status', 'planifie') not in ('annule', 'noshow');
  end if;
  return jsonb_build_object('ok', true, 'truck', k, 'mine', mine, 'taken', n, 'left', m, 'crew', crew);
end $$;
revoke execute on function public.pick_truck(text, text) from public, anon;
grant execute on function public.pick_truck(text, text) to authenticated;
