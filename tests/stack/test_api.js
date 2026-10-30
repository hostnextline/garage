// API + rules test against the local Supabase copy (real Postgres, PostgREST, Auth, edge functions).
const { createClient } = require('@supabase/supabase-js');
const { execSync } = require('child_process');
const crypto = require('crypto');
const K = require('./keys.json');
const URL = 'http://127.0.0.1:54321';
let pass = 0, fail = 0;
function check(name, cond, extra){ if (cond){ pass++; } else { fail++; console.log('FAIL', name, extra !== undefined ? JSON.stringify(extra).slice(0, 400) : ''); } }
function psql(sql){ return execSync(`psql -h 127.0.0.1 -p 54322 -U postgres -Atq -c ${JSON.stringify(sql)}`).toString().trim(); }
const cli = () => createClient(URL, K.anon, { auth: { persistSession: false, autoRefreshToken: false } });
async function login(email, pw){ const c = cli(); const { data, error } = await c.auth.signInWithPassword({ email, password: pw }); if (error) throw new Error(email + ': ' + error.message); c._uid = data.user.id; return c; }
async function fn(c, name, body){ const { data, error } = await c.functions.invoke(name, { body }); if (error){ let j = null; try { j = await error.context.json(); } catch(e){} return { error: j || { message: error.message }, status: error.context && error.context.status }; } return data; }
const ghl = async (path, body) => (await fetch('http://127.0.0.1:9200' + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body || {}) })).json();

(async () => {
  // fresh start
  psql("truncate public.members, public.docs, public.docs_deleted, public.mech_live, public.mech_positions, public.tracks, public.setup_codes, public.app_secrets cascade; delete from auth.users;");
  await ghl('/__reset');
  const anon = cli();

  // ---- setup ----
  check('setup needed at start', (await anon.rpc('setup_needed')).data === true);
  let r = await fn(anon, 'members', { action: 'setup', code: 'NOPE', email: 'hassan@test.ca', password: 'motdepasse1', name: 'Hassan' });
  check('setup refused without code row', r.error && r.error.error === 'bad_code', r);
  const code = 'K7QX-M2PA-9TZC';
  psql(`insert into public.setup_codes (code_hash) values ('${crypto.createHash('sha256').update(code.replace(/-/g, '')).digest('hex')}')`);
  r = await fn(anon, 'members', { action: 'setup', code: 'k7qx m2pa 9tzc', email: 'Hassan@Test.ca', password: 'court', name: 'Hassan' });
  check('setup refuses short password', r.error && /8 caractères/.test(r.error.message), r);
  r = await fn(anon, 'members', { action: 'setup', code: 'k7qx m2pa 9tzc', email: 'Hassan@Test.ca', password: 'motdepasse1', name: 'Hassan Banho', mechanic: 'Hassan' });
  check('setup creates owner', r.ok === true, r);
  check('setup code consumed', psql('select count(*) from public.setup_codes') === '0');
  check('setup no longer needed', (await anon.rpc('setup_needed')).data === false);
  r = await fn(anon, 'members', { action: 'setup', code, email: 'pirate@test.ca', password: 'motdepasse1', name: 'Pirate' });
  check('second setup refused', r.error && r.error.error === 'already_setup', r);

  const owner = await login('hassan@test.ca', 'motdepasse1');
  r = await fn(owner, 'members', { action: 'create', email: 'bureau@test.ca', name: 'Lina Bureau', role: 'bureau', password: 'bureau1234' });
  check('create bureau', r.ok, r);
  r = await fn(owner, 'members', { action: 'create', email: 'saleh@test.ca', name: 'Saleh Haddad', role: 'mecano', mechanic: 'Saleh' });
  check('create mecano + temp password', r.ok && /^Garage-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(r.password), r);
  const salehPw = r.password, salehId = r.user_id;
  r = await fn(owner, 'members', { action: 'create', email: 'ali@test.ca', name: 'Ali', role: 'mecano', mechanic: 'Ali', password: 'alipass123' });
  check('create second mecano', r.ok, r);
  const aliId = r.user_id;
  r = await fn(owner, 'members', { action: 'create', email: 'x@test.ca', name: 'X', role: 'mecano' });
  check('mecano needs mechanic name', r.error && /mécano/.test(r.error.message), r);
  r = await fn(owner, 'members', { action: 'create', email: 'saleh2@test.ca', name: 'Saleh bis', role: 'mecano', mechanic: ' saleh ' });
  check('same mechanic twice refused', r.error && /déjà un compte/.test(r.error.message), r);
  r = await fn(owner, 'members', { action: 'create', email: 'saleh@test.ca', name: 'Dup', role: 'bureau' });
  check('same email refused', r.error && /déjà un compte/.test(r.error.message), r);
  check('failed create left no ghost user', psql("select count(*) from auth.users where email in ('saleh2@test.ca','x@test.ca')") === '0');

  const bureau = await login('bureau@test.ca', 'bureau1234');
  const saleh = await login('saleh@test.ca', salehPw);
  const ali = await login('ali@test.ca', 'alipass123');
  r = await fn(bureau, 'members', { action: 'list' });
  check('bureau cannot manage access', r.error && r.error.error === 'forbidden', r);
  r = await fn(saleh, 'members', { action: 'create', email: 'evil@test.ca', name: 'E', role: 'owner' });
  check('mecano cannot create accounts', r.error && r.error.error === 'forbidden', r);
  r = await fn(owner, 'members', { action: 'list' });
  check('owner lists 4 members with emails', r.ok && r.members.length === 4 && r.members.every(m => m.email), r);

  // ---- data ----
  const set = (c, path, data) => c.rpc('doc_set', { p_path: path, p_data: data });
  const merge = (c, path, patch) => c.rpc('doc_merge', { p_path: path, p_patch: patch });
  const del = (c, path) => c.rpc('doc_delete', { p_path: path });
  const rows = async (c, col) => { const { data, error } = await c.from('docs').select('path,data').eq('col', col); if (error) throw error; return data.map(x => x.path).sort(); };
  check('owner writes config', !(await set(owner, 'config/main', { biz: { name: 'Garage NextLine' }, mechanics: ['Saleh', 'Ali', 'Hassan'] })).error);
  check('bureau cannot write config', (await set(bureau, 'config/main', { biz: { name: 'Hack' } })).error?.code === '42501');
  check('mecano cannot write config', !!(await set(saleh, 'config/main', {})).error);
  check('config unchanged', psql("select data->'biz'->>'name' from public.docs where path='config/main'") === 'Garage NextLine');
  check('owner writes client c1', !(await set(owner, 'clients/c1', { firstName: 'Marie', lastName: 'Tremblay', phone: '514 555-0101', address: '4520 rue Saint-Denis, Montréal', postal: 'H2J 2L3', geo: { lat: 45.5265, lon: -73.5841 } })).error);
  check('bureau writes client c2', !(await set(bureau, 'clients/c2', { firstName: 'Paul', lastName: 'Roy', phone: '438-555-0202', address: '100 rue introuvable', postal: 'H1A 1A1' })).error);
  check('bureau writes client c3', !(await set(bureau, 'clients/c3', { firstName: 'Zoé', phone: '5145550303', address: '1 rue X', postal: 'H3B 1A1' })).error);
  check('bureau writes job j1 (Saleh)', !(await set(bureau, 'jobs/j1', { mechanic: 'Saleh', clientId: 'c1', client: { id: 'c1', firstName: 'Marie', name: 'Marie Tremblay', phone: '514 555-0101', geo: { lat: 45.5265, lon: -73.5841 } }, date: '2026-10-30', time: '14:00', status: 'planifie', invoice: { lines: [{ desc: 'Huile', qty: 1, price: 80 }], total: 92 } })).error);
  check('owner writes job j2 (Ali)', !(await set(owner, 'jobs/j2', { mechanic: 'Ali', clientId: 'c2', client: { name: 'Paul Roy', phone: '438-555-0202' }, status: 'planifie' })).error);
  check('owner writes job j3 (saleh, other case)', !(await set(owner, 'jobs/j3', { mechanic: ' saleh ', clientId: 'c2', client: { name: 'Paul Roy' }, status: 'planifie' })).error);
  check('owner writes job j4 (unassigned)', !(await set(owner, 'jobs/j4', { mechanic: '', clientId: 'c3', status: 'planifie' })).error);
  check('days by bureau', !(await set(bureau, 'days/2026-10-30', { open: '08:00' })).error);
  check('mecano cannot write days', !!(await set(saleh, 'days/2026-10-31', { open: '08:00' })).error);

  check('owner sees all jobs', JSON.stringify(await rows(owner, 'jobs')) === JSON.stringify(['jobs/j1', 'jobs/j2', 'jobs/j3', 'jobs/j4']));
  check('bureau sees all jobs', (await rows(bureau, 'jobs')).length === 4);
  check('Saleh sees only his jobs', JSON.stringify(await rows(saleh, 'jobs')) === JSON.stringify(['jobs/j1', 'jobs/j3']), await rows(saleh, 'jobs'));
  check('Ali sees only his job', JSON.stringify(await rows(ali, 'jobs')) === JSON.stringify(['jobs/j2']));
  check('Saleh sees only his clients', JSON.stringify(await rows(saleh, 'clients')) === JSON.stringify(['clients/c1', 'clients/c2']), await rows(saleh, 'clients'));
  check('Ali sees only c2', JSON.stringify(await rows(ali, 'clients')) === JSON.stringify(['clients/c2']));
  check('mecano reads config', (await rows(saleh, 'config')).length === 1);
  check('mecano reads days', (await rows(saleh, 'days')).length === 1);
  check('mecano cannot read meta', (await rows(saleh, 'meta')).length === 0);
  const a1 = await anon.from('docs').select('path');
  check('anon reads nothing', !!a1.error || a1.data.length === 0, a1);

  r = await merge(saleh, 'jobs/j1', { status: 'route', invoice: { paid: true, method: 'debit' } });
  check('Saleh updates his job (deep merge)', !r.error && r.data.status === 'route' && r.data.invoice.total === 92 && r.data.invoice.lines.length === 1 && r.data.invoice.paid === true, r);
  r = await merge(saleh, 'jobs/j1', { mechanic: 'Ali' });
  check('Saleh cannot hand job to Ali', !!r.error, r);
  check('j1 still Saleh', psql("select data->>'mechanic' from public.docs where path='jobs/j1'") === 'Saleh');
  r = await merge(saleh, 'jobs/j2', { status: 'termine' });
  check('Saleh cannot touch Ali job', !!r.error, r);
  check('j2 unchanged', psql("select data->>'status' from public.docs where path='jobs/j2'") === 'planifie');
  r = await set(saleh, 'jobs/jx', { mechanic: 'Ali', status: 'place' });
  check('mecano cannot create a job for Ali', !!r.error, r);
  r = await set(saleh, 'jobs/jq', { mechanic: 'Saleh', status: 'place', clientId: 'cq' });
  check('mecano creates his own job (facture sur place)', !r.error, r);
  r = await set(saleh, 'clients/cq', { firstName: 'Voisin', phone: '5145550404' });
  check('mecano creates a new client', !r.error, r);
  check('mecano sees new client through his job', (await rows(saleh, 'clients')).includes('clients/cq'));
  r = await del(saleh, 'jobs/jq');
  check('mecano still cannot delete his job', !!r.error, r);
  psql("delete from public.docs where path in ('jobs/jq','clients/cq')");
  r = await del(saleh, 'jobs/j1');
  check('mecano cannot delete a job', r.error && r.error.code === '42501', r);
  r = await merge(saleh, 'clients/c1', { notes: [{ id: 'n1', text: 'Chien dans la cour' }] });
  check('mecano adds note on his client', !r.error, r);
  r = await set(saleh, 'clients/c1', Object.assign(JSON.parse(psql("select data from public.docs where path='clients/c1'")), { phone: '514 555-0199' }));
  check('mecano edits his client fiche', !r.error, r);
  r = await merge(saleh, 'clients/c3', { notes: [] });
  check('mecano cannot touch other client', !!r.error, r);
  r = await merge(owner, 'jobs/nope', { a: 1 });
  check('update of missing doc refused', r.error && r.error.code === 'P0002', r);
  r = await del(owner, 'jobs/nope');
  check('delete of missing doc ok (false)', !r.error && r.data === false, r);

  // drafts
  check('Saleh draft', !(await set(saleh, 'data/users/' + saleh._uid + '/draft-booking', { a: 1 })).error);
  check('owner draft', !(await set(owner, 'data/users/' + owner._uid + '/draft-booking', { b: 2 })).error);
  check('owner cannot read Saleh draft', (await rows(owner, 'data/users/' + saleh._uid)).length === 0);
  check('Saleh reads his draft', (await rows(saleh, 'data/users/' + saleh._uid)).length === 1);
  check('Saleh cannot write in owner drafts', !!(await set(saleh, 'data/users/' + owner._uid + '/x', { c: 3 })).error);
  check('Saleh deletes his draft', (await del(saleh, 'data/users/' + saleh._uid + '/draft-booking')).data === true);

  // tombstones
  check('owner deletes j4', (await del(owner, 'jobs/j4')).data === true);
  const tb = await bureau.from('docs_deleted').select('path,col');
  check('deletion visible to bureau', !tb.error && tb.data.some(x => x.path === 'jobs/j4'), tb);
  const tbs = await saleh.from('docs_deleted').select('path,col');
  check('Saleh sees no draft tombstone of others', !tbs.data.some(x => x.col.indexOf('data/users/' + owner._uid) === 0));

  // invoice numbers
  const nums = await Promise.all(Array.from({ length: 20 }, (_, i) => ([owner, bureau, saleh, ali][i % 4]).rpc('next_invoice_number', { p_start: 1001 })));
  const ns = nums.map(x => x.data).sort((a, b) => a - b);
  check('20 parallel invoice numbers unique and in a row', nums.every(x => !x.error) && ns[0] === 1001 && ns[19] === 1020 && new Set(ns).size === 20, nums.map(x => x.error || x.data));
  check('anon cannot take invoice number', !!(await anon.rpc('next_invoice_number', { p_start: 1 })).error);
  check('meta cannot be written directly', !!(await set(owner, 'meta/invoices', { next: 1 })).error);

  // ---- shift and positions ----
  r = await saleh.rpc('report_position', { p_lat: 45.5, p_lon: -73.6 });
  check('position refused before shift', r.data && r.data.ok === false, r);
  check('no position stored off shift', psql('select count(*) from public.mech_positions') === '0');
  r = await saleh.rpc('shift_start');
  check('Saleh starts shift', !r.error && r.data.on_shift === true, r);
  r = await saleh.rpc('report_position', { p_lat: 45.5000, p_lon: -73.6000, p_acc: 8, p_speed: 0 });
  check('first position stored', r.data && r.data.ok && r.data.stored, r);
  r = await saleh.rpc('report_position', { p_lat: 45.50005, p_lon: -73.6000 });
  check('tiny move not stored again', r.data && r.data.ok && !r.data.stored, r);
  r = await saleh.rpc('report_position', { p_lat: 45.5010, p_lon: -73.6000 });
  check('110 m move stored', r.data && r.data.stored, r);
  r = await saleh.rpc('report_position', { p_lat: 95, p_lon: 0 });
  check('impossible position refused', !!r.error);
  check('owner sees Saleh live', (await owner.from('mech_live').select('*')).data.some(x => x.user_id === salehId && x.lat > 45.5));
  check('bureau sees Saleh path', (await bureau.from('mech_positions').select('*').eq('user_id', salehId)).data.length === 2);
  check('Ali does not see Saleh live', (await ali.from('mech_live').select('*')).data.length === 0);
  check('Ali does not see Saleh path', (await ali.from('mech_positions').select('*')).data.length === 0);
  check('mecano cannot write mech_live directly', !!(await saleh.from('mech_live').update({ lat: 1 }).eq('user_id', salehId).select()).error || psql(`select lat from public.mech_live where user_id='${salehId}'`) !== '1');
  check('mecano cannot insert positions directly', !!(await saleh.from('mech_positions').insert({ user_id: salehId, lat: 1, lon: 1 })).error);

  // ---- en route ----
  r = await fn(ali, 'en-route', { jobId: 'j1', action: 'start' });
  check('Ali cannot start Saleh job', r.error && r.error.error === 'forbidden', r);
  r = await fn(saleh, 'en-route', { jobId: 'j1', action: 'start', pos: { lat: 45.5010, lon: -73.6000, acc: 9 }, base: 'http://127.0.0.1:8088/' });
  check('Saleh start: ok, link, route', r.ok && /^http:\/\/127\.0\.0\.1:8088\/suivi\.html#t=[A-Za-z0-9_-]{20,}$/.test(r.link) && r.route && r.route.length > 5 && r.route_src === 'osm' && r.minutes > 0, r);
  check('no SMS key yet: status off + message ready', r.sms && r.sms.status === 'off' && /^Bonjour Marie, Saleh de Garage NextLine est en route vers chez vous : arrivée prévue vers \d{1,2} h \d{2} \(environ \d+ min\)\. Suivez son trajet en direct : http/.test(r.sms.body), r.sms);
  const tok = r.token;
  let t = (await anon.rpc('get_track', { p_token: tok })).data;
  check('client page data', t && t.status === 'active' && t.mech === 'Saleh' && t.client === 'Marie' && t.garage === 'Garage NextLine' && t.pos && Math.abs(t.pos.lat - 45.501) < 1e-6 && t.dest && t.route && t.route.length > 5, t);
  check('client page hides last name and phone', !JSON.stringify(t).includes('Tremblay') && !JSON.stringify(t).includes('555'));
  check('bad token gives nothing', (await anon.rpc('get_track', { p_token: 'x'.repeat(24) })).data === null);
  r = await fn(owner, 'members', { action: 'secrets-set', ghlToken: 'pit-good-token', ghlLocation: 'loc123' });
  check('owner saves GHL keys', r.ok && r.ghl && r.ghlToken === '…oken', r);
  check('keys not readable by API', (await owner.from('app_secrets').select('*')).error || (await owner.from('app_secrets').select('*')).data.length === 0);
  r = await fn(bureau, 'members', { action: 'secrets-set', ghlToken: 'x' });
  check('bureau cannot change keys', r.error && r.error.error === 'forbidden', r);
  r = await fn(saleh, 'en-route', { jobId: 'j1', action: 'start', pos: { lat: 45.5020, lon: -73.6000 }, base: 'http://127.0.0.1:8088/' });
  check('second press reuses the same link', r.ok && r.token === tok && r.reused, r);
  check('second press sends SMS now that keys exist', r.sms.status === 'sent', r.sms);
  let log = await (await fetch('http://127.0.0.1:9200/__log')).json();
  const up = log.find(x => x.path === '/contacts/upsert'), msg = log.find(x => x.path === '/conversations/messages');
  check('GHL contact upsert payload', up && up.version === '2021-07-28' && up.body.locationId === 'loc123' && up.body.phone === '+15145550199' && up.body.firstName === 'Marie' && up.body.lastName === 'Tremblay' && up.body.postalCode === 'H2J 2L3', up);
  check('GHL SMS payload', msg && msg.version === '2021-04-15' && msg.body.type === 'SMS' && msg.body.contactId === 'ct_0199' && msg.body.message.includes('suivi.html#t=' + tok), msg);
  r = await fn(saleh, 'en-route', { jobId: 'j1', action: 'start', pos: { lat: 45.5020, lon: -73.6000 } });
  check('third press: no duplicate SMS', r.sms.status === 'already', r.sms);
  check('only one SMS sent', (await (await fetch('http://127.0.0.1:9200/__log')).json()).filter(x => x.path === '/conversations/messages').length === 1);
  r = await fn(saleh, 'en-route', { jobId: 'j1', action: 'start', resend: true });
  check('resend on demand', r.sms.status === 'sent', r.sms);
  check('default link host when none given', r.link.indexOf('https://hostnextline.github.io/garage/equipe/suivi.html#t=') === 0, r.link);
  r = await fn(saleh, 'en-route', { jobId: 'j1', action: 'start', base: 'https://evil.example/' });
  check('foreign link address ignored', r.link.indexOf('https://hostnextline.github.io/garage/equipe/suivi.html#t=') === 0, r.link);
  r = await fn(saleh, 'en-route', { jobId: 'j1', action: 'start', base: 'https://hostnextline.github.io/garage/equipe/' });
  check('own site sub-folder accepted', r.link.indexOf('https://hostnextline.github.io/garage/equipe/suivi.html#t=') === 0, r.link);
  r = await fn(saleh, 'en-route', { jobId: 'j1', action: 'refresh', pos: { lat: 45.5100, lon: -73.5900 } });
  check('refresh within 45 s keeps route', r.ok && r.token === tok, r);
  r = await fn(saleh, 'en-route', { jobId: 'j1', action: 'refresh', pos: { lat: 45.5100, lon: -73.5900 }, force: true });
  check('forced refresh recomputes from new spot', r.ok && Math.abs(r.route[0][1] - 45.51) < 1e-6, r);

  // owner presses for Saleh's job without position → uses Saleh's live position
  check('owner adds j5 for Saleh', !(await set(owner, 'jobs/j5', { mechanic: 'Saleh', clientId: 'c1', client: { name: 'Marie Tremblay' }, status: 'planifie' })).error);
  r = await fn(owner, 'en-route', { jobId: 'j5', action: 'start' });
  check('office starts job using mechanic live position', r.ok && r.route && r.route.length > 2 && Math.abs(r.route[0][1] - 45.51) < 1e-6 && r.dest && r.dest.lat === 45.5265, r);
  check('j5 track follows Saleh', psql(`select user_id from public.tracks where job_id='j5'`) === salehId);
  r = await fn(owner, 'en-route', { jobId: 'j3', action: 'start' });
  check('unknown address: still a link, no route', r.ok && r.link && r.dest === null && r.route === null && r.sms.status === 'sent', r);
  check('j3 track follows Saleh', psql(`select user_id from public.tracks where job_id='j3'`) === salehId);
  // Ali's job: Ali not on shift → no position, no route, still a link
  r = await fn(owner, 'en-route', { jobId: 'j2', action: 'start' });
  check('no position yet: link without ETA', r.ok && r.route === null && /est en route vers chez vous\. Suivez/.test(r.sms.body), r);

  // GHL errors
  await ghl('/__reset', { fail: 'dnd' });
  r = await fn(owner, 'en-route', { jobId: 'j2', action: 'start', resend: true });
  check('GHL refusal is reported', r.sms.status === 'error' && /DND/.test(r.sms.error), r.sms);
  check('GHL error saved on track', psql("select sms_status from public.tracks where job_id='j2' and status='active'") === 'error');
  await ghl('/__reset');
  await fn(owner, 'members', { action: 'secrets-set', ghlToken: 'pit-bad' });
  r = await fn(owner, 'en-route', { jobId: 'j2', action: 'start', resend: true });
  check('bad GHL key message', r.sms.status === 'error' && /refuse la clé/.test(r.sms.error), r.sms);
  r = await fn(owner, 'members', { action: 'sms-test', phone: '514-555-0000' });
  check('sms-test reports bad key', r.error && /refuse la clé/.test(r.error.message), r);
  await fn(owner, 'members', { action: 'secrets-set', ghlToken: 'pit-good-token' });
  r = await fn(owner, 'members', { action: 'sms-test', phone: '514-555-0000' });
  check('sms-test ok', r.ok, r);
  r = await fn(owner, 'members', { action: 'sms-test', phone: '555-0000' });
  check('sms-test bad phone', r.error && /10 chiffres/.test(r.error.message), r);
  r = await fn(owner, 'members', { action: 'secrets' });
  check('secrets status masked', r.ok && r.ghl && r.ghlToken === '…oken' && r.ghlLocation === '…c123' && !JSON.stringify(r).includes('pit-good'), r);

  // end
  r = await fn(saleh, 'en-route', { jobId: 'j1', action: 'end', reason: 'arrived' });
  check('arrived closes link', r.ok && r.ended, r);
  t = (await anon.rpc('get_track', { p_token: tok })).data;
  check('client page after arrival: no position, no route', t.status === 'arrived' && !t.pos && !t.route && t.ended_at, t);
  psql(`update public.tracks set expires_at = now() - interval '1 minute' where job_id='j3' and status='active'`);
  const tok3 = psql(`select token from public.tracks where job_id='j3'`);
  t = (await anon.rpc('get_track', { p_token: tok3 })).data;
  check('expired link shows nothing live', t.status === 'expired' && !t.pos, t);

  // shift end hides position everywhere
  await saleh.rpc('shift_end');
  const lv = (await owner.from('mech_live').select('*').eq('user_id', salehId)).data[0];
  check('after shift: no live position', lv && lv.on_shift === false && lv.lat === null, lv);
  r = await saleh.rpc('report_position', { p_lat: 45.6, p_lon: -73.6 });
  check('after shift: positions refused', r.data.ok === false);

  // ---- access changes ----
  r = await fn(owner, 'members', { action: 'update', user_id: aliId, active: false });
  check('deactivate Ali', r.ok, r);
  check('Ali loses data access at once', (await rows(ali, 'jobs')).length === 0);
  let e = null; try { await login('ali@test.ca', 'alipass123'); } catch (x) { e = x; }
  check('Ali cannot log in', !!e && /banned/i.test(e.message), e && e.message);
  r = await fn(owner, 'members', { action: 'update', user_id: aliId, active: true });
  check('reactivate Ali', r.ok);
  const ali2 = await login('ali@test.ca', 'alipass123');
  check('Ali back', (await rows(ali2, 'jobs')).length === 1);
  r = await fn(owner, 'members', { action: 'password', user_id: aliId });
  check('reset password', r.ok && /^Garage-/.test(r.password), r);
  e = null; try { await login('ali@test.ca', 'alipass123'); } catch (x) { e = x; } check('old password refused', !!e);
  await login('ali@test.ca', r.password);
  r = await fn(owner, 'members', { action: 'update', user_id: owner._uid, role: 'bureau' });
  check('owner cannot demote self', r.error && /propre accès/.test(r.error.message), r);
  r = await fn(owner, 'members', { action: 'update', user_id: salehId, role: 'bureau', mechanic: '' });
  check('mecano -> bureau', r.ok, r);
  check('Saleh now sees all jobs', (await rows(saleh, 'jobs')).length === 4);
  r = await fn(owner, 'members', { action: 'update', user_id: salehId, role: 'mecano' });
  check('mecano without name refused', r.error && /nom du mécano/.test(r.error.message), r);
  r = await fn(owner, 'members', { action: 'update', user_id: salehId, role: 'mecano', mechanic: 'Saleh' });
  check('back to mecano', r.ok, r);
  const { error: ue } = await owner.from('members').update({ role: 'bureau' }).eq('user_id', owner._uid);
  check('last owner protected in database too', !!ue && /propriétaire/.test(ue.message), ue);
  const { data: su } = await saleh.from('members').update({ role: 'owner' }).eq('user_id', salehId).select();
  check('mecano cannot promote himself', (!su || su.length === 0) && psql(`select role from public.members where user_id='${salehId}'`) === 'mecano');
  r = await fn(owner, 'members', { action: 'remove', user_id: aliId });
  check('remove Ali', r.ok && r.members.length === 3, r);
  check('Ali auth user deleted', psql("select count(*) from auth.users where email='ali@test.ca'") === '0');
  r = await fn(owner, 'members', { action: 'remove', user_id: owner._uid });
  check('cannot remove self', r.error, r);

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('CRASH', e); process.exit(2); });
