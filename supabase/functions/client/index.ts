// La page du client (lien secret envoyé par texto) : voir sa facture, la payer par carte (Stripe Checkout),
// accepter ou refuser des travaux supplémentaires proposés par le mécano.
//
// Équipe (connecté)     POST { action:'link', jobId, send?:'facture'|'travaux'|'rdv', extraId?, base?, force? } -> { ok, token, link, sms }
//                       'rdv' : le texto de rendez-vous (date, bloc) avec le lien où il peut payer d'avance par carte ;
//                       une seule fois par date + bloc (un nouveau jour ou un nouveau bloc : un nouveau texto)
// Client (lien secret)  POST { action:'view'|'answer'|'pay'|'check', token, extraId?, accept? }
// Stripe (webhook)      POST avec l'en-tête Stripe-Signature (vérifié avec le secret créé à l'enregistrement de la clé)
import { createClient } from 'npm:@supabase/supabase-js@2.118.0';

const SB_URL = Deno.env.get('SUPABASE_URL')!;
const SERVICE = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const GHL_BASE = Deno.env.get('GHL_BASE') || 'https://services.leadconnectorhq.com';
const STRIPE_BASE = Deno.env.get('STRIPE_BASE') || 'https://api.stripe.com';
const DEFAULT_BASE = Deno.env.get('TRACK_BASE') || 'https://hostnextline.github.io/garage/equipe/';
const admin = createClient(SB_URL, SERVICE, { auth: { persistSession: false, autoRefreshToken: false } });
const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
const fail = (message: string, status = 400, error = 'bad_request') => json({ error, message }, status);
const norm = (s: unknown) => String(s ?? '').trim().toLowerCase();
const r2 = (n: number) => Math.round((+n || 0) * 100) / 100;
const money = (n: number, lang = 'fr') => new Intl.NumberFormat(lang === 'en' ? 'en-CA' : 'fr-CA', { style: 'currency', currency: 'CAD' }).format(r2(n)).replace(/\s/g, ' ');
const langOf = (c: any) => (c && c.lang === 'en' ? 'en' : 'fr');   // the language on the client's file (French unless set)
const todayTO = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Toronto', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());

async function timed(url: string, init: RequestInit = {}, ms = 12000) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
  try { return await fetch(url, { ...init, signal: ctl.signal }); } finally { clearTimeout(t); }
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
  return { ghlToken: s.GHL_TOKEN || '', ghlLocation: s.GHL_LOCATION_ID || '', stripeKey: s.STRIPE_KEY || '', stripeHook: s.STRIPE_WEBHOOK_SECRET || '', base: s.TRACK_BASE || '' };
}
async function docGet(path: string) {
  const { data } = await admin.from('docs').select('data').eq('path', path).maybeSingle();
  return (data?.data as any) || null;
}
async function docMerge(path: string, patch: unknown) {
  const { data, error } = await admin.rpc('doc_merge', { p_path: path, p_patch: patch });
  if (error) throw new Error(error.message);
  return data;
}

// ---------- GoHighLevel (same as « en route ») ----------
function e164(phone: string) {
  let d = String(phone || '').replace(/\D/g, '');
  if (d.length === 11 && d[0] === '1') d = d.slice(1);
  return d.length === 10 ? '+1' + d : '';
}
async function ghl(path: string, version: string, token: string, body: unknown) {
  const r = await timed(`${GHL_BASE}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, Version: version, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await r.text();
  let j: any = null; try { j = JSON.parse(text); } catch (_) { /* text */ }
  if (!r.ok) {
    const msg = (j && (Array.isArray(j.message) ? j.message.join(', ') : j.message || j.error)) || text.slice(0, 200) || `HTTP ${r.status}`;
    throw new Error(r.status === 401 || r.status === 403 ? `GoHighLevel refuse la clé (${msg})` : `GoHighLevel : ${msg}`);
  }
  return j || {};
}
async function sendSms(cfg: { ghlToken: string; ghlLocation: string }, c: any, message: string) {
  const phone = e164(c.phone);
  if (!phone) throw new Error('Numéro de téléphone du client invalide');
  const up = await ghl('/contacts/upsert', '2021-07-28', cfg.ghlToken, {
    locationId: cfg.ghlLocation, firstName: c.firstName || undefined, lastName: c.lastName || undefined, phone,
    email: c.email || undefined, source: 'Garage mobile', tags: ['garage-mobile'],
  });
  const contactId = up.contact?.id || up.id;
  if (!contactId) throw new Error('GoHighLevel : contact non créé');
  await ghl('/conversations/messages', '2021-04-15', cfg.ghlToken, { type: 'SMS', contactId, message });
}

// ---------- Stripe ----------
function form(o: Record<string, unknown>, pre = '', out: [string, string][] = []) {
  for (const [k, v] of Object.entries(o)) {
    if (v === undefined || v === null) continue;
    const key = pre ? `${pre}[${k}]` : k;
    if (typeof v === 'object') form(v as Record<string, unknown>, key, out); else out.push([key, String(v)]);
  }
  return out;
}
export async function stripeCall(key: string, method: string, path: string, params?: Record<string, unknown>) {
  const r = await timed(`${STRIPE_BASE}/v1${path}`, {
    method,
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params ? new URLSearchParams(form(params)).toString() : undefined,
  });
  const j: any = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(r.status === 401 ? 'Stripe refuse la clé' : `Stripe : ${j?.error?.message || 'HTTP ' + r.status}`);
  return j;
}
async function hmacHex(secret: string, msg: string) {
  const k = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = new Uint8Array(await crypto.subtle.sign('HMAC', k, new TextEncoder().encode(msg)));
  return Array.from(sig, (b) => b.toString(16).padStart(2, '0')).join('');
}
function same(a: string, b: string) { if (a.length !== b.length) return false; let d = 0; for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i); return d === 0; }
async function stripeSigOk(raw: string, header: string, secret: string) {
  if (!secret || !header) return false;
  const parts = header.split(',').map((p) => p.split('=')), t = parts.find((p) => p[0] === 't')?.[1] || '';
  const v1 = parts.filter((p) => p[0] === 'v1').map((p) => p[1] || '');
  if (!t || !v1.length || Math.abs(Date.now() / 1000 - +t) > 300) return false;
  const want = await hmacHex(secret, `${t}.${raw}`);
  return v1.some((s) => same(s, want));
}

const prepaidOf = (job: any) => (job?.prepaid && +job.prepaid.amount > 0 ? r2(+job.prepaid.amount) : 0);
const balanceOf = (job: any) => r2(Math.max(0, r2(job?.invoice?.total) - prepaidOf(job)));
// a paid Checkout Session → paid ahead (before the invoice), or the invoice is paid (once; a different amount is kept but flagged)
async function markPaid(jobId: string, s: any) {
  const job = await docGet('jobs/' + jobId);
  if (s.metadata?.kind === 'prepay') {
    if (job?.prepaid?.session === s.id) return { ok: true, already: true };
    const amt = r2((+s.amount_total || 0) / 100), at = Date.now();
    await docMerge('jobs/' + jobId, { prepaid: { amount: r2(prepaidOf(job) + amt), session: s.id, at, date: todayTO(), method: 'Carte (en ligne)' }, updatedAt: at });
    return { ok: true, prepaid: amt };
  }
  const inv = job?.invoice;
  if (!inv || !inv.number) return { ok: false, reason: 'no_invoice' };
  if (inv.stripe?.session === s.id && inv.stripe?.amount != null) return { ok: true, already: true };
  const cents = Math.round(balanceOf(job) * 100), got = +s.amount_total || 0, full = Math.abs(got - cents) <= 1;
  const patch: any = { invoice: { stripe: { session: s.id, amount: r2(got / 100), at: Date.now(), short: !full }, updatedAt: Date.now() }, updatedAt: Date.now() };
  if (full) Object.assign(patch.invoice, { paid: true, method: 'Carte (en ligne)', paidAt: todayTO() });
  await docMerge('jobs/' + jobId, patch);
  return { ok: true, full };
}

// ---------- links ----------
function newToken() {
  const b = new Uint8Array(18); crypto.getRandomValues(b);
  return btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
async function linkRow(token: string) {
  if (!/^[A-Za-z0-9_-]{20,64}$/.test(token)) return null;
  const { data } = await admin.from('client_links').select('*').eq('token', token).maybeSingle();
  if (!data || data.revoked || Date.parse(data.expires_at) < Date.now()) return null;
  return data;
}
function first(s: unknown) { return String(s || '').trim().split(/\s+/)[0] || ''; }
function vehicleLabel(v: any) { return [v?.year, v?.make, v?.model].filter(Boolean).join(' '); }

// the appointment: its block (8 h to 12 h…) or, booked by the hour, its time
const BLOCK_H: Record<string, [string, string]> = { am: ['08:00', '12:00'], pm: ['12:00', '16:00'], eve: ['16:00', '20:00'] };
function blockOfTime(t: string) { return t < '12:00' ? 'am' : t < '16:00' ? 'pm' : 'eve'; }
function when(job: any, conf: any) {
  if (conf?.bookMode === 'hours') return { from: '', to: '', at: String(job.time || '') };
  const b = BLOCK_H[String(job.block || '')] ? String(job.block) : blockOfTime(String(job.time || '08:00'));
  return { from: BLOCK_H[b][0], to: BLOCK_H[b][1], at: '' };
}
function hmTxt(t: string, en: boolean) {
  const [h, m] = String(t).split(':').map(Number);
  if (en) return (h % 12 || 12) + (m ? ':' + String(m).padStart(2, '0') : '') + (h < 12 ? ' AM' : ' PM');
  return h + ' h' + (m ? ' ' + String(m).padStart(2, '0') : '');
}
function dayTxt(iso: string, en: boolean) {
  const [y, mo, d] = String(iso).split('-').map(Number);
  return new Intl.DateTimeFormat(en ? 'en-CA' : 'fr-CA', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(y, mo - 1, d)));
}

// what the client may see: no internal notes, no other client, no team phone numbers
async function view(row: any, cfg?: any) {
  const job = await docGet('jobs/' + row.job_id);
  if (!job) return null;
  const conf = (await docGet('config/main')) || {};
  const biz = conf.biz || {};
  let client: any = job.client || {};
  if (job.clientId) { const c = await docGet('clients/' + job.clientId); if (c) client = { ...client, ...c }; }
  const inv = job.invoice && job.invoice.number ? job.invoice : null;
  cfg = cfg || await secrets();
  const pre = prepaidOf(job), q = !inv && job.quote && +job.quote.total > 0 ? job.quote : null, live = !['annule', 'noshow', 'termine'].includes(String(job.status || 'planifie'));
  const w = when(job, conf);
  return {
    ok: true,
    garage: { name: biz.name || 'Garage mobile', phone: biz.phone || '', email: biz.email || '', address: biz.address || '', taxIds: [biz.tps ? 'TPS ' + biz.tps : '', biz.tvq ? 'TVQ ' + biz.tvq : ''].filter(Boolean).join(' · '), footer: conf.footer || '' },
    client: { first: first(client.firstName || client.name), lang: langOf(client) },
    job: { date: job.date || '', vehicle: vehicleLabel(job.vehicle), mechanic: first(job.mechanic), status: String(job.status || 'planifie'), from: live ? w.from : '', to: live ? w.to : '', at: live ? w.at : '' },
    quote: q ? { lines: (q.lines || []).map((l: any) => ({ desc: l.desc, qty: l.qty, price: l.price, type: l.type })), sub: q.sub, tps: q.tps, tvq: q.tvq, total: q.total, taxesOn: q.taxesOn !== false } : null,
    prepaid: pre ? { amount: pre, date: job.prepaid.date || '' } : null,
    balance: inv ? balanceOf(job) : null,
    invoice: inv ? { number: inv.number, issuedAt: inv.issuedAt, lines: (inv.lines || []).map((l: any) => ({ desc: l.desc, qty: l.qty, price: l.price, type: l.type })),
      sub: inv.sub, tps: inv.tps, tvq: inv.tvq, total: inv.total, taxesOn: inv.taxesOn !== false, paid: !!inv.paid, method: inv.method || '', paidAt: inv.paidAt || null, note: inv.note || '',
      online: inv.stripe ? { amount: inv.stripe.amount, short: !!inv.stripe.short } : null } : null,
    extras: (Array.isArray(job.extras) ? job.extras : []).map((x: any) => ({ id: x.id, items: (x.items || []).map((i: any) => ({ desc: i.desc, price: i.price, qty: i.qty || 1 })), note: x.note || '', total: x.total, status: x.status || 'attente', at: x.at, answeredAt: x.answeredAt || null })),
    pay: !!(cfg.stripeKey && (inv ? !inv.paid && balanceOf(job) >= 0.5 : (q && !pre && live && +q.total >= 0.5))),
  };
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors });
  if (req.method !== 'POST') return json({ error: 'method' }, 405);
  try {
    // ---- Stripe tells us a payment went through ----
    const sigHeader = req.headers.get('stripe-signature');
    if (sigHeader) {
      const raw = await req.text(), cfg = await secrets();
      if (!(await stripeSigOk(raw, sigHeader, cfg.stripeHook))) return json({ error: 'bad_signature' }, 400);
      const ev = JSON.parse(raw);
      const { error: dup } = await admin.from('stripe_events').insert({ id: String(ev.id), type: String(ev.type) });
      if (dup) return json({ ok: true, duplicate: true });
      const s = ev.data?.object || {};
      if ((ev.type === 'checkout.session.completed' || ev.type === 'checkout.session.async_payment_succeeded') && s.payment_status === 'paid' && s.metadata?.job_id) {
        const r = await markPaid(String(s.metadata.job_id), s);
        return json({ ok: true, result: r });
      }
      return json({ ok: true, ignored: ev.type });
    }

    const body = await req.json().catch(() => ({}));
    const action = String(body.action || '');

    // ---- the team: make (or reuse) the client's link, and text it ----
    if (action === 'link') {
      const me = await caller(req);
      if (!me) return fail('Connecte-toi avec un compte du garage.', 401, 'not_member');
      if (me.role === 'tresorier') return fail('Le trésorier n\'envoie pas de liens aux clients.', 403, 'forbidden');
      const jobId = String(body.jobId || '');
      if (!/^[A-Za-z0-9_-]{1,80}$/.test(jobId)) return fail('Job invalide.');
      const job = await docGet('jobs/' + jobId);
      if (!job) return fail('Cette job n\'existe plus.', 404, 'no_job');
      if (me.role === 'mecano' && norm(job.mechanic) !== norm(me.mechanic)) return fail('Cette job n\'est pas à toi.', 403, 'forbidden');
      const send = body.send === 'facture' || body.send === 'travaux' || body.send === 'rdv' ? body.send : null;
      const extra = send === 'travaux' ? (job.extras || []).find((x: any) => x.id === body.extraId) : null;
      if (send === 'facture' && !(job.invoice && job.invoice.number)) return fail('Finalise la facture avant de l\'envoyer.');
      if (send === 'travaux' && !extra) return fail('Cette proposition n\'existe plus.');
      if (send === 'rdv' && (String(job.status || 'planifie') !== 'planifie' || String(job.date || '') < todayTO())) return fail('Ce rendez-vous est passé ou commencé : pas de texto de rendez-vous.');
      const cfg = await secrets();
      // the link always points to the garage's own site
      const baseIn = String(body.base || '');
      let base = cfg.base || DEFAULT_BASE;
      try {
        const u = new URL(baseIn);
        if (/^[^\s?#]+\/$/.test(baseIn) && (u.origin === new URL(base).origin || /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(u.origin))) base = baseIn;
      } catch (_) { /* default */ }
      const { data: cur } = await admin.from('client_links').select('*').eq('job_id', jobId).eq('revoked', false).gt('expires_at', new Date().toISOString()).order('created_at', { ascending: false }).limit(1);
      let row = cur?.[0];
      if (!row) {
        const ins = { token: newToken(), job_id: jobId, created_by: me.user_id, base, expires_at: new Date(Date.now() + 120 * 86400000).toISOString() };
        const { error } = await admin.from('client_links').insert(ins);
        if (error) return fail('Le lien n\'a pas pu être créé.', 500, 'link');
        row = ins;
      } else if (row.base !== base) { await admin.from('client_links').update({ base }).eq('token', row.token); row.base = base; }
      let client: any = job.client || {};
      if (job.clientId) { const c = await docGet('clients/' + job.clientId); if (c) client = { ...client, ...c }; }
      const lg = langOf(client), en = lg === 'en';
      const link = `${base}client.html#t=${row.token}&l=${lg}`;   // (the page opens in the client's language)
      if (!send) return json({ ok: true, token: row.token, link });

      const conf = (await docGet('config/main')) || {};
      const fn = first(client.firstName || client.name);
      const w = when(job, conf), rkey = [job.date, conf.bookMode === 'hours' ? job.time || '' : (w.from ? Object.keys(BLOCK_H).find((k) => BLOCK_H[k][0] === w.from) : '')].join('|');
      if (send === 'rdv' && job.rdvSms?.key === rkey && job.rdvSms?.status === 'sent' && !body.force) return json({ ok: true, token: row.token, link, sms: { status: 'already' } });
      const pre = prepaidOf(job), bal = job.invoice?.number ? balanceOf(job) : 0;
      const winTxt = (e: boolean) => w.from ? (e ? `between ${hmTxt(w.from, true)} and ${hmTxt(w.to, true)}` : `entre ${hmTxt(w.from, false)} et ${hmTxt(w.to, false)}`) : (e ? `at ${hmTxt(w.at, true)}` : `à ${hmTxt(w.at, false)}`);
      const moved = send === 'rdv' && job.rdvSms?.key && job.rdvSms.key !== rkey && job.rdvSms.status === 'sent';
      const payAhead = !!(cfg.stripeKey && job.quote && +job.quote.total >= 0.5 && !pre);
      const q = job.quote && +job.quote.total > 0 ? job.quote : null;   // the price told at booking (his invoice starts from it)
      const totTxt = (e: boolean) => q ? (e ? ` Expected total: ${money(q.total, 'en')}${q.taxesOn !== false ? ' (taxes included)' : ''}.` : ` Total prévu : ${money(q.total)}${q.taxesOn !== false ? ' (taxes incluses)' : ''}.`) : '';
      const garage = String(conf.biz?.name || (en ? 'your mobile garage' : 'votre garage mobile')).trim(), hi = (en ? 'Hello' : 'Bonjour') + (fn ? ' ' + fn : '');
      const message = send === 'rdv'
        ? (en
          ? `${hi}, your appointment with ${garage} ${moved ? 'has changed' : 'is confirmed'}: ${dayTxt(job.date, true)}, ${winTxt(true)}.${totTxt(true)} ${payAhead ? 'To see the details or pay ahead by card' : 'The details'}: ${link}`
          : `${hi}, votre rendez-vous avec ${garage} ${moved ? 'a changé' : 'est confirmé'} : ${dayTxt(job.date, false)}, ${winTxt(false)}.${totTxt(false)} ${payAhead ? 'Pour voir les détails ou payer d\'avance par carte' : 'Les détails'} : ${link}`)
        : en
        ? (send === 'facture'
          ? `${hi}, here is your invoice ${job.invoice.number} from ${garage} (${money(job.invoice.total, 'en')}${pre ? `, already paid ${money(pre, 'en')}: ${money(bal, 'en')} left` : ''}): ${link}` + (cfg.stripeKey && !job.invoice.paid && (!pre || bal >= 0.5) ? ' You can pay it online by card.' : '')
          : `${hi}, ${first(me.name) || 'your mechanic'} from ${garage} is proposing extra work on your ${vehicleLabel(job.vehicle) || 'vehicle'} (${money(extra.total, 'en')} before tax). To see it and accept or decline: ${link}`)
        : (send === 'facture'
          ? `${hi}, voici votre facture ${job.invoice.number} de ${garage} (${money(job.invoice.total)}${pre ? `, déjà payé ${money(pre)} : reste ${money(bal)}` : ''}) : ${link}` + (cfg.stripeKey && !job.invoice.paid && (!pre || bal >= 0.5) ? ' Vous pouvez la payer en ligne par carte.' : '')
          : `${hi}, ${first(me.name) || 'votre mécano'} de ${garage} propose des travaux supplémentaires sur votre ${vehicleLabel(job.vehicle) || 'véhicule'} (${money(extra.total)} avant taxes). Pour voir et accepter ou refuser : ${link}`);
      let sms: any = { status: 'off', body: message, phone: client.phone || '' };
      if (cfg.ghlToken && cfg.ghlLocation) {
        try { await sendSms(cfg, client, message); sms = { status: 'sent', body: message, phone: client.phone }; }
        catch (e) { sms = { status: 'error', error: String((e as Error).message || e), body: message, phone: client.phone || '' }; }
      }
      const at = Date.now();
      if (send === 'rdv') await docMerge('jobs/' + jobId, { rdvSms: { key: rkey, status: sms.status, at, error: sms.status === 'error' ? String(sms.error || '').slice(0, 200) : null }, updatedAt: at });
      else if (send === 'facture') await docMerge('jobs/' + jobId, { invoice: { sentAt: at, smsStatus: sms.status }, updatedAt: at });
      else await docMerge('jobs/' + jobId, { extras: (job.extras || []).map((x: any) => x.id === extra.id ? { ...x, sentAt: at, smsStatus: sms.status } : x), updatedAt: at });
      return json({ ok: true, token: row.token, link, sms });
    }

    // ---- the client, with the secret link ----
    const row = await linkRow(String(body.token || ''));
    if (!row) return fail('Ce lien n\'est plus valide. Demandez-en un nouveau au garage.', 404, 'no_link');

    if (action === 'view') {
      const v = await view(row);
      return v ? json(v) : fail('Ce dossier n\'existe plus.', 404, 'no_job');
    }
    if (action === 'answer') {
      const job = await docGet('jobs/' + row.job_id);
      const xs = Array.isArray(job?.extras) ? job.extras : [];
      const x = xs.find((e: any) => e.id === body.extraId);
      if (!x) return fail('Cette proposition n\'existe plus.', 404, 'no_extra');
      if ((x.status || 'attente') !== 'attente') return json({ ...(await view(row)), already: true });
      const at = Date.now();
      await docMerge('jobs/' + row.job_id, { extras: xs.map((e: any) => e.id === x.id ? { ...e, status: body.accept ? 'accepte' : 'refuse', answeredAt: at, answeredBy: 'lien' } : e), updatedAt: at });
      return json(await view(row));
    }
    if (action === 'pay') {
      const cfg = await secrets();
      if (!cfg.stripeKey) return fail('Le paiement en ligne n\'est pas offert par ce garage.', 400, 'no_stripe');
      const job = await docGet('jobs/' + row.job_id), inv = job?.invoice, en = body.lang === 'en';
      const conf = (await docGet('config/main')) || {}, gname = conf.biz?.name || (en ? 'Mobile garage' : 'Garage mobile');
      let cents = 0, name = '', meta: Record<string, string> = { job_id: row.job_id };
      if (inv?.number) {   // the invoice: what is left to pay
        if (inv.paid) return json({ ok: true, paid: true });
        cents = Math.round(balanceOf(job) * 100); name = `${en ? 'Invoice' : 'Facture'} ${inv.number} — ${gname}`; meta = { job_id: row.job_id, invoice: inv.number, kind: 'invoice' };
      } else {             // before the job: the price of the booking, paid ahead
        if (prepaidOf(job)) return json({ ok: true, paid: true });
        if (!job?.quote || ['annule', 'noshow', 'termine'].includes(String(job.status || 'planifie'))) return fail('La facture n\'est pas encore prête.');
        cents = Math.round(r2(job.quote.total) * 100); name = `${en ? 'Appointment' : 'Rendez-vous'} ${job.date} — ${gname}`; meta = { job_id: row.job_id, kind: 'prepay' };
      }
      if (cents < 50) return fail('Montant trop petit pour un paiement par carte.');
      const back = `${row.base}client.html#t=${row.token}&l=${en ? 'en' : 'fr'}`;   // (back from paying: the page in the same language)
      const s = await stripeCall(cfg.stripeKey, 'POST', '/checkout/sessions', {
        mode: 'payment', locale: en ? 'en' : 'fr-CA', client_reference_id: row.job_id,
        success_url: back + '&retour=paye', cancel_url: back,
        line_items: { 0: { quantity: 1, price_data: { currency: 'cad', unit_amount: cents, product_data: { name } } } },
        metadata: meta,
        payment_intent_data: { metadata: meta, description: name },
      });
      await admin.from('client_links').update({ last_session: s.id }).eq('token', row.token);
      return json({ ok: true, url: s.url });
    }
    if (action === 'check') {
      const cfg = await secrets();
      if (cfg.stripeKey && row.last_session) {
        try {
          const s = await stripeCall(cfg.stripeKey, 'GET', '/checkout/sessions/' + encodeURIComponent(row.last_session));
          if (s.payment_status === 'paid' && s.metadata?.job_id === row.job_id) await markPaid(row.job_id, s);
        } catch (_) { /* the webhook will do it */ }
      }
      return json(await view(row, cfg));
    }
    return fail('Action inconnue.');
  } catch (e) {
    return json({ error: 'server', message: String((e as Error).message || e) }, 500);
  }
});
