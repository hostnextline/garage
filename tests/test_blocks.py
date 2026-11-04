"""Rendez-vous par bloc (matin, après-midi, soir), sans assignation à la réservation : l'app répartit les jobs entre les camions
et fait la route la plus courte ; un bloc plein refuse une job de plus. Aussi : l'estimé rapide sans le client, la décharge
signée (plus de photos), l'inventaire général. Owner on the computer and the phone, a mechanic on his phone, real writes."""
import datetime, json
from team_seed import *
from playwright.sync_api import sync_playwright

T0 = datetime.date.today()
def next_day(wd_ok, start=1):
    d = T0 + datetime.timedelta(days=start)
    while not wd_ok(d.weekday()): d += datetime.timedelta(days=1)
    return d.isoformat()
D = next_day(lambda w: w < 5)              # a weekday after today (no block started yet)
SUN = next_day(lambda w: w == 6)           # the garage is closed on Sundays
def job(i): return doc('jobs/' + i) or {}
def cfgd(): return doc('config/main') or {}
def tmin(t): h, m = t.split(':'); return int(h) * 60 + int(m)

otok, pw = seed()
c = cfgd(); c.pop('bookMode', None)                  # (no choice saved: the team version books by block)
c['homePostal'] = 'H4P 2B5'
c['hours'] = {str(d): {'open': d != 0, 'start': '08:00', 'end': '20:00'} for d in range(7)}
c['services'] = c.get('services', []) + [{'name': 'Inspection', 'price': 60}]
doc_set(otok, 'config/main', c)
snapc = lambda pc, n: {'id': 'c1', 'name': n, 'firstName': n, 'lastName': '', 'postal': pc, 'phone': '514 555-0101'}
J = lambda pc, n, extra=None: dict({'date': D, 'time': '08:00', 'block': 'am', 'durationMin': 60, 'mechanic': '', 'truck': '', 'clientId': 'c1', 'client': snapc(pc, n), 'services': ['Inspection'], 'status': 'planifie', 'createdAt': 5}, **(extra or {}))
for i, (pc, n) in enumerate([('H2J 2L3', 'Ana'), ('H2X 1H1', 'Bob'), ('H2T 1A1', 'Cara'), ('H3N 1A1', 'Dan')]):
    doc_set(otok, 'jobs/b%d' % i, J(pc, n))
doc_set(otok, 'jobs/bp', J('H2J 2L4', 'Pin', {'truck': 'c2', 'pin': True, 'mechanic': 'Ali'}))   # a truck chosen by hand
# that morning, each mechanic picked his truck in his app (nobody assigns them)
for em, k in (('saleh@garage.test', 'c1'), ('ali@garage.test', 'c2')):
    http('POST', API + '/rest/v1/rpc/pick_truck', {'p_date': D, 'p_truck': k}, token(em, pw[em.split('@')[0]]))
# the inventory kept by truck before: the same oil in two trucks
doc_set(otok, 'stock/c1__huile-0w-20', {'truck': 'c1', 'name': 'Huile 0W-20', 'ref': '', 'unit': 'L', 'qty': 10, 'min': 4})
doc_set(otok, 'stock/c2__huile-0w-20', {'truck': 'c2', 'name': 'Huile 0W-20', 'ref': '', 'unit': 'L', 'qty': 5, 'min': 6})

with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- 1. the owner on the computer: the routes of a block ----------
    c1 = ctx(b); op = page(c1, 'owner'); login(op, 'hassan@garage.test', pw['hassan'])
    op.goto(BASE + '#agenda'); op.wait_for_timeout(700)
    op.evaluate("(d) => { const S = window.__garageApi.S; S.day = d; S.view = 'grid'; window.__garageApi.render(); }", D); op.wait_for_timeout(500)
    check('team version: booking by block unless chosen otherwise (the 3 blocks of the day above the agenda)', op.locator('#bbar .bband').count() == 3 and 'Matin' in op.inner_text('#bbar') and 'Après-midi' in op.inner_text('#bbar') and 'Soir' in op.inner_text('#bbar'), op.inner_text('#bbar')[:200] if op.locator('#bbar').count() else '')
    check('…the morning: 5 jobs, nobody assigned yet except the pinned one → « à assigner »', '5 jobs' in op.inner_text('#bbar [data-blk="am"]'), op.inner_text('#bbar [data-blk="am"]'))
    op.click('[data-act="replan"]'); op.wait_for_timeout(3000)
    js = {i: job(i) for i in ('b0', 'b1', 'b2', 'b3', 'bp')}
    check('« Refaire les routes » : every job of the morning gets a truck and its mechanic', all(j.get('truck') in ('c1', 'c2') and j.get('mechanic') == {'c1': 'Saleh', 'c2': 'Ali'}[j.get('truck')] for j in js.values()), {k: (j.get('truck'), j.get('mechanic')) for k, j in js.items()})
    check('…split between the two trucks in service (Camion 3 is closed)', {j.get('truck') for j in js.values()} == {'c1', 'c2'})
    check('…the truck chosen by hand keeps its job', js['bp'].get('truck') == 'c2' and js['bp'].get('pin') is True)
    ok_times = True
    for tk in ('c1', 'c2'):
        r = sorted([j for j in js.values() if j.get('truck') == tk], key=lambda j: j.get('order', 0))
        times = [tmin(j['time']) for j in r]
        ok_times = ok_times and times == sorted(times) and times[0] >= 8 * 60 and times[-1] + 60 <= 12 * 60 and [j.get('order') for j in r] == list(range(1, len(r) + 1))
    check('…each route in order (1, 2, 3…), times from 8 h, the last job done by noon', ok_times, {k: (j.get('truck'), j.get('time'), j.get('order')) for k, j in js.items()})
    check('…the two Plateau clients (H2J) in the same route, one after the other', js['b0'].get('truck') == js['bp'].get('truck') and abs(js['b0'].get('order', 0) - js['bp'].get('order', 0)) == 1, (js['b0'].get('truck'), js['b0'].get('order'), js['bp'].get('order')))
    op.reload(); op.wait_for_timeout(1200)
    op.evaluate("(d) => { const S = window.__garageApi.S; S.day = d; S.view = 'grid'; window.__garageApi.render(); }", D); op.wait_for_timeout(400)
    op.click('[data-act="replan"]'); op.wait_for_timeout(1500)
    check('laid out again with nothing new: nothing moves', toast_has(op, 'déjà les plus courtes') and all(job(i).get('time') == js[i].get('time') and job(i).get('truck') == js[i].get('truck') for i in js))

    # ---------- 2. booking: the block, no truck, no mechanic ----------
    op.click('#top [data-act="new"]'); op.wait_for_selector('#cs-q', timeout=8000)
    op.fill('#cs-q', 'Marie'); op.wait_for_timeout(400); op.locator('#cs-results .crow').first.click(); op.wait_for_selector('#blkpick .blk', state='attached', timeout=8000)
    op.evaluate("(d) => { const t = document.getElementById('f-date'); t.value = d; t.dispatchEvent(new Event('change', {bubbles:true})); }", D); op.wait_for_timeout(600)
    bl = op.evaluate("[...document.querySelectorAll('#blkpick .blk')].map(b => [b.dataset.v, b.querySelector('em').textContent])")
    check('booking: three blocks to choose (Matin, Après-midi, Soir), with how full each one is', [x[0] for x in bl] == ['am', 'pm', 'eve'] and all(x[1] in ('Place libre', 'Presque plein', 'Complet') for x in bl), bl)
    check('…no hour to type, no mechanic to choose: the truck is « Automatique »', op.locator('#f-time').get_attribute('type') == 'hidden' and op.input_value('#f-truck') == '' and op.locator('select#f-mech').count() == 0)
    check('…the best blocks near the client are proposed', op.locator('#sugbox [data-act="sug-blk"]').count() >= 1, op.inner_text('#sugbox')[:200] if op.locator('#sugbox').count() else '')
    op.click('#blkpick [data-v="pm"]'); op.wait_for_timeout(300)
    check('…« Après-midi » chosen: the form says the app chooses the truck and the order', op.input_value('#f-block') == 'pm' and op.input_value('#f-time') == '12:00' and 'l\'app choisit le camion' in op.inner_text('#momentmsg'), op.inner_text('#momentmsg'))
    op.evaluate("document.getElementById('jobform').requestSubmit()"); op.wait_for_timeout(2500)
    nj = [j for j in json.loads(psql("select coalesce(json_agg(data), '[]') from public.docs where path like 'jobs/%%' and data->>'block' = 'pm' and data->>'date' = '%s'" % D))]
    check('saved: the job of the afternoon block, then the app gave it a truck, its mechanic and a time in the block', len(nj) == 1 and nj[0].get('truck') in ('c1', 'c2') and nj[0].get('mechanic') in ('Saleh', 'Ali') and 12 * 60 <= tmin(nj[0]['time']) < 16 * 60, nj[0] if nj else None)

    # ---------- 3. a full block refuses one more ----------
    far = ['J7V 1A1', 'J0R 1A1', 'J3L 1A1', 'J6E 1A1', 'J8L 1A1', 'J5R 1A1', 'J4B 1A1', 'J7A 1A1']
    for i, pc in enumerate(far): doc_set(otok, 'jobs/f%d' % i, J(pc, 'Loin %d' % i, {'durationMin': 90}))
    op.reload(); op.wait_for_timeout(1200)
    op.evaluate("(d) => { const S = window.__garageApi.S; S.day = d; window.__garageApi.render(); }", D); op.wait_for_timeout(400)
    op.click('[data-act="replan"]'); op.wait_for_timeout(5000)
    over = int(psql("select count(*) from public.docs where path like 'jobs/%%' and data->>'date' = '%s' and data->>'block' = 'am' and coalesce(data->>'truck', '') = ''" % D))
    check('too many jobs for the morning: the ones that do not fit wait in « À assigner »', over >= 1 and 'à assigner' in op.inner_text('#bbar [data-blk="am"]'), [over, op.inner_text('#bbar [data-blk="am"]')])
    check('…the agenda shows them in their own column', op.locator('.col-h, .colh, th, .cal', has_text='À assigner').count() >= 1 or 'À assigner' in op.inner_text('main'))
    op.click('#top [data-act="new"]'); op.wait_for_selector('#cs-q', timeout=8000)
    op.fill('#cs-q', 'Paul'); op.wait_for_timeout(400); op.locator('#cs-results .crow').first.click(); op.wait_for_selector('#blkpick .blk', state='attached', timeout=8000)
    op.evaluate("(d) => { const t = document.getElementById('f-date'); t.value = d; t.dispatchEvent(new Event('change', {bubbles:true})); }", D); op.wait_for_timeout(600)
    check('…the form says « Complet » for the morning', 'Complet' in op.inner_text('#blkpick [data-v="am"]'), op.inner_text('#blkpick [data-v="am"]'))
    op.evaluate("document.querySelector('#blkpick [data-v=\"am\"]').click()"); op.wait_for_timeout(300)   # (aria-disabled: a person can still touch it)
    check('…and does not let you pick it', toast_has(op, 'complet') and op.input_value('#f-block') != 'am')
    op.evaluate("(d) => { const t = document.getElementById('f-date'); t.value = d; t.dispatchEvent(new Event('change', {bubbles:true})); }", SUN); op.wait_for_timeout(500)
    check('…a closed day: every block « Fermé »', op.evaluate("[...document.querySelectorAll('#blkpick .blk em')].every(e => e.textContent === 'Fermé')"), op.evaluate("[...document.querySelectorAll('#blkpick .blk em')].map(e => e.textContent)"))
    op.evaluate("document.querySelector('.sheet [data-act=\"sheet-close\"]').click()"); op.wait_for_timeout(300)

    # ---------- 4. a cancellation frees its place; the route closes up ----------
    for i in range(len(far)): psql("delete from public.docs where path = 'jobs/f%d'" % i)
    op.reload(); op.wait_for_timeout(1200)
    op.evaluate("(d) => { const S = window.__garageApi.S; S.day = d; window.__garageApi.render(); }", D); op.wait_for_timeout(300)
    op.click('[data-act="replan"]'); op.wait_for_timeout(3000)
    tk0 = job('b1').get('truck')
    op.evaluate("(id) => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = id; window.__garageApi.render(); }", 'b1'); op.wait_for_timeout(500)
    op.evaluate("window.__garageApi.changeStatus('annule')"); op.wait_for_timeout(2500)
    rest = sorted([job(i) for i in ('b0', 'b2', 'b3', 'bp') if job(i).get('truck') == tk0], key=lambda j: j.get('order', 0))
    check('a cancelled job: the others of its route close up (order 1, 2…)', job('b1').get('status') == 'annule' and [j.get('order') for j in rest] == list(range(1, len(rest) + 1)), [(j.get('client', {}).get('name'), j.get('order'), j.get('time')) for j in rest])
    check('computer: no errors', not [e for e in ERRS if e.startswith('owner')], ERRS[:3])

    # ---------- 5. the quick estimate, without the client ----------
    op.goto(BASE + '#accueil'); op.wait_for_selector('#tiles', timeout=10000)
    op.click('#tiles [data-act="est-new"]'); op.wait_for_selector('#est-box', timeout=8000)
    check('« Estimé rapide » tile: an estimate with no client to choose', op.locator('#cs-q').count() == 0 and 'sans le nom du client' in op.inner_text('#est-box'))
    op.evaluate("[...document.querySelectorAll('#est-box [data-act=\"addsvc\"]')].filter(b => /^Inspection ·/.test(b.textContent.trim()))[0].click()"); op.wait_for_timeout(200)
    op.click('#est-box [data-act="addline"][data-v="piece"]'); op.wait_for_timeout(200)
    n = op.locator('#lines .line').count()
    op.fill('#l%d-desc' % (n - 1), 'Plaquettes avant'); op.fill('#l%d-price' % (n - 1), '80'); op.wait_for_timeout(200)
    tot = op.inner_text('#totdl').replace(' ', ' ').replace('\xa0', ' ')
    check('…the total with the taxes right away (60 $ + 80 $ = 140 $ + taxes = 160,97 $)', '140,00' in tot and '160,97' in tot, tot)
    op.click('[data-act="est-yes"]'); op.wait_for_timeout(400)
    check('« Le client accepte »: book a moment, or do the work now', op.locator('#sheet [data-act="est-go"][data-v="book"]').count() == 1 and op.locator('#sheet [data-act="est-go"][data-v="now"]').count() == 1)
    op.click('#sheet [data-act="est-go"][data-v="now"]'); op.wait_for_selector('#cs-q', timeout=8000)
    check('…now: his name and phone are asked (the client step)', op.locator('#cs-q').count() == 1)
    op.fill('#cs-q', 'Marie'); op.wait_for_timeout(400); op.locator('#cs-results .crow').first.click(); op.wait_for_selector('#jobform', timeout=8000); op.wait_for_timeout(400)
    check('…the services of the estimate are already in the job', 'Inspection' in op.inner_text('#jobform') and 'Plaquettes avant' in op.inner_text('#jobform'))
    op.evaluate("document.getElementById('jobform').requestSubmit()"); op.wait_for_selector('#lines .line', timeout=10000); op.wait_for_timeout(500)
    descs = op.evaluate("[...document.querySelectorAll('#lines .line input[data-f=\"desc\"]')].map(i => i.value)")
    check('…the invoice starts from the estimate (same lines, same prices)', descs == ['Inspection', 'Plaquettes avant'] and '160,97' in op.inner_text('#totdl').replace(' ', ' ').replace('\xa0', ' '), descs)
    ej = json.loads(psql("select coalesce(json_agg(data), '[]') from public.docs where path like 'jobs/%' and data ? 'estimate'"))
    check('…the estimate is kept on the job (accepted: kept; otherwise nothing saved)', len(ej) == 1 and ej[0]['estimate']['total'] == 160.97 and ej[0]['status'] == 'place', [x.get('estimate') for x in ej])
    est_job = json.loads(psql("select json_agg(path) from public.docs where path like 'jobs/%' and data ? 'estimate'"))[0].split('/')[1]
    op.click('[data-act="back-inv"]'); op.wait_for_timeout(400)
    c1.close()

    # ---------- 6. the waiver: signed before the work, no photos ----------
    c2 = ctx(b, phone=True); sp = page(c2, 'saleh'); login(sp, 'saleh@garage.test', pw['saleh'])
    psql("update public.docs set data = jsonb_set(jsonb_set(data, '{status}', '\"route\"'), '{date}', to_jsonb('%s'::text)) where path = 'jobs/j1'" % T0.isoformat())
    sp.reload(); sp.wait_for_timeout(1500)
    sp.evaluate("(id) => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = id; window.__garageApi.render(); }", 'j1'); sp.wait_for_timeout(600)
    check('on the way: « Avant de commencer : la décharge du client » on the job', sp.locator('#wv-nudge').count() == 1 and sp.locator('#wv-fold').count() == 1)
    check('…no photo buttons anymore', sp.locator('label[for="pin-av"], label[for="pin-ap"], .pin').count() == 0)
    sp.click('#wv-nudge [data-act="wv-open"]'); sp.wait_for_selector('#sigpad', timeout=8000)
    txt = sp.inner_text('#sheet .wvtext')
    check('…the waiver: the garage\'s name, the conditions (place, items left in the car, parts he supplies)', 'Garage NextLine' in txt and 'objets laissés' in txt and 'pièces que je fournis' in txt, txt[:160])
    bx = sp.locator('#sigpad').bounding_box()
    sp.mouse.move(bx['x'] + 30, bx['y'] + 40); sp.mouse.down(); sp.mouse.move(bx['x'] + 120, bx['y'] + 70, steps=8); sp.mouse.move(bx['x'] + 200, bx['y'] + 30, steps=8); sp.mouse.up()
    sp.click('#sig-save'); sp.wait_for_timeout(1500)
    w = job('j1').get('waiver') or {}
    check('signed: the waiver is kept on the job (name, time, the text signed)', w.get('name') == 'Marie Tremblay' and 'Garage NextLine' in (w.get('text') or '') and w.get('id'), w)
    check('…the signature itself is kept (« waiver »)', psql("select data->>'kind' from public.docs where path = 'photos/%s'" % w.get('id', 'x')) == 'waiver')
    sp.wait_for_timeout(500)
    check('…the job says « Signée par Marie Tremblay », no more reminder', 'Signée par Marie Tremblay' in (sp.text_content('#wv-fold') or '') and 'signée' in sp.inner_text('#wv-fold summary') and sp.locator('#wv-nudge').count() == 0)
    psql("update public.docs set data = data || '{\"lang\": \"en\"}' where path = 'clients/c2'")
    psql("update public.docs set data = jsonb_set(jsonb_set(data, '{status}', '\"place\"'), '{mechanic}', '\"Saleh\"') where path = 'jobs/j2'")
    sp.reload(); sp.wait_for_timeout(1500)
    sp.evaluate("(id) => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = id; window.__garageApi.render(); }", 'j2'); sp.wait_for_timeout(600)
    sp.click('#wv-nudge [data-act="wv-open"]'); sp.wait_for_selector('#sigpad', timeout=8000)
    check('an English-speaking client: the waiver in English', 'I authorize Garage NextLine' in sp.inner_text('#sheet .wvtext'), sp.inner_text('#sheet .wvtext')[:80])
    sp.evaluate("document.querySelector('.sheet [data-act=\"sheet-close\"]').click()"); sp.wait_for_timeout(300)

    # ---------- 7. the mechanic: his routes, the estimate from « + » ----------
    sp.goto(BASE + '#jour'); sp.wait_for_timeout(600)
    sp.evaluate("(d) => { const S = window.__garageApi.S; S.day = d; window.__garageApi.render(); }", D); sp.wait_for_timeout(600)
    mine = json.loads(psql("select coalesce(json_agg(data), '[]') from public.docs where path like 'jobs/%%' and data->>'date' = '%s' and data->>'mechanic' = 'Saleh'" % D))
    check('mechanic\'s day by block: the three blocks, his jobs only, with « ≈ » times', sp.locator('.ph-bh').count() == 3 and sp.locator('.ph-job').count() == len(mine) and all('≈' in t for t in sp.evaluate("[...document.querySelectorAll('.ph-job.s-planifie .pj-t')].map(e => e.textContent)")), [sp.locator('.ph-job').count(), len(mine)])
    sp.click('.tab-new'); sp.wait_for_timeout(400)
    check('« + » on the phone: « Estimé rapide »', sp.locator('#sheet [data-act="ph-go"][data-v="est"]').count() == 1)
    sp.click('#sheet [data-act="ph-go"][data-v="est"]'); sp.wait_for_selector('#est-box', timeout=8000)
    check('…opens the estimate', sp.locator('#est-box [data-act="est-yes"]').count() == 1)
    check('phone: no sideways scroll on the estimate', no_hscroll(sp))
    sp.click('[data-act="est-back"]'); sp.wait_for_timeout(300)
    check('mechanic: no errors', not [e for e in ERRS if e.startswith('saleh')], ERRS[:3])
    c2.close()

    # ---------- 8. the owner's phone: the day by block, « + Réserver » in a block ----------
    c3 = ctx(b, phone=True); pp = page(c3, 'ownerphone'); login(pp, 'hassan@garage.test', pw['hassan'])
    pp.evaluate("(d) => { const S = window.__garageApi.S; S.day = d; window.__garageApi.render(); }", D); pp.wait_for_timeout(600)
    check('phone day: three blocks with their jobs, « + Réserver » where there is room', pp.locator('.ph-bh').count() == 3 and pp.locator('.ph-bh [data-act="blk-book"]').count() >= 1 and pp.locator('.ph-gap').count() == 0)
    pp.locator('.ph-bh[data-blk="eve"] [data-act="blk-book"]').click(); pp.wait_for_selector('#cs-q, #f-block', state='attached', timeout=8000)
    if pp.locator('#cs-q').count():   # (otherwise the booking started on the computer is taken back, with its client)
        pp.fill('#cs-q', 'Paul'); pp.wait_for_timeout(400); pp.locator('#cs-results .crow').first.click(); pp.wait_for_selector('#f-block', state='attached', timeout=8000)
    check('…the form opens with that block chosen (« Soir »)', pp.input_value('#f-block') == 'eve' and pp.input_value('#f-date') == D)
    pp.evaluate("document.querySelector('.sheet [data-act=\"sheet-close\"]').click()"); pp.wait_for_timeout(300)
    check('phone: no sideways scroll on the day', no_hscroll(pp))

    # ---------- 9. the inventory: one list for the garage ----------
    pp.goto(BASE + '#stock'); pp.wait_for_timeout(800)
    check('« Inventaire »: one list (no section per truck), the oil twice (it was counted by truck)', 'Inventaire' in pp.inner_text('#top') and pp.locator('.stkrow').count() == 2 and pp.locator('#stk-dups').count() == 1)
    pp.click('[data-act="stk-merge"]'); pp.wait_for_timeout(2000)
    rows = json.loads(psql("select coalesce(json_agg(data), '[]') from public.docs where path like 'stock/%'"))
    check('« Les additionner »: one line, 15 L (10 + 5), the highest minimum kept', len(rows) == 1 and rows[0]['qty'] == 15 and rows[0]['min'] == 6 and 'truck' not in rows[0], rows)
    pp.click('[data-act="stk-new"]'); pp.wait_for_selector('#stk-name', timeout=8000)
    check('a new item: no truck to choose', pp.locator('#stk-truck').count() == 0)
    pp.fill('#stk-name', 'Filtre à huile'); pp.fill('#stk-q0', '8'); pp.click('[data-act="stk-save"]'); pp.wait_for_timeout(1200)
    check('…saved in the inventory', psql("select data->>'qty' from public.docs where path like 'stock/%' and data->>'name' = 'Filtre à huile'") == '8')
    check('owner phone: no errors', not [e for e in ERRS if e.startswith('ownerphone')], ERRS[:3])
    c3.close()

    # ---------- 10. Réglages: the waiver text, the way of booking ----------
    c4 = ctx(b); o2 = page(c4, 'owner2'); login(o2, 'hassan@garage.test', pw['hassan'])
    o2.evaluate("window.__allSettings = true"); o2.goto(BASE + '#reglages'); o2.wait_for_selector('#wv-set', timeout=10000)
    check('Réglages: « Façon de réserver » (by block chosen) and « Décharge du client » (French and English)', o2.locator('input[name="s-book"][value="blocks"]').is_checked() and o2.locator('#s-waiver').count() == 1 and o2.locator('#s-waiver-en').count() == 1)
    o2.fill('#s-waiver', 'Texte maison de {garage}.'); o2.click('#s-save'); o2.wait_for_timeout(1200)
    check('a waiver of his own: saved', cfgd().get('waiver') == 'Texte maison de {garage}.')
    o2.goto(BASE + '#reglages'); o2.wait_for_selector('#wv-set', timeout=10000)
    o2.click('[data-act="wv-reset"]'); o2.click('#s-save'); o2.wait_for_timeout(1200)
    check('« Remettre le texte de départ »: back to the app\'s text', cfgd().get('waiver') == '')
    o2.goto(BASE + '#reglages'); o2.wait_for_selector('#book-set', timeout=10000)
    o2.check('input[name="s-book"][value="hours"]'); o2.click('#s-save'); o2.wait_for_timeout(1200)
    o2.goto(BASE + '#agenda'); o2.wait_for_timeout(600)
    check('« À l\'heure » chosen: no blocks on the agenda', cfgd().get('bookMode') == 'hours' and o2.locator('#bbar').count() == 0)
    o2.goto(BASE + '#reglages'); o2.wait_for_selector('#book-set', timeout=10000)
    o2.check('input[name="s-book"][value="blocks"]'); o2.click('#s-save'); o2.wait_for_timeout(1200)
    check('…back to blocks', cfgd().get('bookMode') == 'blocks')
    c4.close()
    b.close()
check('no script errors', not ERRS, ERRS[:5])
summary()
