"""Phone interface (screens < 700 px): 4 tabs + « + », one day at a time, job = one big next-step button,
booking in 3 steps, hours with switches, settings one part at a time, payment buttons, full/simple switch."""
import json, os, datetime, re, sys
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open('/home/claude/garage/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
T = datetime.date.today(); iso = lambda d: d.isoformat()
W = T + datetime.timedelta(days=3)
while W.weekday() != 2: W += datetime.timedelta(days=1)   # a Wednesday, 3+ days ahead (open 8 h - 17 h by default)
seed = {'config/main': {'biz': {'name': 'Garage NextLine'}, 'trucks': [], 'mechanics': ['Saleh', 'Ali'], 'rate': 120, 'taxesOn': True, 'goal': 20000, 'prefix': 'F-', 'startNo': 1}}
cl = lambda n, p: {'name': n, 'firstName': n.split()[0], 'lastName': n.split()[1], 'phone': p, 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3'}
seed['clients/c1'] = {'firstName': 'Marie', 'lastName': 'Tremblay', 'phone': '5145550101', 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3'}
seed['clients/c9'] = {'firstName': 'Nadia', 'lastName': 'Haddad', 'phone': '5145550505', 'address': '100 rue Ontario Est, Montréal', 'postal': 'H2X 1H1'}
jobs = [
  ('a1', iso(T), '08:30', 90, 'Saleh', 'termine', cl('Marie Tremblay', '5145550101'), ["Changement d'huile et filtre"], {'number': 'F-0012', 'total': 189.5, 'paid': True, 'issuedAt': iso(T)}),
  ('a2', iso(T), '10:30', 90, 'Saleh', 'route', cl('Paul Roy', '4385550202'), ['Changement de pneus saisonnier'], None),
  ('a3', iso(T), '13:00', 90, 'Ali', 'place', cl('Zoé Gagnon', '5145550303'), ['Freins avant (plaquettes)'], None),
  ('a4', iso(T), '15:30', 90, 'Ali', 'planifie', cl('Luc Bélanger', '4505550404'), ["Changement d'huile et filtre", 'Inspection multipoints'], None),
  ('a5', iso(T + datetime.timedelta(days=1)), '09:00', 60, 'Saleh', 'planifie', cl('Nadia Haddad', '5145550505'), ['Diagnostic'], None),
  ('w1', iso(W), '08:00', 120, 'Saleh', 'planifie', cl('Jean Côté', '5145550606'), ['Alternateur'], None),
  ('w2', iso(W), '08:00', 60, 'Ali', 'planifie', cl('Sara Lévesque', '5145550707'), ['Diagnostic'], None),
]
for (i, d, t, du, m, st, c, sv, inv) in jobs:
    j = {'date': d, 'time': t, 'durationMin': du, 'mechanic': m, 'status': st, 'client': c, 'services': sv, 'service': ', '.join(sv), 'vehicle': {'year': '2018', 'make': 'Honda', 'model': 'Civic'}, 'problem': 'Bruit en freinant' if i == 'a4' else ''}
    if i == 'a1': j['clientId'] = 'c1'
    if inv: j['invoice'] = dict(inv, lines=[{'type': 'mo', 'desc': sv[0], 'qty': 1, 'price': inv['total']}], taxesOn=False, sub=inv['total'], tps=0, tvq=0)
    seed['jobs/' + i] = j
def harness(mode, ui=None):
    pre = ('try{localStorage.setItem("gm.ui",%s)}catch(e){}' % json.dumps(ui)) if ui else ''
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<style>{RESET}</style><script>{pre}window.__MOCK={json.dumps(mode)};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
def open_page(br, mode, width=390, scheme='light', ui=None, touch=True):
    ctx = br.new_context(viewport={'width': width, 'height': 844}, color_scheme=scheme, timezone_id='America/Toronto', locale='fr-CA', has_touch=touch)
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    def route(r):
        if r.request.url == 'https://local.test/': r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness(mode, ui))
        else: r.abort()
    pg.route('**/*', route); pg.goto('https://local.test/'); pg.wait_for_timeout(700)
    return ctx, pg, errs
def txt(pg, sel): return (pg.locator(sel).first.text_content() or '').replace('\xa0', ' ').replace(' ', ' ')
def no_hscroll(pg): return pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
def store(pg, path): return pg.evaluate('p => window.__store[p] || null', path)
def S(pg, k): return pg.evaluate('k => window.__garageApi.S[k]', k)
def tabs(pg): return pg.evaluate("[...document.querySelectorAll('#tabbar .tab:not([hidden])')].sort((a,b)=>a.getBoundingClientRect().x-b.getBoundingClientRect().x).map(b=>b.dataset.t||'+')")
def rows(pg): return pg.evaluate("[...document.querySelectorAll('.ph-list > button')].map(b => b.classList.contains('ph-gap') ? 'gap:' + b.dataset.t + ':' + b.dataset.m : 'job:' + b.dataset.id)")
def wait(pg, ms=250): pg.wait_for_timeout(ms)
def swipe(pg, dx):
    pg.evaluate("""dx => { const el = document.querySelector('.ph-list') || document.querySelector('main') || document.body;
      const mk = (x) => new Touch({identifier: 1, target: el, clientX: x, clientY: 400});
      el.dispatchEvent(new TouchEvent('touchstart', {bubbles: true, touches: [mk(200)], changedTouches: [mk(200)]}));
      el.dispatchEvent(new TouchEvent('touchend', {bubbles: true, touches: [], changedTouches: [mk(200 + dx)]})); }""", dx)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg, errs = open_page(br, {'seed': seed})
    # ---------- 1. layout ----------
    check('1. phone width (390) switches to the simple version', pg.evaluate("document.body.classList.contains('ui-phone')"))
    check('1. tabs: Aujourd\'hui, Clients, +, Factures, Plus (in that order)', tabs(pg) == ['jour', 'clients', '+', 'factures', 'plus'], tabs(pg))
    check('1. opens on Aujourd\'hui', pg.locator('.tab[data-t="jour"][aria-current="page"]').count() == 1)
    check('1. the « + » is the big one in the middle', pg.evaluate("(() => { const n = document.querySelector('.tab-new .tn-plus').getBoundingClientRect(); return n.width >= 44 && n.height >= 44; })()"))
    # ---------- 2. one day ----------
    r = rows(pg)
    check('2. today: the 4 jobs in time order', [x for x in r if x.startswith('job')] == ['job:a1', 'job:a2', 'job:a3', 'job:a4'], r)
    check('2. header says today + count', 'Aujourd\'hui · 4 jobs · 1 terminée' in txt(pg, '.dp-s'), txt(pg, '.dp-s'))
    check('2. each job shows client, car, service and status', 'Paul Roy' in txt(pg, '.ph-job[data-id="a2"]') and 'Honda Civic' in txt(pg, '.ph-job[data-id="a2"]') and 'pneus' in txt(pg, '.ph-job[data-id="a2"]') and pg.locator('.ph-job[data-id="a2"] .pill').count() == 1)
    check('2. all-mechanics view names the mechanic', 'Saleh' in txt(pg, '.ph-job[data-id="a2"]'))
    check('2. no sideways scroll', no_hscroll(pg))
    pg.click('[data-act="ph-day"][data-v="1"]'); wait(pg)
    check('2. › goes to tomorrow', S(pg, 'day') == iso(T + datetime.timedelta(days=1)) and 'job:a5' in rows(pg), rows(pg))
    check('2. « Aujourd\'hui » chip appears off today', pg.locator('[data-act="ph-today"]').count() == 1)
    pg.click('[data-act="ph-today"]'); wait(pg)
    check('2. chip brings back today', S(pg, 'day') == iso(T) and pg.locator('[data-act="ph-today"]').count() == 0)
    swipe(pg, -150); wait(pg)
    check('2. swipe left = next day', S(pg, 'day') == iso(T + datetime.timedelta(days=1)), S(pg, 'day'))
    swipe(pg, 150); wait(pg)
    check('2. swipe right = previous day', S(pg, 'day') == iso(T), S(pg, 'day'))
    swipe(pg, 40); wait(pg)
    check('2. a small move does not change the day', S(pg, 'day') == iso(T))
    pg.evaluate("w => { const i = document.getElementById('ph-date'); i.value = w; i.dispatchEvent(new Event('change', {bubbles: true})); }", iso(W)); wait(pg)
    check('2. tapping the date: picker jumps to that day', S(pg, 'day') == iso(W) and txt(pg, '.dp-t').lower().startswith('mercredi'), txt(pg, '.dp-t'))
    r = rows(pg)
    check('2. free time shown between jobs (9 h: only Ali free; 10 h: everyone)', r == ['job:w1', 'job:w2', 'gap:09:00:Ali', 'gap:10:00:'], r)
    check('2. gap says who is free and until when', 'Libre jusqu' in txt(pg, '.ph-gap[data-t="09:00"]') and 'Ali' in txt(pg, '.ph-gap[data-t="09:00"]') and '+ Réserver' in txt(pg, '.ph-gap[data-t="09:00"]'), txt(pg, '.ph-gap[data-t="09:00"]'))
    pg.select_option('#ph-mech', 'Ali'); wait(pg)
    r = rows(pg)
    check('2. mechanic filter: only Ali\'s jobs + Ali\'s free time', r[0] == 'job:w2' and 'job:w1' not in r and r[1].startswith('gap:09:00:Ali'), r)
    check('2. filter is remembered', pg.evaluate("localStorage.getItem('gm.mech')") == 'Ali')
    pg.select_option('#ph-mech', ''); wait(pg)
    # ---------- 3. booking from a free slot, 3 steps ----------
    pg.click('.ph-gap[data-t="09:00"]'); wait(pg, 500)
    check('3. booking starts by choosing the client', pg.locator('#cs-q').count() == 1)
    pg.fill('#cs-q', 'Nadia'); wait(pg); pg.locator('#cs-results .crow').first.click(); wait(pg, 600)
    check('3. client sheet closed, booking is a full page', pg.locator('#sheet').is_hidden() and S(pg, 'screen') == 'edit')
    check('3. step 1 of 3: Client et auto', pg.locator('#wiz li.here').count() == 1 and 'Client et auto' in txt(pg, '#wiz li.here') and pg.locator('#wiz li').count() == 3)
    check('3. step 1 shows client + vehicle only', pg.locator('#f-vin').is_visible() and not pg.locator('#f-svc-in').is_visible() and not pg.locator('#f-date').is_visible())
    check('3. save button hidden until the last step', not pg.locator('#f-save').is_visible())
    check('3. no sideways scroll (step 1)', no_hscroll(pg))
    pg.fill('#f-make', 'Toyota'); pg.fill('#f-model', 'RAV4')
    pg.click('[data-act="wiz-next"]'); wait(pg)
    check('3. step 2: Service', 'Service' in txt(pg, '#wiz li.here') and pg.locator('#f-svc-in').is_visible() and not pg.locator('#f-vin').is_visible())
    pg.fill('#f-svc-in', 'Diagnostic électrique'); pg.keyboard.press('Escape')
    pg.click('[data-act="wiz-next"]'); wait(pg)
    check('3. typed service kept when continuing', S(pg, 'wiz') == 3 and 'Diagnostic électrique' in pg.evaluate("document.getElementById('svc-picked').textContent"), pg.evaluate("document.getElementById('svc-picked').textContent"))
    check('3. step 3: Moment, prefilled from the free slot', pg.input_value('#f-date') == iso(W) and pg.input_value('#f-time') == '09:00' and pg.input_value('#f-mech') == 'Ali', [pg.input_value('#f-date'), pg.input_value('#f-time'), pg.input_value('#f-mech')])
    check('3. last step shows save + Retour', pg.locator('#f-save').is_visible() and pg.locator('[data-act="wiz-prev"]').is_visible())
    pg.click('[data-act="wiz-prev"]'); wait(pg)
    check('3. Retour goes back one step', S(pg, 'wiz') == 2)
    pg.click('[data-act="wiz-next"]'); wait(pg)
    pg.click('#f-save'); wait(pg, 900)
    new = pg.evaluate("Object.entries(window.__store).filter(([k,v]) => k.startsWith('jobs/') && !['a1','a2','a3','a4','a5','w1','w2'].includes(k.slice(5))).map(([k,v]) => [k, v])")
    nj = new[0][1] if new else {}
    check('3. saved: Nadia, Wed 9 h, Ali, Toyota RAV4, service', len(new) == 1 and nj.get('date') == iso(W) and nj.get('time') == '09:00' and nj.get('mechanic') == 'Ali' and (nj.get('vehicle') or {}).get('make') == 'Toyota' and 'Diagnostic électrique' in (nj.get('services') or []) and 'Nadia' in json.dumps(nj.get('client')), nj)
    check('3. tab bar back after saving', pg.locator('#tabbar').is_visible())
    newid = new[0][0][5:] if new else ''
    # ---------- 4. one job: next-step button ----------
    pg.click('.tab[data-t="jour"]'); wait(pg)
    pg.click('[data-act="ph-today"]') if pg.locator('[data-act="ph-today"]').count() else None; wait(pg)
    pg.click('.ph-job[data-id="a4"]'); wait(pg, 400)
    check('4. job page: car + services on top', 'Honda Civic' in txt(pg, '.pj-what') and 'Inspection multipoints' in txt(pg, '.pj-what'))
    hrefs = pg.evaluate("[...document.querySelectorAll('.rounds .round')].map(a => [a.textContent.trim(), a.getAttribute('href')])")
    check('4. round buttons: Appeler (tel), Texter (sms), Itinéraire (maps)', [h[0] for h in hrefs] == ['Appeler', 'Texter', 'Itinéraire'] and hrefs[0][1].startswith('tel:') and hrefs[1][1] == 'sms:4505550404' and 'google.com/maps' in hrefs[2][1], hrefs)
    check('4. 4 steps, current = Planifiée', pg.locator('.steps4 li').count() == 4 and pg.locator('.steps4 li.here').count() == 1)
    check('4. notes open, other details folded', pg.locator('details.fold[open]').count() == 1 and 'Bruit en freinant' in txt(pg, 'details.fold[open]') and pg.locator('details.fold').count() == 4)
    check('4. no sideways scroll (job)', no_hscroll(pg))
    flow = []
    for want in ('route', 'place'):
        lab = txt(pg, '.nextbtn'); pg.click('.nextbtn'); wait(pg, 400); flow.append((lab, (store(pg, 'jobs/a4') or {}).get('status')))
    check('4. on site: « Travaux faits » open on the job', pg.locator('details.fold[open] summary', has_text='Travaux faits').count() == 1)
    lab = txt(pg, '.nextbtn'); pg.click('.nextbtn'); wait(pg, 400)
    check('4. « Terminer la job » first asks what was done (booked services pre-checked)', pg.locator('#sheet').is_visible() and pg.locator('#svc-picked .pchip').count() == 2 and 'Montant prévu' in txt(pg, '#done-amt'), txt(pg, '#done-amt'))
    pg.fill('#f-svc-in', 'Purge des freins'); pg.keyboard.press('Enter'); wait(pg, 150); pg.keyboard.press('Escape')
    pg.click('[data-act="done-save"]'); wait(pg, 500); flow.append((lab, (store(pg, 'jobs/a4') or {}).get('status')))
    check('4. Je pars → Je suis arrivé → Terminer la job', [f[0] for f in flow] == ['Je pars', 'Je suis arrivé', 'Terminer la job'] and [f[1] for f in flow] == ['route', 'place', 'termine'], flow)
    check('4. work done saved on the job (3 lines)', (store(pg, 'jobs/a4') or {}).get('done') == ["Changement d'huile et filtre", 'Inspection multipoints', 'Purge des freins'], (store(pg, 'jobs/a4') or {}).get('done'))
    check('4. steps follow (3 done, Terminée current)', pg.locator('.steps4 li.past').count() == 3)
    check('4. then: Faire la facture', txt(pg, '.nextbtn') == 'Faire la facture')
    pg.click('.nextbtn'); wait(pg, 500)
    check('4. invoice starts from the work done (3 lines)', pg.locator('#lines .line, .iline').count() >= 3 or pg.evaluate("window.__garageApi.S.inv.lines.length") == 3, pg.evaluate("window.__garageApi.S.inv.lines.map(l => l.desc)"))
    check('4. invoice: payment as big buttons', pg.locator('.paybtns [data-pay]').count() == 4 and pg.evaluate("[...document.querySelectorAll('.paybtns [data-pay]')].map(b=>b.textContent)") == ['Comptant', 'Débit', 'Crédit', 'Virement'])
    check('4. no sideways scroll (invoice)', no_hscroll(pg))
    pg.click('.paybtns [data-pay="Débit"]'); wait(pg, 150)
    check('4. tapping Débit = paid by debit', pg.input_value('#i-method') == 'Débit' and pg.is_checked('#i-paid-1') and pg.locator('.paybtns .on').count() == 1)
    pg.click('.paybtns [data-pay="Crédit"]'); wait(pg, 150)
    check('4. changing to Crédit', pg.input_value('#i-method') == 'Crédit' and pg.get_attribute('.paybtns [data-pay="Débit"]', 'aria-pressed') == 'false')
    pg.click('#i-final'); wait(pg, 900)
    inv = (store(pg, 'jobs/a4') or {}).get('invoice') or {}
    check('4. invoice saved: number, paid, Crédit', inv.get('number') == 'F-0001' and inv.get('paid') is True and inv.get('method') == 'Crédit', {k: inv.get(k) for k in ('number', 'paid', 'method', 'total')})
    if S(pg, 'screen') != 'job':
        pg.evaluate("window.__garageApi.S.screen = 'job'; window.__garageApi.S.jobId = 'a4'; window.__garageApi.render()"); wait(pg)
    check('4. then: Voir la facture', txt(pg, '.nextbtn') == 'Voir la facture', txt(pg, '.nextbtn'))
    pg.select_option('#ph-st', 'annule'); wait(pg, 400)
    check('4. status menu « Annulé » asks for the amount lost first', pg.locator('#cx-amt').is_visible() and (store(pg, 'jobs/a4') or {}).get('status') == 'termine')
    pg.click('[data-act="cx-why"][data-v="client"]'); pg.click('[data-act="cx-yes"]'); wait(pg, 500)
    lo = (store(pg, 'jobs/a4') or {}).get('lost') or {}
    check('4. status menu: cancel', (store(pg, 'jobs/a4') or {}).get('status') == 'annule' and 'Annulée' in txt(pg, '.pjob') and lo.get('amount', 0) < 0 and lo.get('reason') == 'client', lo)
    check('4. cancelled job offers to put it back', txt(pg, '.nextbtn') == 'Remettre la job à l\'agenda')
    pg.click('.nextbtn'); wait(pg, 400)
    check('4. back to Planifiée (amount lost removed)', (store(pg, 'jobs/a4') or {}).get('status') == 'planifie' and not (store(pg, 'jobs/a4') or {}).get('lost'))
    pg.click('[data-act="back"]'); wait(pg)
    # delete the job booked in step 3 (asks first)
    pg.evaluate("w => { const i = document.getElementById('ph-date'); i.value = w; i.dispatchEvent(new Event('change', {bubbles: true})); }", iso(W)); wait(pg)
    pg.click('.ph-job[data-id="%s"]' % newid); wait(pg, 400)
    pg.click('[data-act="del"]'); wait(pg)
    check('4. delete asks first', pg.locator('[data-act="del-yes"]').count() == 1 and store(pg, 'jobs/' + newid) is not None)
    pg.click('[data-act="del-no"]'); wait(pg)
    check('4. « Garder » keeps it', store(pg, 'jobs/' + newid) is not None and pg.locator('[data-act="del-yes"]').count() == 0)
    pg.click('[data-act="del"]'); wait(pg); pg.click('[data-act="del-yes"]'); wait(pg, 600)
    check('4. « Supprimer » removes it (back to the original state)', store(pg, 'jobs/' + newid) is None and 'job:' + newid not in rows(pg), rows(pg))
    # ---------- 5. « + » menu ----------
    pg.click('.tab-new'); wait(pg, 400)
    check('5. « + » offers 4 choices', pg.evaluate("[...document.querySelectorAll('#sheet .ph-row b')].map(b=>b.textContent)") == ['Nouvelle réservation', 'Facture sur place', 'Nouveau client', 'Nouvelle dépense'])
    pg.click('[data-act="ph-go"][data-v="quick"]'); wait(pg, 500)
    pg.fill('#cs-q', 'Marie'); wait(pg); pg.locator('#cs-results .crow').first.click(); wait(pg, 600)
    check('5. on-the-spot invoice: 3 steps, last one is « Confirmer »', 'Confirmer' in pg.evaluate("document.getElementById('wiz').textContent"))
    pg.click('[data-act="wiz-next"]'); wait(pg); pg.fill('#f-svc-in', 'Survoltage'); pg.keyboard.press('Escape'); pg.click('[data-act="wiz-next"]'); wait(pg)
    check('5. date = today, button « Enregistrer et faire la facture »', pg.input_value('#f-date') == iso(T) and 'faire la facture' in txt(pg, '#f-save'))
    before = set(pg.evaluate("Object.keys(window.__store)"))
    pg.click('#f-save'); wait(pg, 900)
    qid = [k for k in pg.evaluate("Object.keys(window.__store)") if k.startswith('jobs/') and k not in before]
    check('5. saved and the invoice opens with payment buttons', len(qid) == 1 and S(pg, 'screen') == 'invoice' and pg.locator('.paybtns').count() == 1, (qid, S(pg, 'screen')))
    pg.click('.paybtns [data-pay="Comptant"]'); pg.click('#i-final'); wait(pg, 900)
    qj = store(pg, qid[0]) if qid else {}
    check('5. on-the-spot invoice saved, paid cash', ((qj or {}).get('invoice') or {}).get('method') == 'Comptant' and ((qj or {}).get('invoice') or {}).get('paid') is True and ((qj or {}).get('invoice') or {}).get('number') == 'F-0002', (qj or {}).get('invoice'))
    pg.evaluate("p => { delete window.__store[p]; }", qid[0]) if qid else None   # clean-up (mock)
    pg.evaluate("window.__garageApi.S.screen = null; window.__garageApi.render()"); wait(pg)
    pg.click('.tab-new'); wait(pg, 300); pg.click('[data-act="ph-go"][data-v="client"]'); wait(pg, 500)
    check('5. « Nouveau client » opens the client form', S(pg, 'screen') == 'cform' and pg.locator('#sheet').is_hidden())
    pg.click('[data-act="cform-back"]'); wait(pg, 300)
    # ---------- 6. Plus ----------
    pg.click('.tab[data-t="plus"]'); wait(pg)
    pl = pg.evaluate("[...document.querySelectorAll('nav.ph-menu .ph-row b')].map(b=>b.textContent)")
    check('6. Plus: Tableau de bord, Heures d\'ouverture, Disponibilités des mécanos, Réglages', pl == ['Tableau de bord', 'Heures d\'ouverture', 'Disponibilités des mécanos', 'Trésorerie', 'Réglages'], pl)
    check('6. Plus: « Version complète » row', pg.locator('[data-act="ui-full"]').count() == 1)
    check('6. no sideways scroll (Plus)', no_hscroll(pg))
    pg.click('a[href="#accueil"]'); wait(pg, 400)
    check('6. dashboard opens from Plus, « Plus » tab stays lit', pg.locator('.kpi-big').count() == 1 and pg.locator('.tab[data-t="plus"][aria-current="page"]').count() == 1)
    check('6. no sideways scroll (dashboard)', no_hscroll(pg))
    pg.click('[data-act="ph-back"]'); wait(pg)
    check('6. back arrow returns to Plus', S(pg, 'tab') == 'plus' and pg.locator('[data-act="ui-full"]').count() == 1)
    # hours
    pg.click('a[href="#heures"]'); wait(pg, 400)
    check('6. hours: 14 days with a switch each', pg.locator('.hz').count() == 14 and pg.locator('.hz .switch').count() == 14)
    wd = pg.evaluate("[...document.querySelectorAll('.hz .switch')].map(s => [s.dataset.v, s.getAttribute('aria-checked')])")
    wi = [x for x in wd if x[0] == iso(W)][0]
    check('6. Wednesday is open by default', wi[1] == 'true', wi)
    pg.click('.switch[data-v="%s"]' % iso(W)); wait(pg, 400)
    check('6. switch closes that day (saved)', (store(pg, 'days/' + iso(W)) or {}).get('closed') is True and pg.get_attribute('.switch[data-v="%s"]' % iso(W), 'aria-checked') == 'false')
    pg.click('.switch[data-v="%s"]' % iso(W)); wait(pg, 400)
    check('6. switch opens it again', pg.get_attribute('.switch[data-v="%s"]' % iso(W), 'aria-checked') == 'true' and not (store(pg, 'days/' + iso(W)) or {}).get('closed'))
    pg.select_option('select[data-hz="start"][data-d="%s"]' % iso(W), '09:00'); wait(pg, 400)
    dd = store(pg, 'days/' + iso(W)) or {}
    check('6. opening time changed for that day only', dd.get('start') == '09:00' and dd.get('end') == '17:00' and '9' in txt(pg, '.hz:has(.switch[data-v="%s"]) .hz-d span' % iso(W)), dd)
    pg.select_option('select[data-hz="end"][data-d="%s"]' % iso(W), '08:00'); wait(pg, 400)
    check('6. closing before opening is refused', (store(pg, 'days/' + iso(W)) or {}).get('end') == '17:00' and 'après' in txt(pg, '#toast'))
    pg.evaluate("p => { delete window.__store[p]; }", 'days/' + iso(W))   # clean-up (mock)
    check('6. weekly hours listed (Lun … Dim)', pg.locator('.hz-w').count() == 7)
    check('6. no sideways scroll (hours)', no_hscroll(pg))
    pg.click('a[data-sec="Horaire"]'); wait(pg, 400)
    check('6. « Modifier l\'horaire habituel » opens that part of Réglages', S(pg, 'tab') == 'reglages' and pg.locator('#setform section.sect.cur h3').count() == 1 and txt(pg, '#setform section.sect.cur h3').startswith('Horaire'), txt(pg, '#setform section.sect.cur h3'))
    # settings
    pg.click('.ph-secback >> visible=true'); wait(pg)
    secs = pg.evaluate("[...document.querySelectorAll('#ph-setlist .ph-row b')].map(b=>b.textContent)")
    check('6. Réglages: a list of parts', len(secs) >= 5 and 'Tarifs' in secs and pg.locator('#setform > section.sect:visible').count() == 0, secs)
    ti = secs.index('Tarifs')
    pg.click('[data-act="ph-sec"][data-v="%d"]' % ti); wait(pg)
    check('6. one part at a time + save button', pg.locator('#setform > section.sect:visible').count() == 1 and pg.locator('#s-goal').is_visible() and pg.locator('#s-save').is_visible())
    check('6. no sideways scroll (Réglages)', no_hscroll(pg))
    pg.fill('#s-goal', '25000'); pg.click('#s-save'); wait(pg, 800)
    check('6. saving a part works', (store(pg, 'config/main') or {}).get('goal') == 25000, (store(pg, 'config/main') or {}).get('goal'))
    if S(pg, 'tab') == 'reglages' and pg.locator('#s-goal:visible').count() == 0:
        pg.click('[data-act="ph-sec"][data-v="%d"]' % ti); wait(pg)
    pg.fill('#s-goal', '20000'); pg.click('#s-save'); wait(pg, 800)
    check('6. put back to 20 000 (original)', (store(pg, 'config/main') or {}).get('goal') == 20000)
    # full <-> simple
    pg.click('.tab[data-t="plus"]'); wait(pg); pg.click('[data-act="ui-full"]'); wait(pg, 500)
    check('7. « Version complète »: all tabs, opens Accueil', tabs(pg) == ['accueil', 'agenda', 'clients', 'factures', 'tresor', 'reglages'] and not pg.evaluate("document.body.classList.contains('ui-phone')"), tabs(pg))
    check('7. choice remembered', pg.evaluate("localStorage.getItem('gm.ui')") == 'full')
    check('7. dashboard offers to go back to the simple version', pg.locator('[data-act="ui-phone"]').count() == 1)
    pg.click('[data-act="ui-phone"]'); wait(pg, 500)
    check('7. back to the simple version', tabs(pg) == ['jour', 'clients', '+', 'factures', 'plus'] and pg.evaluate("localStorage.getItem('gm.ui')") is None)
    check('no page errors (main run)', not errs, errs)
    ctx.close()

    # ---------- 8. read-only viewer ----------
    ctx, pg, errs = open_page(br, {'seed': seed, 'readOnly': True})
    wait(pg, 400)
    check('8. read-only: no « + », no free-time rows', pg.locator('.tab-new').is_hidden() and pg.locator('.ph-gap').count() == 0)
    pg.click('.ph-job[data-id="a2"]'); wait(pg, 400)
    check('8. read-only job: no next-step button, no status menu', pg.locator('.nextbtn').count() == 0 and pg.locator('#ph-st').count() == 0 and pg.locator('.rounds .round').count() == 3)
    check('no page errors (read-only)', not errs, errs)
    ctx.close()

    # ---------- 9. big screens stay the full version ----------
    ctx, pg, errs = open_page(br, {'seed': seed}, width=1280, touch=False)
    check('9. computer (1280): full version, opens Accueil', not pg.evaluate("document.body.classList.contains('ui-phone')") and pg.locator('.tab[data-t="accueil"][aria-current="page"]').count() == 1 and tabs(pg) == ['accueil', 'agenda', 'clients', 'factures', 'tresor', 'reglages'], tabs(pg))
    check('9. no « Version simple » chip on a computer', pg.locator('[data-act="ui-phone"]').count() == 0)
    pg.set_viewport_size({'width': 390, 'height': 844}); wait(pg, 500)
    check('9. shrinking the window switches to the simple version', pg.evaluate("document.body.classList.contains('ui-phone')") and tabs(pg) == ['jour', 'clients', '+', 'factures', 'plus'])
    ctx.close()
    ctx, pg, errs = open_page(br, {'seed': seed}, width=768, touch=True)
    check('9. tablet (768): full version', not pg.evaluate("document.body.classList.contains('ui-phone')"))
    ctx.close()

    # ---------- 10. dark mode ----------
    ctx, pg, errs = open_page(br, {'seed': seed}, scheme='dark')
    bg = pg.evaluate("getComputedStyle(document.querySelector('.ph-job')).color")
    check('10. dark mode: light text on the day list', sum(int(x) for x in re.findall(r'\d+', bg)[:3]) > 450, bg)
    pg.screenshot(path=os.path.join(SC, 'p_test_dark.png'))
    pg.click('.ph-job[data-id="a3"]'); wait(pg, 400)
    check('10. dark job page: next step « Terminer la job »', txt(pg, '.nextbtn') == 'Terminer la job')
    check('no page errors (dark)', not errs, errs)
    ctx.close()
    br.close()

ok = sum(1 for _, c in results if c)
print('%d/%d passed' % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
