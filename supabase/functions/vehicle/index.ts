// Décodage d'un VIN pour l'équipe du garage : on demande à la base publique et gratuite de la NHTSA (vPIC),
// côté serveur (pas de souci de navigateur), seulement pour une personne connectée du garage.
// POST { vin } -> { ok, vin, r: { ModelYear, Make, Model, Trim, ... } }
import { createClient } from 'npm:@supabase/supabase-js@2.118.0';

const SB_URL = Deno.env.get('SUPABASE_URL')!;
const SERVICE = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const VPIC = Deno.env.get('VPIC_BASE') || 'https://vpic.nhtsa.dot.gov';
const admin = createClient(SB_URL, SERVICE, { auth: { persistSession: false, autoRefreshToken: false } });
const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
const fail = (message: string, status = 400, error = 'bad_request') => json({ error, message }, status);
const KEEP = ['ModelYear', 'Make', 'Model', 'Trim', 'Series', 'DisplacementL', 'EngineCylinders', 'FuelTypePrimary', 'DriveType', 'BodyClass',
  'TransmissionStyle', 'EngineModel', 'ElectrificationLevel', 'PlantCountry', 'ErrorCode', 'ErrorText'];

async function member(req: Request) {
  const tok = (req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '');
  if (!tok) return null;
  const { data, error } = await admin.auth.getUser(tok);
  if (error || !data?.user) return null;
  const { data: m } = await admin.from('members').select('user_id').eq('user_id', data.user.id).eq('active', true).maybeSingle();
  return m;
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });
  if (req.method !== 'POST') return json({ error: 'method' }, 405);
  try {
    if (!(await member(req))) return fail('Connecte-toi avec un compte du garage.', 401, 'not_member');
    const body = await req.json().catch(() => ({}));
    const vin = String(body.vin || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
    if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) return fail('Un VIN a 17 lettres et chiffres (jamais I, O ou Q).');
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 10000);
    let j: any;
    try {
      const r = await fetch(`${VPIC}/api/vehicles/DecodeVinValues/${vin}?format=json`, { signal: ctl.signal, headers: { Accept: 'application/json' } });
      if (!r.ok) return fail(`La base des véhicules ne répond pas (HTTP ${r.status}).`, 502, 'vpic');
      j = await r.json();
    } finally { clearTimeout(t); }
    const src = (j && Array.isArray(j.Results) && j.Results[0]) || {};
    const out: Record<string, string> = {};
    for (const k of KEEP) out[k] = String(src[k] ?? '').trim();
    return json({ ok: true, vin, r: out });
  } catch (e) {
    const msg = (e as Error).name === 'AbortError' ? 'La base des véhicules ne répond pas.' : String((e as Error).message || e);
    return json({ error: 'server', message: msg }, 502);
  }
});
