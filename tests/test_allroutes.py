"""Garage familial : chaque mécano voit toutes les routes et peut tout faire sur n'importe quelle job (copie locale de Supabase,
vraies écritures) :
1. les règles : Ali lit et change la job de Saleh, son client, ses photos ; reste fermé : les réglages, l'argent, l'équipe ;
2. « En route » : Ali part sur la job de Saleh (pour l'aider) → le client suit Ali ; le lien client aussi ;
3. son app : les puces des camions, sa route d'abord, puis celle de Saleh ; la job de Saleh avec « Je pars » et
   « C'est la job de Saleh : si tu pars, le client suivra ta position » ; tous les clients ;
4. en anglais."""
import json, os, time, datetime
from team_seed import *
from playwright.sync_api import sync_playwright
T0 = datetime.date.today(); TODAY = T0.isoformat()
def job(i): return doc('jobs/' + i) or {}
def get(tok, path): return http('GET', API + '/rest/v1/docs?select=path,data&path=eq.' + path, token=tok)
def bad(r): return isinstance(r, dict) and r.get('_status', 200) >= 400
otok, pw = seed()
c = doc('config/main'); c['trucks'] = [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': ''}, {'id': 'c2', 'name': 'Camion 2', 'on': True, 'mech': ''}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]
c['hours'] = {str(x): {'open': True, 'start': '07:00', 'end': '21:00'} for x in range(7)}
doc_set(otok, 'config/main', c)
doc_set(otok, 'photos/j1__1', {'job': 'j1', 'kind': 'avant', 'data': 'data:image/png;base64,AAAA'})
stok = token('saleh@garage.test', pw['saleh']); atok = token('ali@garage.test', pw['ali'])

# ---------- 1. the rules ----------
r = get(atok, 'jobs/j1')
check('Ali (mechanic) reads Saleh\'s job', isinstance(r, list) and len(r) == 1, r)
r = get(atok, 'clients/c1')
check('…and Saleh\'s client (Marie)', isinstance(r, list) and len(r) == 1, r)
r = get(atok, 'photos/j1__1')
check('…and its photos', isinstance(r, list) and len(r) == 1, r)
r = http('POST', API + '/rest/v1/rpc/doc_merge', {'p_path': 'jobs/j1', 'p_patch': {'notes': 'Ali passe aider'}}, atok)
check('Ali changes Saleh\'s job (a note): allowed', not bad(r) and job('j1').get('notes') == 'Ali passe aider', r)
http('POST', API + '/rest/v1/rpc/doc_merge', {'p_path': 'jobs/j1', 'p_patch': {'notes': ''}}, otok)
r = http('POST', API + '/rest/v1/rpc/doc_merge', {'p_path': 'clients/c1', 'p_patch': {'notes': 'Code de porte 12'}}, atok)
check('…and Saleh\'s client: allowed', not bad(r) and (doc('clients/c1') or {}).get('notes') == 'Code de porte 12', r)
http('POST', API + '/rest/v1/rpc/doc_merge', {'p_path': 'clients/c1', 'p_patch': {'notes': ''}}, otok)
r = doc_set(atok, 'config/main', dict(c, rate=1))
check('still closed for a mechanic: the settings', bad(r) and (doc('config/main') or {}).get('rate') == 120, r)
r = doc_set(atok, 'expenses/x1', {'total': 5})
check('…the garage\'s money (expenses)', bad(r), r)
r = get(atok, 'expenses/x1'); doc_set(otok, 'expenses/x2', {'total': 9}); r2 = get(atok, 'expenses/x2')
check('…cannot read the expenses either', isinstance(r2, list) and len(r2) == 0, r2)
r = doc_set(atok, 'days/' + TODAY, {'date': TODAY, 'closed': True})
check('…nor change the day\'s hours', bad(r), r)
psql("delete from public.docs where path = 'expenses/x2'")

# ---------- 2. « En route » on Saleh's job ----------
r = fn(atok, 'en-route', {'jobId': 'j1', 'action': 'start', 'self': True, 'notify': False, 'pos': {'lat': 45.52, 'lon': -73.58, 'acc': 9}, 'base': 'http://127.0.0.1:8088/'})
tk = psql("select coalesce(mech_name,'') || '|' || (select email from auth.users where id = user_id) from public.tracks where job_id = 'j1' and status = 'active'")
check('Ali goes on Saleh\'s job (« En route »): allowed, and the client follows Ali', r.get('ok') and tk == 'Ali Benali|ali@garage.test' or (r.get('ok') and tk.endswith('|ali@garage.test')), (r.get('error'), tk))
check('…without a text (« sans texto »), the tracking only', r.get('sms', {}).get('status') == 'quiet', r.get('sms'))
r = fn(atok, 'en-route', {'jobId': 'j1', 'action': 'end', 'reason': 'cancelled', 'self': True})
check('…he stops it', r.get('ok') and psql("select count(*) from public.tracks where job_id = 'j1' and status = 'active'") == '0', r)
r = fn(atok, 'client', {'action': 'link', 'jobId': 'j1'})
check('the client\'s link of Saleh\'s job, made by Ali: allowed', r.get('ok') and r.get('token'), r)
r = fn(otok, 'en-route', {'jobId': 'j1', 'action': 'start', 'notify': False, 'base': 'http://127.0.0.1:8088/'})
tk = psql("select (select email from auth.users where id = user_id) from public.tracks where job_id = 'j1' and status = 'active'")
check('the owner pressing for Saleh (office): the client follows Saleh, as before', r.get('ok') and tk == 'saleh@garage.test', (r.get('error'), tk))
fn(otok, 'en-route', {'jobId': 'j1', 'action': 'end', 'reason': 'cancelled'})

with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- 3. his app ----------
    http('POST', API + '/rest/v1/rpc/pick_truck', {'p_date': TODAY, 'p_truck': 'c2'}, atok)
    ac = ctx(b, phone=True); ap = page(ac, 'ali'); login(ap, 'ali@garage.test', pw['ali'])
    ap.goto(BASE + '#jour'); ap.wait_for_timeout(1500)
    chips = ap.evaluate("[...document.querySelectorAll('.chips.trucks [data-act=\"mech\"]')].map(b => [b.dataset.v, b.getAttribute('aria-pressed') || b.className])")
    check('Ali\'s day: the truck chips, his own (Camion 2, he picked it) first', [x[0] for x in chips] == ['', 'c1', 'c2', 'c3'] and ('true' in chips[2][1] or ' on' in chips[2][1]), chips)
    ids = ap.evaluate("[...document.querySelectorAll('.ph-job')].map(e => e.dataset.id)")
    check('…his route: his job (Paul), not Saleh\'s', 'j2' in ids and 'j1' not in ids, ids)
    ap.click('.chips.trucks [data-act="mech"][data-v="c1"]'); ap.wait_for_timeout(600)
    ids = ap.evaluate("[...document.querySelectorAll('.ph-job')].map(e => e.dataset.id)")
    check('touching « Camion 1 »: Saleh\'s route (Marie)', 'j1' in ids and 'j2' not in ids, ids)
    ap.click('.ph-job[data-id="j1"]'); ap.wait_for_timeout(700)
    nb = txt(ap, '.nextbtn')
    check('Saleh\'s job, on Ali\'s phone: « Je pars : aviser Marie » (he can go)', nb.startswith('Je pars'), nb)
    check('…« C\'est la job de Saleh : si tu pars, le client suivra ta position. »', 'si tu pars, le client suivra ta position' in txt(ap, '#main'), txt(ap, '#main')[:300])
    ap.screenshot(path=os.path.join(SC, 'allroutes_job.png'))
    ap.click('[data-act="back"]'); ap.wait_for_timeout(400)
    ap.click('.tab[data-t="clients"]'); ap.wait_for_timeout(800)
    cl = txt(ap, '#main')
    check('his clients: all of them (Marie, Saleh\'s client, too)', 'Marie' in cl and 'Paul' in cl, cl[:200])
    check('phone: no sideways scroll, no errors', no_hscroll(ap) and not ERRS, ERRS[:3])
    # ---------- 4. English ----------
    ec = ctx(b, phone=True); ec.add_init_script("try { localStorage.setItem('gm.lang', 'en'); } catch(e){}"); ep = page(ec, 'ali en'); login(ep, 'ali@garage.test', pw['ali'])
    ep.goto(BASE + '#jour'); ep.wait_for_timeout(1200)
    ep.click('.chips.trucks [data-act="mech"][data-v="c1"]'); ep.wait_for_timeout(500)
    ep.click('.ph-job[data-id="j1"]'); ep.wait_for_timeout(700)
    check('English: « This is Saleh\'s job: if you go, the client will follow your location. »', "if you go, the client will follow your location" in txt(ep, '#main'), txt(ep, '#main')[:300])
    check('English: no errors', not ERRS, ERRS[:3])
    b.close()
http('POST', API + '/rest/v1/rpc/pick_truck', {'p_date': TODAY, 'p_truck': ''}, atok)
summary()
