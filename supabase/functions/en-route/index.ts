// « En route » : crée le lien de suivi, calcule l'itinéraire et texte le client (GoHighLevel).
// POST { jobId, action: 'start' | 'refresh' | 'end', pos?: {lat, lon, acc}, resend?: boolean, reason?: 'arrived' | 'cancelled', base?: string }
import { createClient } from 'npm:@supabase/supabase-js@2.118.0';

const SB_URL = Deno.env.get('SUPABASE_URL')!;
const SERVICE = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const GHL_BASE = Deno.env.get('GHL_BASE') || 'https://services.leadconnectorhq.com';
const OSRM_BASE = Deno.env.get('OSRM_BASE') || 'https://router.project-osrm.org';
const PHOTON_BASE = Deno.env.get('PHOTON_BASE') || 'https://photon.komoot.io';
const TOMTOM_BASE = Deno.env.get('TOMTOM_BASE') || 'https://api.tomtom.com';
const DEFAULT_BASE = Deno.env.get('TRACK_BASE') || 'https://hostnextline.github.io/garage/equipe/';
const UA = 'GarageMobile/1.0 (suivi en route)';

const admin = createClient(SB_URL, SERVICE, { auth: { persistSession: false, autoRefreshToken: false } });
const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
const norm = (s: unknown) => String(s ?? '').trim().toLowerCase();
type Pt = { lat: number; lon: number };
const okPt = (p: any): p is Pt => p && Number.isFinite(+p.lat) && Number.isFinite(+p.lon) && Math.abs(+p.lat) <= 90 && Math.abs(+p.lon) <= 180;

function meters(a: Pt, b: Pt) {
  const R = 6371000, r = Math.PI / 180, dLa = (b.lat - a.lat) * r, dLo = (b.lon - a.lon) * r;
  const h = Math.sin(dLa / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLo / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

async function caller(req: Request) {
  const tok = (req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '');
  if (!tok) return null;
  const { data, error } = await admin.auth.getUser(tok);
  if (error || !data?.user) return null;
  const { data: m } = await admin.from('members').select('*').eq('user_id', data.user.id).eq('active', true).maybeSingle();
  return m;
}
async function secrets() {
  const { data } = await admin.from('app_secrets').select('name,value');
  const s: Record<string, string> = {};
  (data || []).forEach((r: any) => { s[r.name] = r.value; });
  return {
    ghlToken: Deno.env.get('GHL_TOKEN') || s.GHL_TOKEN || '',
    ghlLocation: Deno.env.get('GHL_LOCATION_ID') || s.GHL_LOCATION_ID || '',
    tomtom: Deno.env.get('TOMTOM_KEY') || s.TOMTOM_KEY || '',
    base: s.TRACK_BASE || '',
  };
}

// keeps at most n points of a line (enough to draw it, light to send)
function thin(coords: [number, number][], n = 250) {
  if (coords.length <= n) return coords;
  const step = (coords.length - 1) / (n - 1), out: [number, number][] = [];
  for (let i = 0; i < n; i++) out.push(coords[Math.round(i * step)]);
  return out;
}
async function timed(url: string, init: RequestInit = {}, ms = 8000) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
  try { return await fetch(url, { ...init, signal: ctl.signal }); } finally { clearTimeout(t); }
}
// route: TomTom (traffic) when a key exists, otherwise OpenStreetMap (OSRM), otherwise a straight-line estimate
async function route(from: Pt, to: Pt, tomtom: string) {
  if (tomtom) {
    try {
      const r = await timed(`${TOMTOM_BASE}/routing/1/calculateRoute/${from.lat},${from.lon}:${to.lat},${to.lon}/json?key=${encodeURIComponent(tomtom)}&traffic=true&travelMode=car&routeType=fastest`);
      if (r.ok) {
        const j = await r.json(), rt = j.routes?.[0];
        const pts = (rt?.legs || []).flatMap((l: any) => l.points || []).map((p: any) => [p.longitude, p.latitude] as [number, number]);
        if (rt && pts.length) return { coords: thin(pts), km: rt.summary.lengthInMeters / 1000, minutes: rt.summary.travelTimeInSeconds / 60, src: 'tomtom' };
      }
    } catch (_) { /* next provider */ }
  }
  try {
    const r = await timed(`${OSRM_BASE}/route/v1/driving/${from.lon},${from.lat};${to.lon},${to.lat}?overview=full&geometries=geojson`, { headers: { 'User-Agent': UA } });
    if (r.ok) {
      const j = await r.json(), rt = j.routes?.[0];
      if (rt?.geometry?.coordinates?.length) return { coords: thin(rt.geometry.coordinates), km: rt.distance / 1000, minutes: (rt.duration / 60) * 1.25, src: 'osm' };
    }
  } catch (_) { /* straight line */ }
  const km = (meters(from, to) * 1.35) / 1000;
  return { coords: [[from.lon, from.lat], [to.lon, to.lat]] as [number, number][], km, minutes: (km / 30) * 60 + 3, src: 'estimate' };
}
async function geocode(address: string, tomtom: string): Promise<Pt | null> {
  if (!address) return null;
  try {
    if (tomtom) {
      const r = await timed(`${TOMTOM_BASE}/search/2/geocode/${encodeURIComponent(address)}.json?key=${encodeURIComponent(tomtom)}&countrySet=CA&limit=1`);
      if (r.ok) { const p = (await r.json()).results?.[0]?.position; if (p) return { lat: p.lat, lon: p.lon }; }
    }
    const r = await timed(`${PHOTON_BASE}/api/?q=${encodeURIComponent(address)}&limit=1&lang=fr&lat=45.52&lon=-73.6`, { headers: { 'User-Agent': UA } });
    if (r.ok) { const c = (await r.json()).features?.[0]?.geometry?.coordinates; if (c) return { lat: c[1], lon: c[0] }; }
  } catch (_) { /* no destination point */ }
  return null;
}

function e164(phone: string) {
  let d = String(phone || '').replace(/\D/g, '');
  if (d.length === 11 && d[0] === '1') d = d.slice(1);
  return d.length === 10 ? '+1' + d : '';
}
const hhmm = (d: Date) => new Intl.DateTimeFormat('fr-CA', { timeZone: 'America/Toronto', hour: 'numeric', minute: '2-digit' }).format(d).replace(/\s/g, ' ');

async function ghl(path: string, version: string, token: string, body: unknown) {
  const r = await timed(`${GHL_BASE}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, Version: version, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  }, 12000);
  const text = await r.text();
  let j: any = null; try { j = JSON.parse(text); } catch (_) { /* keep text */ }
  if (!r.ok) {
    const msg = (j && (Array.isArray(j.message) ? j.message.join(', ') : j.message || j.error)) || text.slice(0, 200) || `HTTP ${r.status}`;
    throw new Error(r.status === 401 || r.status === 403 ? `GoHighLevel refuse la clé (${msg})` : `GoHighLevel : ${msg}`);
  }
  return j || {};
}
export async function sendSms(cfg: { ghlToken: string; ghlLocation: string }, c: { first?: string; last?: string; phone: string; email?: string; address?: string; postal?: string }, message: string) {
  const phone = e164(c.phone);
  if (!phone) throw new Error('Numéro de téléphone du client invalide');
  const up = await ghl('/contacts/upsert', '2021-07-28', cfg.ghlToken, {
    locationId: cfg.ghlLocation, firstName: c.first || undefined, lastName: c.last || undefined, phone,
    email: c.email || undefined, address1: c.address || undefined, postalCode: c.postal || undefined,
    source: 'Garage mobile', tags: ['garage-mobile'],
  });
  const contactId = up.contact?.id || up.id;
  if (!contactId) throw new Error('GoHighLevel : contact non créé');
  const sent = await ghl('/conversations/messages', '2021-04-15', cfg.ghlToken, { type: 'SMS', contactId, message });
  return { contactId, messageId: sent.messageId || sent.id || null };
}

function token() {
  const b = new Uint8Array(18); crypto.getRandomValues(b);
  return btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });
  if (req.method !== 'POST') return json({ error: 'method' }, 405);
  try {
    const me = await caller(req);
    if (!me) return json({ error: 'not_member', message: 'Connecte-toi avec un compte du garage.' }, 401);
    const body = await req.json().catch(() => ({}));
    const jobId = String(body.jobId || '');
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(jobId)) return json({ error: 'bad_job' }, 400);
    const { data: jobRow } = await admin.from('docs').select('data').eq('path', 'jobs/' + jobId).maybeSingle();
    const job: any = jobRow?.data;
    if (!job) return json({ error: 'no_job', message: "Cette job n'existe plus." }, 404);
    const mine = me.mechanic && norm(job.mechanic) === norm(me.mechanic);
    if (me.role === 'mecano' && !mine) return json({ error: 'forbidden', message: "Cette job n'est pas à toi." }, 403);

    // whose position the client follows: the job's mechanic, otherwise the person who pressed the button
    let mech: any = me;
    if (job.mechanic && !mine) {
      const { data: ms } = await admin.from('members').select('*').eq('active', true).not('mechanic', 'is', null);
      mech = (ms || []).find((m: any) => norm(m.mechanic) === norm(job.mechanic)) || me;
    }
    const cfg = await secrets();
    const action = body.action || 'start';
    const { data: active } = await admin.from('tracks').select('*').eq('job_id', jobId).eq('status', 'active').maybeSingle();

    if (action === 'end') {
      const reason = body.reason === 'cancelled' ? 'cancelled' : 'arrived';
      if (active) await admin.from('tracks').update({ status: reason, ended_at: new Date().toISOString(), route: null }).eq('token', active.token);
      await admin.from('mech_live').update({ job_id: null }).eq('user_id', mech.user_id).eq('job_id', jobId);
      return json({ ok: true, ended: !!active, status: reason });
    }

    // where the mechanic is now
    let from: Pt | null = null;
    const pos = body.pos;
    if (okPt(pos) && mech.user_id === me.user_id) {
      from = { lat: +pos.lat, lon: +pos.lon };
      await admin.from('mech_live').update({ lat: from.lat, lon: from.lon, acc: pos.acc ?? null, at: new Date().toISOString(), job_id: jobId })
        .eq('user_id', me.user_id).eq('on_shift', true);
    } else {
      const { data: live } = await admin.from('mech_live').select('*').eq('user_id', mech.user_id).maybeSingle();
      if (live?.on_shift && okPt(live) && live.at && Date.now() - Date.parse(live.at) < 15 * 60000) from = { lat: live.lat, lon: live.lon };
      if (live?.on_shift) await admin.from('mech_live').update({ job_id: jobId }).eq('user_id', mech.user_id);
    }

    if (action === 'refresh') {
      if (!active) return json({ error: 'no_track', message: 'Le suivi est déjà fermé.' }, 404);
      if (!from || !okPt({ lat: active.dest_lat, lon: active.dest_lon })) return json({ ok: true, token: active.token, route: active.route, minutes: active.minutes, km: active.km, eta_at: active.eta_at });
      const fresh = active.route_at && Date.now() - Date.parse(active.route_at) < 45000;
      if (fresh && !body.force) return json({ ok: true, token: active.token, route: active.route, minutes: active.minutes, km: active.km, eta_at: active.eta_at, route_src: active.route_src });
      const r = await route(from, { lat: active.dest_lat, lon: active.dest_lon }, cfg.tomtom);
      const eta = new Date(Date.now() + r.minutes * 60000).toISOString();
      await admin.from('tracks').update({ route: r.coords, route_at: new Date().toISOString(), route_src: r.src, km: r.km, minutes: r.minutes, eta_at: eta }).eq('token', active.token);
      return json({ ok: true, token: active.token, route: r.coords, minutes: r.minutes, km: r.km, eta_at: eta, route_src: r.src });
    }

    // ---- start ----
    let client: any = job.client || {};
    if (job.clientId) {
      const { data: c } = await admin.from('docs').select('data').eq('path', 'clients/' + job.clientId).maybeSingle();
      if (c?.data) client = { ...client, ...c.data };
    }
    const first = String(client.firstName || String(client.name || '').split(' ')[0] || '').trim();
    const last = String(client.lastName || '').trim();
    const address = [client.address, client.postal].filter(Boolean).join(' ').trim();
    let dest: Pt | null = okPt(client.geo) ? { lat: +client.geo.lat, lon: +client.geo.lon } : null;
    if (!dest && active && okPt({ lat: active.dest_lat, lon: active.dest_lon })) dest = { lat: active.dest_lat, lon: active.dest_lon };
    if (!dest) dest = await geocode(address, cfg.tomtom);

    const { data: conf } = await admin.from('docs').select('data').eq('path', 'config/main').maybeSingle();
    const garage = String(conf?.data?.biz?.name || 'votre garage mobile').trim();
    const r = from && dest ? await route(from, dest, cfg.tomtom) : null;
    const now = Date.now();
    const eta = r ? new Date(now + r.minutes * 60000) : null;

    const tk = active?.token || token();
    const row = {
      token: tk, job_id: jobId, user_id: mech.user_id, mech_name: mech.name, client_first: first || null, garage,
      dest_lat: dest?.lat ?? null, dest_lon: dest?.lon ?? null, status: 'active', created_by: me.user_id,
      expires_at: new Date(now + 4 * 3600000).toISOString(),
      route: r?.coords ?? null, route_at: r ? new Date(now).toISOString() : null, route_src: r?.src ?? null,
      km: r?.km ?? null, minutes: r?.minutes ?? null, eta_at: eta ? eta.toISOString() : null,
    };
    if (active) await admin.from('tracks').update(row).eq('token', tk);
    else {
      const { error } = await admin.from('tracks').insert(row);
      if (error) return json({ error: 'track', message: "Le lien de suivi n'a pas pu être créé." }, 500);
    }

    // the link always points to the garage's own site (never to an address typed by someone else)
    const baseIn = String(body.base || '');
    let base = cfg.base || DEFAULT_BASE;
    try {
      const u = new URL(baseIn), allowed = [new URL(base).origin];
      if (/^[^\s?#]+\/$/.test(baseIn) && (allowed.includes(u.origin) || /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(u.origin))) base = baseIn;
    } catch (_) { /* default */ }
    const link = `${base}suivi.html#t=${tk}`;
    const mechFirst = String(mech.name || 'Votre mécano').trim().split(/\s+/)[0];
    const message = `Bonjour${first ? ' ' + first : ''}, ${mechFirst} de ${garage} est en route vers chez vous` +
      (eta ? ` : arrivée prévue vers ${hhmm(eta)} (environ ${Math.max(1, Math.round(r!.minutes))} min)` : '') +
      `. Suivez son trajet en direct : ${link}`;

    let sms: any = { status: 'off', body: message, phone: client.phone || '' };
    if (active && active.sms_status === 'sent' && !body.resend) sms = { status: 'already', body: message, phone: client.phone || '', at: active.sms_at };
    else if (cfg.ghlToken && cfg.ghlLocation) {
      try {
        const res = await sendSms(cfg, { first, last, phone: client.phone, email: client.email, address: client.address, postal: client.postal }, message);
        sms = { status: 'sent', body: message, phone: client.phone, messageId: res.messageId };
      } catch (e) {
        sms = { status: 'error', error: String((e as Error).message || e), body: message, phone: client.phone || '' };
      }
      await admin.from('tracks').update({ sms_status: sms.status, sms_error: sms.error || null, sms_at: new Date().toISOString() }).eq('token', tk);
    }
    return json({ ok: true, token: tk, link, dest, minutes: r?.minutes ?? null, km: r?.km ?? null, eta_at: row.eta_at, route: r?.coords ?? null, route_src: r?.src ?? null, sms, reused: !!active });
  } catch (e) {
    return json({ error: 'server', message: String((e as Error).message || e) }, 500);
  }
});
