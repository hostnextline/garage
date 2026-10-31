// Sauvegarde automatique : lit tout le carnet (sauf brouillons, positions GPS et clés) pour la copie de chaque nuit.
// Aucun mot de passe : GitHub signe chaque exécution de la sauvegarde (jeton OIDC), et on accepte seulement
// le dépôt privé hostnextline/garage-sauvegardes (vérifié par son numéro, qui ne change jamais), branche main.
// POST { after?: string }  en-tête x-gh-oidc: <jeton GitHub>
//   -> { ok, at, rows: [{ path, data, updated_at }], next: string | null, counts?, members? }
import { createClient } from 'npm:@supabase/supabase-js@2.118.0';
import { createRemoteJWKSet, jwtVerify } from 'npm:jose@5.9.6';

const SB_URL = Deno.env.get('SUPABASE_URL')!;
const SERVICE = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const ISSUER = Deno.env.get('GH_OIDC_ISSUER') || 'https://token.actions.githubusercontent.com';
const REPO = 'hostnextline/garage-sauvegardes';
const REPO_ID = '1441054755';
const OWNER_ID = '243496564';
const AUDIENCE = 'garage-sauvegarde';
const JWKS = createRemoteJWKSet(new URL(ISSUER + '/.well-known/jwks'));
const admin = createClient(SB_URL, SERVICE, { auth: { persistSession: false, autoRefreshToken: false } });
const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-gh-oidc',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
const PAGE = 25;   // les photos de reçus pèsent jusqu'à ~330 ko : 25 par page au plus

async function fromOurRepo(tok: string) {
  if (!tok) return false;
  try {
    const { payload: p } = await jwtVerify(tok, JWKS, { issuer: ISSUER, audience: AUDIENCE, algorithms: ['RS256'], clockTolerance: 30 });
    return p.repository === REPO && String(p.repository_id) === REPO_ID && String(p.repository_owner_id) === OWNER_ID && p.ref === 'refs/heads/main';
  } catch (_e) {
    return false;
  }
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });
  if (req.method !== 'POST') return json({ error: 'method' }, 405);
  try {
    if (!(await fromOurRepo(req.headers.get('x-gh-oidc') || ''))) {
      return json({ error: 'not_allowed', message: 'Seule la sauvegarde du dépôt privé du garage peut lire le carnet.' }, 401);
    }
    const body = await req.json().catch(() => ({}));
    const after = typeof body.after === 'string' ? body.after : '';
    const { data: rows, error } = await admin.from('docs').select('path,data,updated_at')
      .gt('path', after).not('path', 'like', 'data/%').order('path').limit(PAGE);
    if (error) return json({ error: 'db', message: error.message }, 500);
    const out: Record<string, unknown> = { ok: true, at: new Date().toISOString(), rows, next: rows.length === PAGE ? rows[rows.length - 1].path : null };
    if (!after) {   // première page : le nombre attendu par sorte, pour vérifier que rien ne manque, et l'équipe
      const { data: cols, error: e2 } = await admin.from('docs').select('col').not('path', 'like', 'data/%');
      if (e2) return json({ error: 'db', message: e2.message }, 500);
      const counts: Record<string, number> = {};
      for (const c of cols) counts[c.col] = (counts[c.col] || 0) + 1;
      const { data: ms } = await admin.from('members').select('user_id,role,name,mechanic,active,created_at').order('created_at');
      out.counts = counts; out.members = ms || [];
    }
    return json(out);
  } catch (e) {
    return json({ error: 'server', message: String((e as Error).message || e) }, 500);
  }
});
