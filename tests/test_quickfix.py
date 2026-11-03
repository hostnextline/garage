"""Les corrections rapides, version équipe (copie locale de Supabase, vraies écritures) :
1. réglages : seulement ce qui a changé est envoyé, même hors ligne (ce que les autres ont changé reste) ;
2. bloc : la place est revérifiée par le serveur (deux réservations en même temps ; une faite hors ligne) ;
3. facture terminée sans réseau : « à numéroter », puis le prochain numéro de la série au retour du signal ;
4. synchro : plus de retéléchargement complet ; une job déplacée disparaît, un client devenu visible apparaît."""
import datetime, json, threading, urllib.parse
from team_seed import *
from playwright.sync_api import sync_playwright

T0 = datetime.date.today()
def next_day(wd_ok, start=2):
    d = T0 + datetime.timedelta(days=start)
    while not wd_ok(d.weekday()): d += datetime.timedelta(days=1)
    return d.isoformat()
D = next_day(lambda w: w < 5)
def cfgd(): return doc('config/main') or {}
def job(i): return doc('jobs/' + i) or {}
def rpc(tok, name, body): return http('POST', API + '/rest/v1/rpc/' + name, body, tok)
def merge(tok, path, patch): return rpc(tok, 'doc_merge', {'p_path': path, 'p_patch': patch})
def mark(key): v = psql("select n from public.block_marks where key = '%s'" % key); return int(v) if v else 0
def nxt(): return (doc('meta/invoices') or {}).get('next')
def setv(p, sel, v): p.evaluate("([s, v]) => { const e = document.querySelector(s); e.value = v; e.dispatchEvent(new Event('input', {bubbles:true})); e.dispatchEvent(new Event('change', {bubbles:true})); }", [sel, v])
def kind(u):
    q = urllib.parse.unquote(u)
    if 'select=id,updated_at' in q: return 'check'
    if 'select=id,data,updated_at' in q: return 'byid' if 'id=in.' in q else 'changes' if 'updated_at=gte' in q else 'full'
    return 'other'

otok, pw = seed()
ltok = token('lina@garage.test', pw['lina']); atok = token('ali@garage.test', pw['ali']); stok = token('saleh@garage.test', pw['saleh'])

with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- 1. the settings: only what was changed ----------
    c1 = ctx(b); c1.add_init_script('window.__allSettings = 1')   # (every settings section open at once)
    op = page(c1, 'owner'); login(op, 'hassan@garage.test', pw['hassan'])
    sent = []
    op.on('request', lambda r: sent.append((r.url.split('/rpc/')[-1], r.post_data)) if '/rest/v1/rpc/doc_' in r.url and r.method == 'POST' else None)
    op.goto(BASE + '#reglages'); op.wait_for_selector('#s-save', timeout=10000); op.wait_for_timeout(600)
    goal0 = cfgd().get('goal')
    op.fill('#s-rate', '135'); op.wait_for_timeout(300)        # Hassan is typing in the settings…
    tr = [dict(t) for t in cfgd()['trucks']]; tr[2]['name'] = 'Camion trois'
    merge(otok, 'config/main', {'lux': 'saphir', 'goal': 7777, 'trucks': tr})   # …meanwhile, from another device: colors, goal, a truck's name
    op.wait_for_timeout(1500); del sent[:]
    op.click('#s-save'); ok1 = toast_has(op, 'Réglages enregistrés'); op.wait_for_timeout(800)
    c = cfgd()
    check('settings saved: his change is there (rate 135 $)', ok1 and c.get('rate') == 135, c.get('rate'))
    check('…and what someone else changed meanwhile stays: the colors, the truck\'s name', c.get('lux') == 'saphir' and c['trucks'][2]['name'] == 'Camion trois', (c.get('lux'), c['trucks'][2]))
    check('…even a field of the same form he did not touch (the goal) is not put back to its old value', c.get('goal') == 7777, (goal0, c.get('goal')))
    ps = [json.loads(x[1]) for x in sent if x[0] == 'doc_patch']
    check('…only the changed part is sent (rate), not the whole settings', len(ps) == 1 and set(ps[0]['p_set']) == {'rate', 'updatedAt'} and not [x for x in sent if x[0] == 'doc_set'], [x[0] for x in sent] + [sorted(ps[0]['p_set']) if ps else None])
    # without network
    op.goto(BASE + '#reglages'); op.wait_for_selector('#s-save', timeout=10000); op.wait_for_timeout(600)
    c1.set_offline(True); op.wait_for_timeout(500)
    op.fill('#s-footer', 'Merci de votre confiance !'); op.wait_for_timeout(200)
    op.click('#s-save')
    check('without network: saved on the phone, sent when the signal is back', toast_has(op, 'envoyé au retour du signal'))
    merge(otok, 'config/main', {'rate': 150, 'lux': 'emeraude'})   # someone else, online, meanwhile
    c1.set_offline(False)
    back = wait_for(op, "window.__supa && window.__supa.pending() === 0", 25000); op.wait_for_timeout(800)
    c = cfgd()
    check('back online: his footer arrives…', back and c.get('footer') == 'Merci de votre confiance !', c.get('footer'))
    check('…without erasing what was changed meanwhile (rate 150 $, colors)', c.get('rate') == 150 and c.get('lux') == 'emeraude', (c.get('rate'), c.get('lux')))
    del sent[:]
    op.goto(BASE + '#reglages'); op.wait_for_selector('.lux-sw', state='attached', timeout=10000); op.wait_for_timeout(500)
    op.evaluate("document.querySelector('.lux-sw[data-v=\"bordeaux\"]').click()"); op.wait_for_timeout(1200)
    ps = [json.loads(x[1]) for x in sent if x[0] == 'doc_patch']
    check('the colors: only the colors are sent', cfgd().get('lux') == 'bordeaux' and len(ps) == 1 and set(ps[0]['p_set']) == {'lux', 'updatedAt'}, [sorted(p['p_set']) for p in ps])
    r = rpc(ltok, 'doc_patch', {'p_path': 'config/main', 'p_set': {'rate': 1}, 'p_unset': []})
    check('the office cannot change the settings this way either (same rights as before)', isinstance(r, dict) and r.get('_status') in (401, 403) and cfgd().get('rate') == 150, r)
    check('computer: no errors (settings)', not ERRS, ERRS[:3])

    # ---------- 2. a block: the room checked again by the server ----------
    c = cfgd(); c.pop('bookMode', None); c['homePostal'] = 'H4P 2B5'
    c['hours'] = {str(d): {'open': d != 0, 'start': '08:00', 'end': '20:00'} for d in range(7)}
    c['trucks'] = [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Camion 2', 'on': False, 'mech': 'Ali'}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]
    doc_set(otok, 'config/main', c)
    snapc = lambda n: {'id': 'c1', 'name': n, 'firstName': n, 'lastName': '', 'postal': 'H4P 2B5', 'phone': '514 555-0101'}
    for i in range(3): doc_set(otok, 'jobs/m%d' % i, {'date': D, 'time': '08:00', 'block': 'am', 'durationMin': 60, 'mechanic': '', 'truck': '', 'clientId': 'c1', 'client': snapc('Déjà %d' % i), 'services': ['Inspection'], 'status': 'planifie', 'createdAt': 5})
    for cid, pc in (('c1', 'H4P 2B5'), ('c2', 'H4P 2B6')):
        cl = doc('clients/' + cid); cl['postal'] = pc; doc_set(otok, 'clients/' + cid, cl)
    cA = ctx(b); cA.add_init_script("window.__syncCfg = {tick: 600000};")    # (this one hears of the others' bookings only when it asks)
    A = page(cA, 'owner-A'); login(A, 'hassan@garage.test', pw['hassan'])
    cB = ctx(b); B = page(cB, 'lina'); login(B, 'lina@garage.test', pw['lina'])
    def open_form(p, who):
        p.goto(BASE + '#agenda'); p.wait_for_timeout(600)
        p.click('#top [data-act="new"]'); p.wait_for_selector('#cs-q', timeout=8000)
        p.fill('#cs-q', who); p.wait_for_timeout(400); p.locator('#cs-results .crow').first.click(); p.wait_for_selector('#blkpick .blk', state='attached', timeout=8000)
        p.evaluate("(d) => { const t = document.getElementById('f-date'); t.value = d; t.dispatchEvent(new Event('change', {bubbles:true})); }", D); p.wait_for_timeout(600)
        p.evaluate("document.querySelector('#blkpick [data-v=\"am\"]').click()"); p.wait_for_timeout(300)
    open_form(A, 'Marie'); open_form(B, 'Paul')
    em = lambda p: p.inner_text('#blkpick [data-v="am"] em')
    check('two people book the last place of the morning at the same time (both forms say there is room)', A.input_value('#f-block') == 'am' and B.input_value('#f-block') == 'am' and em(A) != 'Complet' and em(B) != 'Complet', (em(A), em(B)))
    sr = A.evaluate("[...document.querySelectorAll('#sugbox .sug-road')].map(e => e.textContent)")
    check('the block picker shows the road time as an estimate only (« ≈ 5 min de route »), said not counted in the units', sr and all(re.match(r'^≈ (\d+ min|\d+ h( \d+)?) de route$', x) for x in sr) and 'pas compté dans tes unités' in txt(A, '#sugbox'), (sr, txt(A, '#sugbox')[-140:]))
    A.evaluate("() => { const T = window.__supa, f0 = T.fresh; window.__gate = new Promise(r => { window.__open = r; }); T.fresh = function(c){ return f0(c).then(() => window.__gate); }; }")
    A.evaluate("document.getElementById('jobform').requestSubmit()"); A.wait_for_timeout(1500)   # A counted the room… and is held there
    B.evaluate("document.getElementById('jobform').requestSubmit()"); B.wait_for_timeout(2500)   # B books meanwhile
    A.evaluate("window.__open()"); A.wait_for_timeout(3500)
    am = json.loads(psql("select coalesce(json_agg(data->'client'->>'name'), '[]') from public.docs where path like 'jobs/%%' and data->>'date' = '%s' and data->>'block' = 'am'" % D))
    check('only one of the two gets it (4 jobs of 60 min in the 4 h morning, not 5: no road time added)', len(am) == 4 and 'Paul Roy' in am and 'Marie Tremblay' not in am, am)
    check('…the other is told right away: « Ce bloc vient de se remplir »', 'vient de se remplir' in (A.inner_text('#formerr') if A.locator('#formerr').count() else ''), A.inner_text('#formerr') if A.locator('#formerr').count() else '')
    check('…his form now shows the morning « Complet » and stays open (nothing lost: another block, another day)', em(A) == 'Complet' and A.locator('#jobform').count() == 1, em(A))
    check('…the server counted one booking in that block', mark(D + '|am') == 1, mark(D + '|am'))
    A.evaluate("document.querySelector('#blkpick [data-v=\"pm\"]').click()"); A.wait_for_timeout(300)
    A.evaluate("document.getElementById('jobform').requestSubmit()"); A.wait_for_timeout(3000)
    pm = json.loads(psql("select coalesce(json_agg(data->'client'->>'name'), '[]') from public.docs where path like 'jobs/%%' and data->>'date' = '%s' and data->>'block' = 'pm'" % D))
    check('…he picks the afternoon: it passes at once', pm == ['Marie Tremblay'] and mark(D + '|pm') == 1, (pm, mark(D + '|pm')))
    # a booking made without network takes its place when the signal is back (the others count again then)
    open_form(B, 'Paul'); B.evaluate("document.querySelector('#blkpick [data-v=\"eve\"]').click()"); B.wait_for_timeout(300)
    cB.set_offline(True); B.wait_for_timeout(400)
    B.evaluate("document.getElementById('jobform').requestSubmit()")
    check('without network: the booking waits on the phone', toast_has(B, 'envoyé au retour du signal'))
    m0 = mark(D + '|eve'); cB.set_offline(False)
    wait_for(B, "window.__supa && window.__supa.pending() === 0", 25000); B.wait_for_timeout(1000)
    ev = json.loads(psql("select coalesce(json_agg(data->'client'->>'name'), '[]') from public.docs where path like 'jobs/%%' and data->>'date' = '%s' and data->>'block' = 'eve'" % D))
    check('…back online: it is saved, and the block\'s count moved (anyone booking there counts again)', ev == ['Paul Roy'] and m0 == 0 and mark(D + '|eve') == 1, (ev, m0, mark(D + '|eve')))
    # straight to the server
    jd = {'date': D, 'time': '08:00', 'block': 'am', 'durationMin': 60, 'mechanic': '', 'truck': '', 'clientId': 'c1', 'client': snapc('Test'), 'services': ['Inspection'], 'status': 'planifie'}
    r = rpc(otok, 'block_book', {'p_key': D + '|am', 'p_mark': 0, 'p_path': 'jobs/zz', 'p_data': jd, 'p_merge': False})
    check('server: a booking counted with an old count is refused (nothing written)', isinstance(r, dict) and r.get('ok') is False and r.get('mark') == 1 and not doc('jobs/zz'), r)
    r = rpc(atok, 'block_book', {'p_key': D + '|am', 'p_mark': None, 'p_path': 'jobs/zz', 'p_data': dict(jd, mechanic='Saleh', truck='c1'), 'p_merge': False})
    check('server: a mechanic cannot book a job for someone else this way (refused, the count does not move)', isinstance(r, dict) and r.get('_status') in (401, 403) and not doc('jobs/zz') and mark(D + '|am') == 1, r)
    r = rpc(ltok, 'block_book', {'p_key': 'pas-un-bloc', 'p_mark': None, 'p_path': 'jobs/zz', 'p_data': jd, 'p_merge': False})
    check('server: a block that does not exist is refused', isinstance(r, dict) and r.get('_status') == 400 and not doc('jobs/zz'), r)
    A.goto(BASE + '#agenda'); A.wait_for_timeout(500); A.evaluate("(d) => { const S = window.__garageApi.S; S.day = d; window.__garageApi.render(); }", D); A.wait_for_timeout(500)
    band = txt(A, '#bbar .bband[data-blk="am"]')
    check('the day\'s block bar: the morning full with 4 jobs, its road time shown apart (« ≈ … de route (estimé) »)', 'complet' in band and re.search(r'≈ (\d+ min|\d+ h( \d+)?) de route \(estimé\)', band) is not None, band)
    check('no errors (blocks)', not [e for e in ERRS if e.split(':')[0] in ('owner-A', 'lina')], ERRS[:3])
    for cx in (cA, cB): cx.close()

    # ---------- 3. an invoice finished without network ----------
    c3 = ctx(b, phone=True); sp = page(c3, 'saleh'); login(sp, 'saleh@garage.test', pw['saleh'])
    sp.evaluate("(id) => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = id; window.__garageApi.render(); }", 'j1'); sp.wait_for_timeout(700)
    c3.set_offline(True); sp.wait_for_timeout(400)
    sp.evaluate("document.querySelector('[data-act=\"invoice\"]').click()"); sp.wait_for_selector('#lines', state='attached', timeout=8000)
    sp.evaluate("[...document.querySelectorAll('[data-act=\"addsvc\"]')].filter(b => /huile/i.test(b.textContent))[0].click()"); sp.wait_for_timeout(300)
    sp.evaluate("document.getElementById('i-final').click()")
    check('finished without network: « son numéro arrive dès que le signal revient »', toast_has(sp, 'son numéro arrive dès que le signal revient'))
    sp.wait_for_timeout(600)
    no = txt(sp, '.inv-no')
    check('…the invoice says « À NUMÉROTER » (no more number made of the date and time)', 'À NUMÉROTER' in no and not re.search(r'F-\d{6}-\d{6}', sp.inner_text('main')), no)
    sp.evaluate("(id) => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = id; window.__garageApi.render(); }", 'j1'); sp.wait_for_timeout(500)
    sr = sp.evaluate("[...document.querySelectorAll('.sendrow')].map(e => e.textContent).join(' ')")
    check('…the job on his phone says « à numéroter »', 'à numéroter' in sp.evaluate("(document.querySelector('#inv-fold summary') || {}).textContent || ''"), sp.evaluate("(document.querySelector('#inv-fold summary') || {}).textContent || ''"))
    check('…it cannot be sent to the client before it has its number (the job says why)', sp.locator('[data-act="inv-send"]').count() == 0 and 'attend son numéro' in sr, sr)
    st = sp.evaluate("window.__garageApi.S.jobs.find(j => j.id === 'j1').status")
    check('…the job is « Terminé » all the same', st == 'termine', st)
    n0 = rpc(otok, 'next_invoice_number', {'p_start': 1})   # meanwhile, the office finishes another invoice: F-0001
    merge(otok, 'jobs/j2', {'invoice': {'lines': [{'type': 'forfait', 'desc': 'Inspection multipoints', 'qty': 1, 'price': 60}], 'sub': 60, 'tps': 3, 'tvq': 5.99, 'total': 68.99, 'number': 'F-%04d' % n0, 'issuedAt': TODAY, 'taxesOn': True, 'paid': False}, 'status': 'termine'})
    c3.set_offline(False)
    got = wait_for(sp, "(() => { const j = window.__garageApi.S.jobs.find(j => j.id === 'j1'); return j && j.invoice && j.invoice.number; })()", 30000)
    inv = job('j1').get('invoice') or {}
    check('back online: the next number of the series (F-0002, after the office\'s F-0001)', got and n0 == 1 and inv.get('number') == 'F-0002' and 'toNumber' not in inv, inv)
    sp.evaluate("(id) => { const S = window.__garageApi.S; S.screen = 'preview'; S.jobId = id; window.__garageApi.render(); }", 'j1'); sp.wait_for_timeout(500)
    check('…shown on his phone (the invoice: F-0002)', wait_for(sp, "document.querySelector('.inv-no') && document.querySelector('.inv-no').textContent.includes('F-0002')", 8000), txt(sp, '.inv-no'))
    sp.evaluate("(id) => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = id; window.__garageApi.render(); }", 'j1'); sp.wait_for_timeout(500)
    check('…no number lost or used twice (the next one is 3)', nxt() == 3, nxt())
    check('…now it can be sent', wait_for(sp, "!!document.querySelector('[data-act=\"inv-send\"]')", 8000))
    # two devices asking at the same moment: one number only
    pend = {'date': TODAY, 'time': '09:00', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'status': 'termine',
            'invoice': {'lines': [{'type': 'forfait', 'desc': 'Inspection', 'qty': 1, 'price': 50}], 'sub': 50, 'tps': 2.5, 'tvq': 4.99, 'total': 57.49, 'number': None, 'toNumber': True, 'issuedAt': TODAY, 'paid': False}}
    doc_set(otok, 'jobs/k1', pend)
    out = {}
    th = [threading.Thread(target=lambda t, k: out.__setitem__(k, rpc(t, 'number_invoice', {'p_path': 'jobs/k1'})), args=(t, k)) for t, k in ((otok, 'owner'), (ltok, 'lina'), (stok, 'saleh'))]
    [t.start() for t in th]; [t.join() for t in th]
    check('three devices number the same invoice at the same moment: all get the same number, only one is used', len(set(out.values())) == 1 and list(out.values())[0] == 'F-0003' and nxt() == 4, (out, nxt()))
    doc_set(otok, 'jobs/k2', dict(pend, invoice=dict(pend['invoice'], toNumber=False)))
    r = rpc(otok, 'number_invoice', {'p_path': 'jobs/k2'})
    check('a draft (not finished) gets no number', isinstance(r, dict) and r.get('_status') == 400 and nxt() == 4, r)
    doc_set(otok, 'jobs/k3', pend)
    r = rpc(atok, 'number_invoice', {'p_path': 'jobs/k3'})
    check('another mechanic cannot number Saleh\'s invoice (and no number is used)', isinstance(r, dict) and r.get('_status') in (400, 401, 403, 404) and nxt() == 4 and not (job('k3').get('invoice') or {}).get('number'), r)
    check('phone: no errors (invoices)', not [e for e in ERRS if e.startswith('saleh')], ERRS[:3])
    c3.close()

    # ---------- 4. the sync: no more full downloads ----------
    for k in ('k1', 'k2', 'k3'): psql("delete from public.docs where path = 'jobs/%s'" % k)
    psql("delete from public.docs where path like 'jobs/%%' and data->>'date' = '%s'" % D)   # (the bookings of part 2)
    merge(otok, 'jobs/j1', {'mechanic': 'Saleh', 'truck': 'c1'})
    reqs = []
    c4 = ctx(b, phone=True); c4.add_init_script("window.__syncCfg = {tick: 1000, check: 4000, away: 1000};")
    sp = page(c4, 'saleh2'); sp.on('request', lambda r: reqs.append(r.url) if '/rest/v1/docs?' in r.url and r.method == 'GET' else None)
    login(sp, 'saleh@garage.test', pw['saleh']); sp.wait_for_timeout(1500)
    first = len(reqs); sp.wait_for_timeout(9000)
    later = [kind(u) for u in reqs[first:]]
    check('app open: the light check runs (every few seconds here), never a whole new download', later.count('check') >= 3 and later.count('full') == 0, {k: later.count(k) for k in set(later)})
    del reqs[:]
    sp.reload(); sp.wait_for_selector('#tabbar, .ph-top', timeout=15000); sp.wait_for_timeout(2500)
    ks = [kind(u) for u in reqs]
    check('the app opened again: what it keeps on the phone + the light check, not everything again', ks.count('full') == 0 and ks.count('check') >= 1, {k: ks.count(k) for k in set(ks)})
    has = lambda what, i: sp.evaluate("([w, i]) => window.__garageApi.S[w].some(x => x.id === i)", [what, i])
    check('Saleh sees his job and its client (and not Paul, Ali\'s client)', has('jobs', 'j1') and has('clients', 'c1') and not has('clients', 'c2'))
    merge(otok, 'jobs/j1', {'mechanic': 'Ali', 'truck': 'c2'})        # the office moves his job to Ali's truck
    gone = wait_for(sp, "!window.__garageApi.S.jobs.some(j => j.id === 'j1')", 9000)
    check('a job moved to another truck leaves his phone within seconds (before: up to 10 minutes)', gone and not has('clients', 'c1'))
    doc_set(otok, 'jobs/j3', {'date': TODAY, 'time': '15:00', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c2', 'client': {'id': 'c2', 'name': 'Paul Roy'}, 'services': ['Inspection'], 'status': 'planifie'})
    seen = wait_for(sp, "window.__garageApi.S.jobs.some(j => j.id === 'j3') && window.__garageApi.S.clients.some(c => c.id === 'c2')", 9000)
    check('a new job for him arrives, with its client\'s fiche (unchanged, but now his to see)', seen)
    check('phone: no errors (sync)', not [e for e in ERRS if e.startswith('saleh2')], ERRS[:3])
    c4.close(); c1.close()

    # ---------- 6. a truck in service without its mechanic yet; the booking window on a computer ----------
    sat = T0 + datetime.timedelta(days=1)
    while sat.weekday() != 5: sat += datetime.timedelta(days=1)
    SAT = sat.isoformat()
    c = cfgd(); c.pop('bookMode', None); c.pop('homePostal', None)
    c['hours'] = {str(x): {'open': x in (0, 5, 6), 'start': '15:30' if x == 5 else '10:00' if x in (0, 6) else '08:00', 'end': '20:00' if x == 5 else '18:00' if x in (0, 6) else '17:00'} for x in range(7)}
    c['trucks'] = [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': ''}, {'id': 'c2', 'name': 'Camion 2', 'on': False, 'mech': ''}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]
    doc_set(otok, 'config/main', c)
    c6 = ctx(b); w6 = page(c6, 'owner-wide'); w6.set_viewport_size({'width': 1600, 'height': 900}); login(w6, 'hassan@garage.test', pw['hassan'])
    w6.goto(BASE + '#agenda'); w6.wait_for_timeout(700)
    w6.click('#top [data-act="new"]'); w6.wait_for_selector('#cs-q', timeout=8000)
    w6.fill('#cs-q', 'Marie'); w6.wait_for_timeout(400); w6.locator('#cs-results .crow').first.click(); w6.wait_for_selector('#blkpick .blk', state='attached', timeout=8000)
    w6.evaluate("(d) => { const t = document.getElementById('f-date'); t.value = d; t.dispatchEvent(new Event('change', {bubbles:true})); }", SAT); w6.wait_for_timeout(700)
    bl = w6.evaluate("[...document.querySelectorAll('#blkpick .blk')].map(b => b.dataset.v + ':' + b.querySelector('em').textContent)")
    check('a truck in service whose mechanic is not chosen yet: Saturday (open 10 h–18 h) has room in every block (no more « Fermé »)', bl == ['am:Presque plein', 'pm:Place libre', 'eve:Presque plein'], bl)
    geo = w6.evaluate("(() => { const r = document.querySelector('#sheet .sheet').getBoundingClientRect(), a = document.querySelector('#jobform section[data-step=\"1\"]').getBoundingClientRect(), z = document.querySelector('#jobform section[data-step=\"3\"]').getBoundingClientRect(); return {w: r.width, cx: a.left, rx: z.left, ry: z.top, cy: a.top}; })()")
    check('on a computer the booking window is big (1180 px on a 1600 px screen), the appointment on the right of the client', geo['w'] >= 1100 and geo['rx'] > geo['cx'] + 400 and abs(geo['ry'] - geo['cy']) < 5, geo)
    w6.evaluate("document.querySelector('#blkpick [data-v=\"pm\"]').click()"); w6.wait_for_timeout(300)
    w6.evaluate("document.getElementById('jobform').requestSubmit()"); w6.wait_for_timeout(3000)
    sj = json.loads(psql("select coalesce(json_agg(json_build_object('t', data->>'truck', 'm', data->>'mechanic', 'b', data->>'block')), '[]') from public.docs where path like 'jobs/%%' and data->>'date' = '%s'" % SAT))
    check('…the booking passes: in Camion 1, its mechanic to come (he follows when the truck is given to him)', sj == [{'t': 'c1', 'm': '', 'b': 'pm'}], sj)
    c6.close()
    cp6 = ctx(b, phone=True); p6 = page(cp6, 'owner-phone6'); login(p6, 'hassan@garage.test', pw['hassan'])
    p6.evaluate("location.hash = 'jour'"); p6.wait_for_timeout(500)
    p6.evaluate("document.querySelector('.tab[data-t=\"plus\"]') && document.querySelector('.tab[data-t=\"plus\"]').click()"); p6.wait_for_timeout(300)
    p6.evaluate("(d) => { const S = window.__garageApi.S; S.day = d; S.tab = 'jour'; window.__garageApi.render(); }", SAT); p6.wait_for_timeout(400)
    if p6.locator('[data-act="blk-book"]').count(): p6.locator('[data-act="blk-book"]').first.click()
    else: p6.evaluate("document.querySelector('[data-act=\"new\"], [data-act=\"ph-go\"][data-v=\"new\"]') && document.querySelector('[data-act=\"new\"], [data-act=\"ph-go\"][data-v=\"new\"]').click()")
    p6.wait_for_timeout(800)
    pw6 = p6.evaluate("(() => { const s = document.querySelector('#sheet:not([hidden]) .sheet'); return s ? Math.round(s.getBoundingClientRect().width) : innerWidth; })()")
    check('on a phone the booking stays as before (the whole width, one column)', pw6 <= 390, pw6)
    check('no errors (part 6)', not [e for e in ERRS if e.split(':')[0] in ('owner-wide', 'owner-phone6')], ERRS[:3])
    cp6.close()
    b.close()

# ---------- 5. how much is downloaded: 2 000 jobs ----------
rows = []
base = {'time': '10:00', 'block': 'am', 'durationMin': 90, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'status': 'termine', 'createdAt': 1761900000000, 'updatedAt': 1761990000000,
        'client': {'id': 'c1', 'firstName': 'Marie', 'lastName': 'Tremblay', 'name': 'Marie Tremblay', 'phone': '514 555-0101', 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3', 'geo': {'lat': 45.5265, 'lon': -73.5841}, 'lang': 'fr'},
        'vehicle': {'make': 'Honda', 'model': 'Civic', 'year': '2018', 'vin': '2HGFC2F59JH512345', 'plate': 'ABC 123', 'km': '84 500', 'engine': '2,0 L 4 cyl.'},
        'services': ["Changement d'huile et filtre", 'Freins avant (plaquettes)', 'Inspection multipoints'], 'service': "Changement d'huile et filtre, Freins avant (plaquettes), Inspection multipoints", 'notes': 'Bruit à l\'avant droit au freinage.',
        'invoice': {'lines': [{'type': 'forfait', 'desc': "Changement d'huile et filtre", 'qty': 1, 'price': 89.95}, {'type': 'forfait', 'desc': 'Freins avant (plaquettes)', 'qty': 1, 'price': 249}, {'type': 'piece', 'desc': 'Plaquettes céramique', 'qty': 1, 'price': 74.5}, {'type': 'frais', 'desc': 'Frais de déplacement', 'qty': 1, 'price': 25}],
                    'taxesOn': True, 'tpsRate': 0.05, 'tvqRate': 0.09975, 'sub': 438.45, 'tps': 21.92, 'tvq': 43.74, 'total': 504.11, 'paid': True, 'method': 'Débit', 'paidAt': '2026-10-01', 'note': '', 'number': 'F-0001', 'issuedAt': '2026-10-01', 'updatedAt': 1761990000000},
        'waiver': {'id': 'j__wv1', 'name': 'Marie Tremblay', 'at': 1761900000000, 'text': "J'autorise le garage à faire les travaux convenus sur mon véhicule. " * 6}}
bj = json.dumps(base).replace("'", "''")
psql("insert into public.docs (path, data) select 'jobs/big' || i, '" + bj + "'::jsonb || jsonb_build_object('date', (current_date - (i % 700))::text) from generate_series(0, 1999) i")
check('2 000 jobs added for the measure', int(psql("select count(*) from public.docs where path like 'jobs/big%'")) == 2000)
def size(sel):
    tot = 0
    for off in range(0, 3000, 1000):
        req = urllib.request.Request(API + '/rest/v1/docs?select=%s&col=eq.jobs&order=path.asc&offset=%d&limit=1000' % (sel, off), headers={'apikey': K['anon'], 'Authorization': 'Bearer ' + otok})
        with urllib.request.urlopen(req) as r: b2 = r.read()
        tot += len(b2)
        if len(json.loads(b2)) < 1000: break
    return tot
full, light = size('id,data,updated_at'), size('id,updated_at')
print('SIZES full=%d light=%d' % (full, light))
check('2 000 jobs: the light check downloads at least 15 times less than the whole copy (%.1f MB → %.0f KB)' % (full / 1e6, light / 1e3), full > 15 * light, (full, light))
psql("delete from public.docs where path like 'jobs/big%'")
summary()
