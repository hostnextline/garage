-- Invitations par courriel : le propriétaire écrit un courriel, la personne reçoit un lien et choisit elle-même son mot de passe.
-- Rien n'est effacé : une seule table de plus, lue et écrite seulement par le serveur (fonction members).

create table if not exists public.invites (
  token_hash  text primary key check (length(token_hash) = 64),   -- sha256 du lien secret (le lien lui-même n'est jamais gardé)
  user_id     uuid not null references auth.users(id) on delete cascade,
  email       text not null,
  created_by  uuid,
  created_at  timestamptz not null default now(),
  expires_at  timestamptz not null default now() + interval '7 days',
  used_at     timestamptz,
  sent_by     text                                                 -- 'courriel' (GoHighLevel), 'manuel' (le propriétaire l'envoie lui-même)
);
create index if not exists invites_user on public.invites (user_id, created_at desc);
alter table public.invites enable row level security;

-- personne d'autre que le serveur : pas même un accès vide par l'API
revoke all on public.invites from anon, authenticated;
grant all on public.invites to service_role;
