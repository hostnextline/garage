-- Carte de l'équipe pour tout le monde : les mécanos (position pendant leur journée), leurs trajets en cours,
-- et TOUS les rendez-vous du jour avec le nom et l'adresse du client (choix du propriétaire), numérotés par mécano.
-- Lecture seulement, par une seule fonction : les règles des tables ne changent pas (un mécano ne lit toujours
-- que ses propres jobs et clients ailleurs dans l'app). Case « Voir la carte » : oui par défaut.

create or replace function public.team_map(p_day date default null) returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare d text := coalesce(p_day, (now() at time zone 'America/Toronto')::date)::text; ok boolean;
begin
  if public.my_role() is null then raise exception 'not_member' using errcode = '42501'; end if;
  ok := public.has_role('owner') or public.has_role('bureau') or coalesce(
    (select (m.perms ->> 'map')::boolean from public.members m where m.user_id = auth.uid() and m.active and jsonb_typeof(m.perms -> 'map') = 'boolean'),
    (select bool_or((c.data -> r ->> 'map')::boolean) from public.members m cross join unnest(m.roles) r join public.docs c on c.path = 'config/roles'
       where m.user_id = auth.uid() and m.active and jsonb_typeof(c.data -> r -> 'map') = 'boolean'),
    true);
  if not ok then raise exception 'not_granted' using errcode = '42501'; end if;
  return jsonb_build_object(
    'day', d,
    'jobs', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', j.id, 'mechanic', j.data ->> 'mechanic', 'time', j.data ->> 'time', 'durationMin', j.data -> 'durationMin',
        'status', coalesce(j.data ->> 'status', 'planifie'),
        'client', jsonb_build_object(
          'name', coalesce(nullif(j.data -> 'client' ->> 'name', ''), nullif(btrim(concat(j.data -> 'client' ->> 'firstName', ' ', j.data -> 'client' ->> 'lastName')), ''),
                           nullif(btrim(concat(c.data ->> 'firstName', ' ', c.data ->> 'lastName')), ''), c.data ->> 'name'),
          'address', coalesce(nullif(j.data -> 'client' ->> 'address', ''), c.data ->> 'address'),
          'geo', coalesce(j.data -> 'client' -> 'geo', c.data -> 'geo')),
        'services', j.data -> 'services') order by j.data ->> 'time')
      from public.docs j left join public.docs c on c.path = 'clients/' || (j.data ->> 'clientId')
      where j.col = 'jobs' and j.data ->> 'date' = d and coalesce(j.data ->> 'status', '') not in ('annule', 'noshow')), '[]'::jsonb),
    'live', coalesce((
      select jsonb_agg(jsonb_build_object('user_id', l.user_id, 'lat', l.lat, 'lon', l.lon, 'at', l.at, 'shift_started_at', l.shift_started_at, 'job_id', l.job_id))
      from public.mech_live l where l.on_shift and l.lat is not null), '[]'::jsonb),
    'members', coalesce((
      select jsonb_agg(jsonb_build_object('user_id', m.user_id, 'name', m.name, 'mechanic', m.mechanic, 'roles', m.roles))
      from public.members m where m.active), '[]'::jsonb),
    'tracks', coalesce((
      select jsonb_agg(jsonb_build_object('job_id', t.job_id, 'user_id', t.user_id, 'eta_at', t.eta_at, 'route', t.route, 'dest_lat', t.dest_lat, 'dest_lon', t.dest_lon))
      from public.tracks t where t.status = 'active' and t.expires_at > now()), '[]'::jsonb));
end $$;
revoke execute on function public.team_map(date) from public, anon;
grant execute on function public.team_map(date) to authenticated, service_role;
