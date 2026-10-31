// Équipe et accès : seulement le propriétaire (sauf « setup », qui crée le tout premier propriétaire avec un code à usage unique).
// POST { action: 'setup' | 'list' | 'create' | 'update' | 'password' | 'remove' | 'secrets' | 'secrets-set' | 'sms-test', ... }
import { createClient } from 'npm:@supabase/supabase-js@2.118.0';

const SB_URL = Deno.env.get('SUPABASE_URL')!;
const SERVICE = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const GHL_BASE = Deno.env.get('GHL_BASE') || 'https://services.leadconnectorhq.com';
const admin = createClient(SB_URL, SERVICE, { auth: { persistSession: false, autoRefreshToken: false } });
const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
const fail = (message: string, status = 400, error = 'bad_request') => json({ error, message }, status);
const ROLES = ['owner', 'bureau', 'mecano', 'tresorier'];
const clean = (s: unknown, n = 60) => String(s ?? '').replace(/\s+/g, ' ').trim().slice(0, n);
const emailOk = (e: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e);

async function caller(req: Request) {
  const tok = (req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '');
  if (!tok) return null;
  const { data, error } = await admin.auth.getUser(tok);
  if (error || !data?.user) return null;
  const { data: m } = await admin.from('members').select('*').eq('user_id', data.user.id).eq('active', true).maybeSingle();
  return m;
}
async function sha256(s: string) {
  const b = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)));
  return Array.from(b).map((x) => x.toString(16).padStart(2, '0')).join('');
}
// temporary password that is easy to read out loud: Garage-XXXX-XXXX
function tempPassword() {
  const A = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789', b = new Uint8Array(8); crypto.getRandomValues(b);
  const s = Array.from(b).map((x) => A[x % A.length]).join('');
  return `Garage-${s.slice(0, 4)}-${s.slice(4)}`;
}
function e164(phone: string) {
  let d = String(phone || '').replace(/\D/g, '');
  if (d.length === 11 && d[0] === '1') d = d.slice(1);
  return d.length === 10 ? '+1' + d : '';
}
async function ghl(path: string, version: string, token: string, body: unknown) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 12000);
  try {
    const r = await fetch(`${GHL_BASE}${path}`, { method: 'POST', signal: ctl.signal, headers: { Authorization: `Bearer ${token}`, Version: version, 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body) });
    const text = await r.text();
    let j: any = null; try { j = JSON.parse(text); } catch (_) { /* text */ }
    if (!r.ok) {
      const msg = (j && (Array.isArray(j.message) ? j.message.join(', ') : j.message || j.error)) || text.slice(0, 200) || `HTTP ${r.status}`;
      throw new Error(r.status === 401 || r.status === 403 ? `GoHighLevel refuse la clé (${msg})` : `GoHighLevel : ${msg}`);
    }
    return j || {};
  } finally { clearTimeout(t); }
}
async function secretMap() {
  const { data } = await admin.from('app_secrets').select('name,value,updated_at');
  const s: Record<string, any> = {};
  (data || []).forEach((r: any) => { s[r.name] = r; });
  return s;
}
const mask = (v?: string) => (v ? '…' + v.slice(-4) : '');

async function listMembers() {
  const { data: ms } = await admin.from('members').select('*').order('created_at');
  const out = [];
  for (const m of ms || []) {
    const { data } = await admin.auth.admin.getUserById(m.user_id);
    out.push({ ...m, email: data?.user?.email || '', last_sign_in_at: data?.user?.last_sign_in_at || null });
  }
  return out;
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });
  if (req.method !== 'POST') return json({ error: 'method' }, 405);
  try {
    const body = await req.json().catch(() => ({}));
    const action = String(body.action || '');

    // ---- very first owner, once, with the one-time code ----
    if (action === 'setup') {
      const { count } = await admin.from('members').select('user_id', { count: 'exact', head: true }).eq('role', 'owner').eq('active', true);
      if ((count || 0) > 0) return fail('Le garage a déjà un propriétaire. Connecte-toi.', 409, 'already_setup');
      const code = clean(body.code, 40).toUpperCase().replace(/[^A-Z0-9]/g, '');
      const email = clean(body.email, 120).toLowerCase(), password = String(body.password || ''), name = clean(body.name);
      if (!emailOk(email)) return fail('Courriel invalide.');
      if (password.length < 8) return fail('Le mot de passe doit avoir au moins 8 caractères.');
      if (!name) return fail('Écris ton nom.');
      const h = await sha256(code);
      const { data: used } = await admin.from('setup_codes').delete().eq('code_hash', h).gt('expires_at', new Date().toISOString()).select();
      if (!used?.length) return fail('Code de mise en route invalide ou expiré.', 403, 'bad_code');
      const { data: u, error } = await admin.auth.admin.createUser({ email, password, email_confirm: true, user_metadata: { name } });
      if (error || !u?.user) {
        await admin.from('setup_codes').insert({ code_hash: h, expires_at: used[0].expires_at });
        return fail(/already|exists|registered/i.test(error?.message || '') ? 'Ce courriel a déjà un compte.' : 'Le compte n\'a pas pu être créé : ' + (error?.message || ''), 400);
      }
      const { error: e2 } = await admin.from('members').insert({ user_id: u.user.id, role: 'owner', name, mechanic: clean(body.mechanic) || null });
      if (e2) { await admin.auth.admin.deleteUser(u.user.id); await admin.from('setup_codes').insert({ code_hash: h, expires_at: used[0].expires_at }); return fail('Le compte n\'a pas pu être créé : ' + e2.message, 500); }
      await admin.from('setup_codes').delete().neq('code_hash', '');
      return json({ ok: true });
    }

    const me = await caller(req);
    if (!me) return fail('Connecte-toi avec un compte du garage.', 401, 'not_member');
    if (me.role !== 'owner') return fail('Seul le propriétaire gère les accès.', 403, 'forbidden');

    if (action === 'list') return json({ ok: true, members: await listMembers() });

    if (action === 'create') {
      const email = clean(body.email, 120).toLowerCase(), name = clean(body.name), role = String(body.role || ''), mechanic = clean(body.mechanic) || null;
      if (!emailOk(email)) return fail('Courriel invalide.');
      if (!name) return fail('Écris le nom de la personne.');
      if (!ROLES.includes(role)) return fail('Choisis un rôle.');
      if (role === 'mecano' && !mechanic) return fail('Choisis le nom du mécano dans la liste.');
      const password = String(body.password || '') || tempPassword();
      if (password.length < 8) return fail('Le mot de passe doit avoir au moins 8 caractères.');
      const { data: u, error } = await admin.auth.admin.createUser({ email, password, email_confirm: true, user_metadata: { name } });
      if (error || !u?.user) return fail(/already|exists|registered/i.test(error?.message || '') ? 'Ce courriel a déjà un compte.' : 'Le compte n\'a pas pu être créé : ' + (error?.message || ''));
      const { error: e2 } = await admin.from('members').insert({ user_id: u.user.id, role, name, mechanic });
      if (e2) {
        await admin.auth.admin.deleteUser(u.user.id);
        return fail(/members_mechanic_uq/.test(e2.message) ? `${mechanic} a déjà un compte.` : 'Le compte n\'a pas pu être créé : ' + e2.message);
      }
      return json({ ok: true, user_id: u.user.id, password, members: await listMembers() });
    }

    const uid = String(body.user_id || '');
    if (['update', 'password', 'remove'].includes(action)) {
      const { data: m } = await admin.from('members').select('*').eq('user_id', uid).maybeSingle();
      if (!m) return fail('Cette personne n\'a plus de compte.', 404, 'no_member');

      if (action === 'update') {
        const up: Record<string, unknown> = {};
        if (body.name !== undefined) { const n = clean(body.name); if (!n) return fail('Écris le nom.'); up.name = n; }
        if (body.role !== undefined) { if (!ROLES.includes(body.role)) return fail('Rôle inconnu.'); up.role = body.role; }
        if (body.mechanic !== undefined) up.mechanic = clean(body.mechanic) || null;
        if (body.active !== undefined) up.active = !!body.active;
        if (uid === me.user_id && (up.active === false || (up.role && up.role !== 'owner'))) return fail('Tu ne peux pas retirer ton propre accès de propriétaire.');
        const { error } = await admin.from('members').update(up).eq('user_id', uid);
        if (error) return fail(/propriétaire/.test(error.message) ? 'Il faut garder au moins un propriétaire actif.' : /members_mechanic_uq/.test(error.message) ? 'Ce mécano a déjà un compte.' : /mecano_needs_mechanic/.test(error.message) ? 'Choisis le nom du mécano dans la liste.' : error.message);
        if (up.active !== undefined) {
          await admin.auth.admin.updateUserById(uid, { ban_duration: up.active ? 'none' : '876000h' } as any);
          if (!up.active) await admin.from('mech_live').update({ on_shift: false, shift_started_at: null, lat: null, lon: null, at: null, job_id: null }).eq('user_id', uid);
        }
        return json({ ok: true, members: await listMembers() });
      }
      if (action === 'password') {
        const password = String(body.password || '') || tempPassword();
        if (password.length < 8) return fail('Le mot de passe doit avoir au moins 8 caractères.');
        const { error } = await admin.auth.admin.updateUserById(uid, { password });
        if (error) return fail('Le mot de passe n\'a pas changé : ' + error.message);
        return json({ ok: true, password });
      }
      if (action === 'remove') {
        if (uid === me.user_id) return fail('Tu ne peux pas supprimer ton propre compte.');
        if (m.role === 'owner') {
          const { count } = await admin.from('members').select('user_id', { count: 'exact', head: true }).eq('role', 'owner').eq('active', true);
          if ((count || 0) <= 1 && m.active) return fail('Il faut garder au moins un propriétaire actif.');
        }
        const { error } = await admin.auth.admin.deleteUser(uid);
        if (error) return fail('Le compte n\'a pas été supprimé : ' + error.message);
        return json({ ok: true, members: await listMembers() });
      }
    }

    if (action === 'secrets') {
      const s = await secretMap();
      return json({ ok: true, ghl: !!(s.GHL_TOKEN && s.GHL_LOCATION_ID), ghlToken: mask(s.GHL_TOKEN?.value), ghlLocation: mask(s.GHL_LOCATION_ID?.value), tomtom: mask(s.TOMTOM_KEY?.value), updated_at: s.GHL_TOKEN?.updated_at || null });
    }
    if (action === 'secrets-set') {
      const pairs: [string, unknown][] = [['GHL_TOKEN', body.ghlToken], ['GHL_LOCATION_ID', body.ghlLocation], ['TOMTOM_KEY', body.tomtomKey]];
      for (const [name, v] of pairs) {
        if (v === undefined || v === null) continue;
        const val = String(v).trim();
        if (val.length > 400 || /\s/.test(val)) return fail('Une des clés a un format invalide (espaces ou trop longue).');
        if (!val) await admin.from('app_secrets').delete().eq('name', name);
        else await admin.from('app_secrets').upsert({ name, value: val, updated_at: new Date().toISOString() });
      }
      const s = await secretMap();
      return json({ ok: true, ghl: !!(s.GHL_TOKEN && s.GHL_LOCATION_ID), ghlToken: mask(s.GHL_TOKEN?.value), ghlLocation: mask(s.GHL_LOCATION_ID?.value), tomtom: mask(s.TOMTOM_KEY?.value) });
    }
    if (action === 'sms-test') {
      const s = await secretMap();
      if (!s.GHL_TOKEN || !s.GHL_LOCATION_ID) return fail('Ajoute d\'abord la clé et l\'identifiant du compte GoHighLevel.');
      const phone = e164(body.phone);
      if (!phone) return fail('Écris un numéro à 10 chiffres.');
      try {
        const up = await ghl('/contacts/upsert', '2021-07-28', s.GHL_TOKEN.value, { locationId: s.GHL_LOCATION_ID.value, firstName: clean(me.name).split(' ')[0] || 'Test', phone, source: 'Garage mobile', tags: ['garage-mobile', 'test'] });
        const contactId = up.contact?.id || up.id;
        if (!contactId) throw new Error('GoHighLevel : contact non créé');
        await ghl('/conversations/messages', '2021-04-15', s.GHL_TOKEN.value, { type: 'SMS', contactId, message: 'Test du garage mobile : les textos « en route » fonctionnent.' });
        return json({ ok: true });
      } catch (e) {
        return fail(String((e as Error).message || e), 502, 'sms_failed');
      }
    }
    return fail('Action inconnue.');
  } catch (e) {
    return json({ error: 'server', message: String((e as Error).message || e) }, 500);
  }
});
