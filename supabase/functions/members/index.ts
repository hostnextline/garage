// Équipe et accès : seulement le propriétaire (sauf « setup », qui crée le tout premier propriétaire avec un code à usage unique).
// POST { action: 'setup' | 'list' | 'create' | 'invite' | 'invite-resend' | 'update' | 'password' | 'remove' | 'secrets' | 'secrets-set' | 'sms-test', ... }
// Sans compte (lien d'invitation) : { action: 'invite-info' | 'invite-accept', token, password? }
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
// several roles per person (main role = owner > bureau > mecano > tresorier, set by the database) + rights for this person only
const PERM_KEYS = ['money', 'book', 'clients', 'factures', 'stock', 'agenda', 'editinv', 'hours_others', 'map', 'tresor'];
function rolesOf(body: any): string[] {
  const r = Array.isArray(body.roles) ? body.roles : body.role ? [body.role] : [];
  return [...new Set(r.map((x: unknown) => String(x)).filter((x: string) => ROLES.includes(x)))] as string[];
}
function permsOf(v: any): Record<string, boolean> | null {
  if (v === undefined || v === null) return null;
  const out: Record<string, boolean> = {};
  if (typeof v === 'object') for (const k of PERM_KEYS) if (typeof v[k] === 'boolean') out[k] = v[k];
  return out;
}
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

// ---------- invitations : le propriétaire écrit un courriel, la personne choisit son mot de passe avec le lien ----------
const DEFAULT_BASE = Deno.env.get('TRACK_BASE') || 'https://hostnextline.github.io/garage/equipe/';
const ROLE_FR: Record<string, string> = { owner: 'propriétaire', bureau: 'bureau', mecano: 'mécano', tresorier: 'trésorier' };
const INVITE_DAYS = 7;
function newToken(n = 24) {
  const b = new Uint8Array(n); crypto.getRandomValues(b);
  return btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function pickBase(baseIn: unknown, s: Record<string, any>) {
  let base = s.TRACK_BASE?.value || DEFAULT_BASE;
  const b = String(baseIn || '');
  try {
    const u = new URL(b);
    if (/^[^\s?#]+\/$/.test(b) && (u.origin === new URL(base).origin || /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(u.origin))) base = b;
  } catch (_) { /* default */ }
  return base;
}
async function garageName() {
  const { data } = await admin.from('docs').select('data').eq('path', 'config/main').maybeSingle();
  return String((data?.data as any)?.biz?.name || 'Garage mobile').trim();
}
/* The agenda's mechanics are the team's mechanics: each name comes from the person's account (never typed),
   and each mechanic has one truck. config/main keeps in step:
   - mechanics: the names with an account, plus names typed before that nobody has removed yet;
   - crewAccounts: the names that have an account;
   - trucks: a truck whose mechanic left is free again; assigning a mechanic to a truck takes him off his old one.
   Returns the trucks whose usual mechanic changed ({c1: 'Ali'}), so the app moves the coming appointments with them. */
const lc = (s: unknown) => String(s ?? '').trim().toLowerCase();
const DEF_TRUCKS = [{ id: 'c1', name: 'Camion 1', on: true, mech: '' }, { id: 'c2', name: 'Camion 2', on: false, mech: '' }, { id: 'c3', name: 'Camion 3', on: false, mech: '' }];
async function syncCrew(o: { assign?: { mech: string; truck: string }; drop?: string[] } = {}) {
  const { data: ms } = await admin.from('members').select('mechanic,created_at').not('mechanic', 'is', null).order('created_at');
  const accounts = ((ms || []) as any[]).map((m) => String(m.mechanic)).filter(Boolean);
  const drop = new Set((o.drop || []).map(lc));
  const { data: d } = await admin.from('docs').select('data').eq('path', 'config/main').maybeSingle();
  const cfg: any = d?.data || null;
  const cur: string[] = Array.isArray(cfg?.mechanics) ? cfg.mechanics.map(String).filter(Boolean) : [];
  const list: string[] = [];
  const push = (n: string) => { if (n && !drop.has(lc(n)) && !list.some((x) => lc(x) === lc(n))) list.push(n); };
  cur.forEach((n) => push(accounts.find((x) => lc(x) === lc(n)) || n));   // (the order already chosen stays)
  accounts.forEach(push);
  const moved: Record<string, string> = {};
  let trucks: any[] | null = Array.isArray(cfg?.trucks) ? cfg.trucks.map((t: any) => ({ ...t })) : null;
  let tChanged = false;
  if (!trucks && o.assign?.truck) { trucks = DEF_TRUCKS.map((t) => ({ ...t })); tChanged = true; }
  if (trucks) {
    trucks.forEach((t: any) => { if (t && t.mech && !list.some((x) => lc(x) === lc(t.mech))) { t.mech = ''; moved[t.id] = ''; tChanged = true; } });
    const a = o.assign;
    if (a && a.mech) trucks.forEach((t: any) => {
      if (!t) return;
      if (a.truck && t.id === a.truck) {
        if (lc(t.mech) !== lc(a.mech)) { t.mech = a.mech; moved[t.id] = a.mech; tChanged = true; }
        if (t.on === false) { t.on = true; tChanged = true; }   // (a truck that gets its mechanic goes into service)
      } else if (lc(t.mech) === lc(a.mech)) { t.mech = ''; moved[t.id] = ''; tChanged = true; }
    });
  }
  const patch: Record<string, unknown> = {};
  if (JSON.stringify(list) !== JSON.stringify(cur)) patch.mechanics = list;
  if (JSON.stringify(cfg?.crewAccounts || null) !== JSON.stringify(accounts)) patch.crewAccounts = accounts;
  if (tChanged) patch.trucks = trucks;
  if (!Object.keys(patch).length) return moved;
  patch.updatedAt = Date.now();
  if (!cfg) await admin.from('docs').insert({ path: 'config/main', data: patch });
  else { const { error } = await admin.rpc('doc_merge', { p_path: 'config/main', p_patch: patch }); if (error) console.error('syncCrew', error.message); }
  return moved;
}
/* a mechanic whose account is gone: his coming appointments, not started yet, wait for the truck's next mechanic */
const mtlDay = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
async function freeJobs(mech: unknown) {
  if (!lc(mech)) return 0;
  const { data } = await admin.from('docs').select('path,data').eq('col', 'jobs').eq('mech', lc(mech)).gte('data->>date', mtlDay());
  let n = 0;
  for (const r of (data || []) as any[]) {
    if ((r.data?.status || 'planifie') !== 'planifie') continue;
    const { error } = await admin.rpc('doc_merge', { p_path: r.path, p_patch: { mechanic: '', updatedAt: Date.now() } });
    if (!error) n++;
  }
  return n;
}
const mechTaken = (m: string) => `Un autre mécano s'appelle déjà « ${m} ». Ajoute l'initiale de son nom de famille (ex. : ${m} B.).`;
/* the truck chosen in the invitation or the card: '' = no truck; undefined = unchanged */
const truckOf = (b: any) => b.truck === undefined || b.truck === null ? undefined : clean(b.truck, 40);
const h = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' } as Record<string, string>)[c]);
function inviteMessageFr(o: { name: string; email: string; role: string; garage: string; by: string; link: string }) {
  const first = o.name.split(' ')[0] || o.name, role = String(o.role).split(',').map((r) => ROLE_FR[r] || r).join(' et ');
  const subject = `Ton accès au carnet de ${o.garage}`;
  const text = `Bonjour ${first},\n\n${o.by} t'a ajouté à l'équipe de ${o.garage} (${role}).\n\n` +
    `1. Active ton compte et choisis ton mot de passe avec ce lien (valide ${INVITE_DAYS} jours) :\n${o.link}\n\n` +
    `2. Mets l'app sur l'écran d'accueil de ton téléphone (l'app te le montre aussi, étape par étape) :\n` +
    `- iPhone (Safari) : bouton Partager (sur les iPhone récents : ••• à côté de l'adresse, puis Partager), puis « Sur l'écran d'accueil », puis « Ajouter ».\n` +
    `- Android (Chrome) : menu ⋮, puis « Installer l'application » (ou « Ajouter à l'écran d'accueil »).\n` +
    `Si le lien s'ouvre dans ton app de courriel, choisis d'abord « Ouvrir dans Safari » (iPhone) ou « Ouvrir dans Chrome » (Android).\n\n` +
    `3. Ouvre l'app avec la nouvelle icône Garage et connecte-toi une fois. Ensuite, elle se souvient de toi.\n\n` +
    `Ton courriel pour te connecter : ${o.email}\n`;
  const html = `<div style="font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.5;color:#1e1915;max-width:520px">` +
    `<p>Bonjour ${h(first)},</p><p>${h(o.by)} t'a ajouté à l'équipe de <b>${h(o.garage)}</b> (${h(role)}).</p>` +
    `<p><b>1. Active ton compte</b> et choisis ton mot de passe :</p>` +
    `<p><a href="${h(o.link)}" style="display:inline-block;background:#1e1915;color:#ffffff;text-decoration:none;font-weight:bold;padding:14px 22px;border-radius:12px">Activer mon compte</a></p>` +
    `<p style="font-size:13px;color:#6b5e55">Le lien est valide ${INVITE_DAYS} jours. S'il ne s'ouvre pas, copie cette adresse : ${h(o.link)}</p>` +
    `<p><b>2. Mets l'app sur ton téléphone</b> (elle s'ouvrira comme une vraie app ; l'app te le montre aussi, étape par étape) :</p>` +
    `<ul><li><b>iPhone (Safari)</b> : bouton Partager (sur les iPhone récents : <b>•••</b> à côté de l'adresse, puis Partager), puis « Sur l'écran d'accueil », puis « Ajouter ».</li>` +
    `<li><b>Android (Chrome)</b> : menu ⋮, puis « Installer l'application » (ou « Ajouter à l'écran d'accueil »).</li></ul>` +
    `<p style="font-size:13px;color:#6b5e55">Si le lien s'ouvre dans ton app de courriel, choisis d'abord « Ouvrir dans Safari » (iPhone) ou « Ouvrir dans Chrome » (Android).</p>` +
    `<p><b>3. Ouvre l'app avec la nouvelle icône Garage</b> et connecte-toi une fois. Ensuite, elle se souvient de toi.</p>` +
    `<p>Ton courriel pour te connecter : <b>${h(o.email)}</b></p></div>`;
  return { subject, text, html };
}
const ROLE_EN: Record<string, string> = { owner: 'owner', bureau: 'office', mecano: 'mechanic', tresorier: 'treasurer' };
function inviteMessageEn(o: { name: string; email: string; role: string; garage: string; by: string; link: string }) {
  const first = o.name.split(' ')[0] || o.name, role = String(o.role).split(',').map((r) => ROLE_EN[r] || r).join(' and ');
  const subject = `Your access to the ${o.garage} logbook`;
  const text = `Hello ${first},\n\n${o.by} added you to the ${o.garage} team (${role}).\n\n` +
    `1. Activate your account and choose your password with this link (valid ${INVITE_DAYS} days):\n${o.link}\n\n` +
    `2. Put the app on your phone's home screen (the app also shows you how, step by step):\n` +
    `- iPhone (Safari): Share button (on recent iPhones: ••• next to the address, then Share), then "Add to Home Screen", then "Add".\n` +
    `- Android (Chrome): menu ⋮, then "Install app" (or "Add to Home screen").\n` +
    `If the link opens inside your email app, first choose "Open in Safari" (iPhone) or "Open in Chrome" (Android).\n\n` +
    `3. Open the app with the new Garage icon and sign in once. After that, it remembers you.\n\n` +
    `Your email to sign in: ${o.email}\n`;
  const html = `<div style="font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.5;color:#1e1915;max-width:520px">` +
    `<p>Hello ${h(first)},</p><p>${h(o.by)} added you to the <b>${h(o.garage)}</b> team (${h(role)}).</p>` +
    `<p><b>1. Activate your account</b> and choose your password:</p>` +
    `<p><a href="${h(o.link)}" style="display:inline-block;background:#1e1915;color:#ffffff;text-decoration:none;font-weight:bold;padding:14px 22px;border-radius:12px">Activate my account</a></p>` +
    `<p style="font-size:13px;color:#6b5e55">The link is valid ${INVITE_DAYS} days. If it doesn't open, copy this address: ${h(o.link)}</p>` +
    `<p><b>2. Put the app on your phone</b> (it opens like a real app; the app also shows you how, step by step):</p>` +
    `<ul><li><b>iPhone (Safari)</b>: Share button (on recent iPhones: <b>•••</b> next to the address, then Share), then "Add to Home Screen", then "Add".</li>` +
    `<li><b>Android (Chrome)</b>: menu ⋮, then "Install app" (or "Add to Home screen").</li></ul>` +
    `<p style="font-size:13px;color:#6b5e55">If the link opens inside your email app, first choose "Open in Safari" (iPhone) or "Open in Chrome" (Android).</p>` +
    `<p><b>3. Open the app with the new Garage icon</b> and sign in once. After that, it remembers you.</p>` +
    `<p>Your email to sign in: <b>${h(o.email)}</b></p></div>`;
  return { subject, text, html };
}
function inviteMessage(o: { name: string; email: string; role: string; garage: string; by: string; link: string; lang?: string }) { return o.lang === 'en' ? inviteMessageEn(o) : inviteMessageFr(o); }
async function sendInvite(s: Record<string, any>, name: string, email: string, msg: { subject: string; text: string; html: string }) {
  if (!s.GHL_TOKEN || !s.GHL_LOCATION_ID) return { status: 'off' };
  try {
    const parts = name.trim().split(/\s+/);
    const up = await ghl('/contacts/upsert', '2021-07-28', s.GHL_TOKEN.value, { locationId: s.GHL_LOCATION_ID.value, firstName: parts[0] || undefined, lastName: parts.slice(1).join(' ') || undefined, email, source: 'Garage mobile', tags: ['garage-mobile', 'equipe'] });
    const contactId = up.contact?.id || up.id;
    if (!contactId) throw new Error('GoHighLevel : contact non créé');
    await ghl('/conversations/messages', '2021-04-15', s.GHL_TOKEN.value, { type: 'Email', contactId, subject: msg.subject, html: msg.html, message: msg.text });
    return { status: 'sent' };
  } catch (e) {
    return { status: 'error', error: String((e as Error).message || e) };
  }
}
/* a fresh link for this person (older unused links stop working) */
async function makeInvite(userId: string, email: string, by: string) {
  await admin.from('invites').delete().eq('user_id', userId).is('used_at', null);
  const token = newToken();
  const { error } = await admin.from('invites').insert({ token_hash: await sha256(token), user_id: userId, email, created_by: by, expires_at: new Date(Date.now() + INVITE_DAYS * 86400000).toISOString() });
  if (error) throw new Error('L\'invitation n\'a pas pu être créée : ' + error.message);
  return token;
}
async function inviteAndSend(me: any, m: { user_id: string; name: string; role: string; roles?: string[] }, email: string, baseIn: unknown, langIn?: unknown) {
  const lang = langIn === 'en' ? 'en' : 'fr';   // the language of the person who invites (what he sees in the app)
  const s = await secretMap();
  const token = await makeInvite(m.user_id, email, me.user_id);
  const link = pickBase(baseIn, s) + '#invite=' + token + '&l=' + lang;   // (the activation page opens in that language)
  const msg = inviteMessage({ name: m.name, email, role: (m.roles && m.roles.length ? m.roles : [m.role]).join(','), garage: await garageName(), by: String(me.name || (lang === 'en' ? 'The owner' : 'Le propriétaire')).split(' ')[0], link, lang });
  const mail = await sendInvite(s, m.name, email, msg);
  await admin.from('invites').update({ sent_by: mail.status === 'sent' ? 'courriel' : 'manuel' }).eq('token_hash', await sha256(token));
  return { link, mail, message: { subject: msg.subject, body: msg.text } };
}
async function inviteRow(token: unknown) {
  const t = String(token || '');
  if (!/^[A-Za-z0-9_-]{20,80}$/.test(t)) return null;
  const { data } = await admin.from('invites').select('*').eq('token_hash', await sha256(t)).maybeSingle();
  if (!data || data.used_at || Date.parse(data.expires_at) < Date.now()) return null;
  return data;
}
const STRIPE_BASE = Deno.env.get('STRIPE_BASE') || 'https://api.stripe.com';
// Stripe: the key stays here (never in the browser); saving it creates the « paid » notice (webhook) toward the client function
async function stripeCall(key: string, method: string, path: string, params?: [string, string][]) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 12000);
  try {
    const r = await fetch(`${STRIPE_BASE}/v1${path}`, { method, signal: ctl.signal, headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/x-www-form-urlencoded' }, body: params ? new URLSearchParams(params).toString() : undefined });
    const j: any = await r.json().catch(() => ({}));
    if (!r.ok) { const e: any = new Error(r.status === 401 ? 'Stripe refuse cette clé.' : 'Stripe : ' + (j?.error?.message || 'HTTP ' + r.status)); e.status = r.status; throw e; }
    return j;
  } finally { clearTimeout(t); }
}
function stripeStatus(s: Record<string, any>) {
  const k = s.STRIPE_KEY?.value || '';
  return { stripe: !!k, stripeKey: mask(k), stripeMode: /_test_/.test(k) ? 'test' : k ? 'live' : '', stripeHook: !!s.STRIPE_WEBHOOK_SECRET };
}

async function listMembers() {
  const { data: ms } = await admin.from('members').select('*').order('created_at');
  const { data: inv } = await admin.from('invites').select('user_id,created_at,expires_at,used_at,sent_by').order('created_at', { ascending: false });
  const out = [];
  for (const m of ms || []) {
    const { data } = await admin.auth.admin.getUserById(m.user_id);
    const last = (inv || []).find((x: any) => x.user_id === m.user_id);
    const signed = data?.user?.last_sign_in_at || null;
    const invite = last && !last.used_at && !signed ? { at: last.created_at, expires_at: last.expires_at, expired: Date.parse(last.expires_at) < Date.now(), sent_by: last.sent_by } : null;
    out.push({ ...m, email: data?.user?.email || '', last_sign_in_at: signed, invite });
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

    // ---- the invited person, with the secret link (no account yet) ----
    if (action === 'invite-info') {
      const row = await inviteRow(body.token);
      if (!row) return fail('Cette invitation n\'est plus valide (déjà utilisée ou plus de 7 jours). Demande au propriétaire de t\'en renvoyer une.', 404, 'bad_invite');
      const { data: m } = await admin.from('members').select('name,role,active').eq('user_id', row.user_id).maybeSingle();
      if (!m || !m.active) return fail('Ce compte n\'a plus accès au garage. Parle au propriétaire.', 403, 'no_access');
      return json({ ok: true, name: m.name, role: m.role, email: row.email, garage: await garageName() });
    }
    if (action === 'invite-accept') {
      const password = String(body.password || '');
      if (password.length < 8) return fail('Le mot de passe doit avoir au moins 8 caractères.');
      const row = await inviteRow(body.token);
      if (!row) return fail('Cette invitation n\'est plus valide (déjà utilisée ou plus de 7 jours). Demande au propriétaire de t\'en renvoyer une.', 404, 'bad_invite');
      const { data: m } = await admin.from('members').select('active').eq('user_id', row.user_id).maybeSingle();
      if (!m || !m.active) return fail('Ce compte n\'a plus accès au garage. Parle au propriétaire.', 403, 'no_access');
      // one use only: take the link first, give it back if the password could not be set
      const { data: took } = await admin.from('invites').update({ used_at: new Date().toISOString() }).eq('token_hash', row.token_hash).is('used_at', null).select();
      if (!took?.length) return fail('Cette invitation vient d\'être utilisée.', 409, 'bad_invite');
      const { error } = await admin.auth.admin.updateUserById(row.user_id, { password, email_confirm: true } as any);
      if (error) { await admin.from('invites').update({ used_at: null }).eq('token_hash', row.token_hash); return fail('Le mot de passe n\'a pas été enregistré : ' + error.message); }
      return json({ ok: true, email: row.email });
    }

    const me = await caller(req);
    if (!me) return fail('Connecte-toi avec un compte du garage.', 401, 'not_member');
    // a person deletes his own account (his jobs, invoices and clients stay in the garage's logbook)
    if (action === 'leave') {
      if (me.role === 'owner' || (Array.isArray(me.roles) && me.roles.includes('owner'))) {
        const { count } = await admin.from('members').select('user_id', { count: 'exact', head: true }).eq('role', 'owner').eq('active', true);
        if ((count || 0) <= 1) return fail("Tu es le seul propriétaire : donne d'abord le rôle de propriétaire à quelqu'un d'autre (Équipe et accès), puis supprime ton compte.", 400, 'last_owner');
      }
      const { error } = await admin.auth.admin.deleteUser(me.user_id);
      if (error) return fail('Le compte n\'a pas été supprimé : ' + error.message);
      if (me.mechanic) { await freeJobs(me.mechanic); await syncCrew({ drop: [me.mechanic] }); }
      return json({ ok: true });
    }
    if (me.role !== 'owner') return fail('Seul le propriétaire gère les accès.', 403, 'forbidden');

    if (action === 'list') { await syncCrew(); return json({ ok: true, members: await listMembers() }); }

    if (action === 'create') {
      const email = clean(body.email, 120).toLowerCase(), name = clean(body.name), roles = rolesOf(body), role = roles[0] || '', truck = truckOf(body), perms = permsOf(body.perms) || {};
      // the name in the agenda: the person's own name (or the name already in the agenda, picked in the list)
      const mechanic = clean(body.mechanic) || (roles.includes('mecano') || truck ? name : '') || null;
      if (!emailOk(email)) return fail('Courriel invalide.');
      if (!name) return fail('Écris le nom de la personne.');
      if (!roles.length) return fail('Choisis au moins un rôle.');
      const password = String(body.password || '') || tempPassword();
      if (password.length < 8) return fail('Le mot de passe doit avoir au moins 8 caractères.');
      const { data: u, error } = await admin.auth.admin.createUser({ email, password, email_confirm: true, user_metadata: { name } });
      if (error || !u?.user) return fail(/already|exists|registered/i.test(error?.message || '') ? 'Ce courriel a déjà un compte.' : 'Le compte n\'a pas pu être créé : ' + (error?.message || ''));
      const { error: e2 } = await admin.from('members').insert({ user_id: u.user.id, role, roles, perms, name, mechanic });
      if (e2) {
        await admin.auth.admin.deleteUser(u.user.id);
        return fail(/members_mechanic_uq/.test(e2.message) ? mechTaken(String(mechanic)) : 'Le compte n\'a pas pu être créé : ' + e2.message);
      }
      const moved = await syncCrew(mechanic && truck !== undefined ? { assign: { mech: mechanic, truck } } : {});
      return json({ ok: true, user_id: u.user.id, password, moved, members: await listMembers() });
    }

    if (action === 'invite') {
      const email = clean(body.email, 120).toLowerCase(), name = clean(body.name), roles = rolesOf(body), role = roles[0] || '', truck = truckOf(body), perms = permsOf(body.perms) || {};
      // the name in the agenda: the person's own name (or the name already in the agenda, picked in the list)
      const mechanic = clean(body.mechanic) || (roles.includes('mecano') || truck ? name : '') || null;
      if (!emailOk(email)) return fail('Courriel invalide.');
      if (!name) return fail('Écris le nom de la personne.');
      if (!roles.length) return fail('Choisis au moins un rôle.');
      // nobody knows this password: the person chooses one with the link
      const { data: u, error } = await admin.auth.admin.createUser({ email, password: newToken(24) + 'aA1!', email_confirm: true, user_metadata: { name } });
      if (error || !u?.user) return fail(/already|exists|registered/i.test(error?.message || '') ? 'Ce courriel a déjà un compte. Dans la liste, touche « Renvoyer l\'invitation » ou « Nouveau mot de passe ».' : 'L\'invitation n\'a pas pu être créée : ' + (error?.message || ''));
      const { error: e2 } = await admin.from('members').insert({ user_id: u.user.id, role, roles, perms, name, mechanic });
      if (e2) {
        await admin.auth.admin.deleteUser(u.user.id);
        return fail(/members_mechanic_uq/.test(e2.message) ? mechTaken(String(mechanic)) : 'L\'invitation n\'a pas pu être créée : ' + e2.message);
      }
      try {
        const r = await inviteAndSend(me, { user_id: u.user.id, name, role, roles }, email, body.base, body.lang);
        const moved = await syncCrew(mechanic && truck !== undefined ? { assign: { mech: mechanic, truck } } : {});
        return json({ ok: true, user_id: u.user.id, email, ...r, moved, members: await listMembers() });
      } catch (e) {
        await admin.auth.admin.deleteUser(u.user.id);
        await syncCrew();
        return fail(String((e as Error).message || e), 500);
      }
    }

    const uid = String(body.user_id || '');
    if (action === 'invite-resend') {
      const { data: m } = await admin.from('members').select('*').eq('user_id', uid).maybeSingle();
      if (!m) return fail('Cette personne n\'a plus de compte.', 404, 'no_member');
      const { data: au } = await admin.auth.admin.getUserById(uid);
      const { data: used } = await admin.from('invites').select('token_hash').eq('user_id', uid).not('used_at', 'is', null).limit(1);
      if (au?.user?.last_sign_in_at || used?.length) return fail('Cette personne a déjà activé son compte. Pour l\'aider, donne-lui un nouveau mot de passe.');
      const email = au?.user?.email || '';
      if (!email) return fail('Cette personne n\'a pas de courriel.');
      const r = await inviteAndSend(me, m, email, body.base, body.lang);
      return json({ ok: true, user_id: uid, email, ...r, members: await listMembers() });
    }
    if (['update', 'password', 'remove'].includes(action)) {
      const { data: m } = await admin.from('members').select('*').eq('user_id', uid).maybeSingle();
      if (!m) return fail('Cette personne n\'a plus de compte.', 404, 'no_member');

      if (action === 'update') {
        const up: Record<string, unknown> = {};
        if (body.name !== undefined) { const n = clean(body.name); if (!n) return fail('Écris le nom.'); up.name = n; }
        if (body.roles !== undefined || body.role !== undefined) { const rs = rolesOf(body); if (!rs.length) return fail('Choisis au moins un rôle.'); up.roles = rs; up.role = rs.includes('owner') ? 'owner' : rs.includes('bureau') ? 'bureau' : rs.includes('mecano') ? 'mecano' : 'tresorier'; }
        if (body.perms !== undefined) up.perms = permsOf(body.perms) || {};
        if (body.mechanic !== undefined) up.mechanic = clean(body.mechanic) || null;
        const truck = truckOf(body);
        if (body.active !== undefined) up.active = !!body.active;
        if (uid === me.user_id && (up.active === false || (up.role && up.role !== 'owner'))) return fail('Tu ne peux pas retirer ton propre accès de propriétaire.');
        const finalRoles = (up.roles as string[] | undefined) || m.roles || [m.role];
        let finalMech = up.mechanic !== undefined ? up.mechanic : m.mechanic;
        // a mechanic (or someone who gets a truck) is in the agenda under his own name; the name stays the same after, so his jobs stay his
        if (!finalMech && (finalRoles.includes('mecano') || truck)) finalMech = up.mechanic = (up.name as string) || m.name;
        const { error } = await admin.from('members').update(up).eq('user_id', uid);
        if (error) return fail(/propriétaire/.test(error.message) ? 'Il faut garder au moins un propriétaire actif.' : /members_mechanic_uq/.test(error.message) ? mechTaken(String(finalMech)) : /mecano_needs_mechanic/.test(error.message) ? 'Choisis le nom du mécano dans la liste.' : error.message);
        if (up.active !== undefined) {
          await admin.auth.admin.updateUserById(uid, { ban_duration: up.active ? 'none' : '876000h' } as any);
          if (!up.active) await admin.from('mech_live').update({ on_shift: false, shift_started_at: null, lat: null, lon: null, at: null, job_id: null }).eq('user_id', uid);
        }
        const moved = await syncCrew(finalMech && truck !== undefined ? { assign: { mech: String(finalMech), truck } } : {});
        return json({ ok: true, moved, members: await listMembers() });
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
        let moved = {};
        if (m.mechanic) { await freeJobs(m.mechanic); moved = await syncCrew({ drop: [m.mechanic] }); }
        return json({ ok: true, moved, members: await listMembers() });
      }
    }

    if (action === 'secrets') {
      const s = await secretMap();
      return json({ ok: true, ghl: !!(s.GHL_TOKEN && s.GHL_LOCATION_ID), ghlToken: mask(s.GHL_TOKEN?.value), ghlLocation: mask(s.GHL_LOCATION_ID?.value), tomtom: mask(s.TOMTOM_KEY?.value), updated_at: s.GHL_TOKEN?.updated_at || null, ...stripeStatus(s) });
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
      let warn = '';
      if (body.stripeKey !== undefined && body.stripeKey !== null) {
        const k = String(body.stripeKey).trim(), s0 = await secretMap(), now = new Date().toISOString();
        if (k && !/^(sk|rk)_(live|test)_[A-Za-z0-9]{10,}$/.test(k)) return fail('La clé Stripe commence par sk_live_ (ou rk_live_ pour une clé restreinte). La clé publique pk_… ne fonctionne pas ici.');
        let hook: any = null;
        if (k) {
          try {
            hook = await stripeCall(k, 'POST', '/webhook_endpoints', [['url', `${SB_URL}/functions/v1/client`], ['enabled_events[0]', 'checkout.session.completed'], ['enabled_events[1]', 'checkout.session.async_payment_succeeded'], ['description', 'Garage mobile : factures payées en ligne']]);
          } catch (e) {
            if ((e as any).status === 401) return fail('Stripe refuse cette clé. Copie la clé secrète (sk_live_…) dans Stripe → Développeurs → Clés API.', 400, 'stripe_key');
            warn = 'Clé enregistrée, mais Stripe n\'a pas créé l\'avis de paiement (' + (e as Error).message + '). Les paiements seront confirmés quand le client revient sur sa page.';
          }
        }
        if (s0.STRIPE_WEBHOOK_ID?.value && s0.STRIPE_KEY?.value) { try { await stripeCall(s0.STRIPE_KEY.value, 'DELETE', '/webhook_endpoints/' + encodeURIComponent(s0.STRIPE_WEBHOOK_ID.value)); } catch (_) { /* already gone */ } }
        await admin.from('app_secrets').delete().in('name', ['STRIPE_KEY', 'STRIPE_WEBHOOK_SECRET', 'STRIPE_WEBHOOK_ID']);
        if (k) {
          const rows = [{ name: 'STRIPE_KEY', value: k, updated_at: now }];
          if (hook?.secret && hook?.id) rows.push({ name: 'STRIPE_WEBHOOK_SECRET', value: hook.secret, updated_at: now }, { name: 'STRIPE_WEBHOOK_ID', value: hook.id, updated_at: now });
          await admin.from('app_secrets').insert(rows);
        }
      }
      const s = await secretMap();
      return json({ ok: true, ghl: !!(s.GHL_TOKEN && s.GHL_LOCATION_ID), ghlToken: mask(s.GHL_TOKEN?.value), ghlLocation: mask(s.GHL_LOCATION_ID?.value), tomtom: mask(s.TOMTOM_KEY?.value), ...stripeStatus(s), warn });
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
        await ghl('/conversations/messages', '2021-04-15', s.GHL_TOKEN.value, { type: 'SMS', contactId, message: body.lang === 'en' ? 'Mobile garage test: the "on the way" texts work.' : 'Test du garage mobile : les textos « en route » fonctionnent.' });
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
