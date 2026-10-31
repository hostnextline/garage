// Sauvegarde automatique : lit tout le carnet (sauf brouillons, positions GPS et clés) pour la copie de chaque nuit.
// Seule la clé de sauvegarde ouvre la porte : on garde seulement son empreinte SHA-256 (app_secrets.BACKUP_KEY_SHA256).
// POST { after?: string }  en-tête x-backup-key
//   -> { ok, at, rows: [{ path, data, updated_at }], next: string | null, counts?, members? }
import { createClient } from 'npm:@supabase/supabase-js@2.118.0';

const SB_URL = Deno.env.get('SUPABASE_URL')!;
const SERVICE = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const admin = createClient(SB_URL, SERVICE, { auth: { persistSession: false, autoRefreshToken: false } });
const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-backup-key',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
const PAGE = 25;   // les photos de reçus pèsent jusqu'à ~330 ko : 25 par page au plus

async function sha256(s: string) {
  const b = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)));
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
}
function same(a: string, b: string) {   // comparaison en temps constant
  if (a.length !== b.length) return false;
  let d = 0; for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });
  if (req.method !== 'POST') return json({ error: 'method' }, 405);
  try {
    const key = req.headers.get('x-backup-key') || '';
    const { data: s } = await admin.from('app_secrets').select('value').eq('name', 'BACKUP_KEY_SHA256').maybeSingle();
    if (!s?.value || key.length < 32 || !same(await sha256(key), s.value)) {
      await new Promise((r) => setTimeout(r, 400));
      return json({ error: 'not_allowed', message: 'Clé de sauvegarde absente ou mauvaise.' }, 401);
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
