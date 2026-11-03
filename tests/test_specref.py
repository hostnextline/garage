"""La fiche technique remplie toute seule (copie locale de Supabase, vraies écritures) :
1. réservation : dès l'année + la marque + le modèle, l'huile (litres, viscosité, filtre) d'après la liste de référence ;
   plusieurs moteurs cette année-là : « Quel moteur ? » ; le moteur choisi part avec la job ;
2. page de la job : la fiche remplie, « à confirmer » ; choisir le moteur ; « Confirmer pour ce moteur » → la fiche du garage ;
3. le VIN scanné donne le moteur exact : la fiche suit (et le dit) ;
4. deux versions d'un même moteur qui ne prennent pas la même huile (traction / intégrale) : « Quelle version ? » ;
5. un véhicule hors de la liste : on le dit, la fiche se remplit une fois comme avant."""
import time, re, os, datetime, json
from team_seed import *
from playwright.sync_api import sync_playwright

REF = json.load(open(os.path.join(SC, 'specref', 'specref_all.json')))
def ref(model, year, displ, turbo=None, fuel='gas', code=None):
    for r in REF:
        if r['model'] == model and r['from'] <= year <= r['to'] and abs(r['displL'] - displ) < 0.06 and (turbo is None or r['turbo'] == turbo) and r['fuel'] == fuel and (code is None or code in r['engine']): return r
def L(x): return ('%g' % float(x)).replace('.', ',') + ' L'
CIV = '2HGFC2F58JH512345'
T0 = datetime.date.today()
D = T0 + datetime.timedelta(days=2)
while D.weekday() >= 5: D += datetime.timedelta(days=1)
D = D.isoformat()

otok, pw = seed()
c = doc('config/main'); c.pop('bookMode', None); c['homePostal'] = 'H4P 2B5'
c['hours'] = {str(x): {'open': True, 'start': '08:00', 'end': '20:00'} for x in range(7)}
doc_set(otok, 'config/main', c)
cl1 = doc('clients/c1')
snap = {'id': 'c1', 'firstName': 'Marie', 'lastName': 'Tremblay', 'name': 'Marie Tremblay', 'phone': cl1['phone'], 'address': cl1['address'], 'postal': cl1['postal'], 'geo': cl1['geo']}
for jid, veh in (('v1', {'year': '2017', 'make': 'Ford', 'model': 'F-150'}), ('v2', {'year': '2018', 'make': 'Honda', 'model': 'Civic'}), ('v3', {'year': '2019', 'make': 'Chevrolet', 'model': 'Equinox'}), ('v4', {'year': '2016', 'make': 'Toyota', 'model': 'Corolla'})):
    doc_set(otok, 'jobs/' + jid, {'date': T0.isoformat(), 'time': '15:00', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'client': snap, 'vehicle': veh,
                                  'services': ["Changement d'huile et filtre"], 'service': "Changement d'huile et filtre", 'status': 'planifie', 'createdAt': 1})
def veh(jid): return (doc('jobs/' + jid) or {}).get('vehicle') or {}
def open_job(p, jid):
    p.evaluate("(id) => { const A = window.__garageApi, S = A.S; S.tab = 'agenda'; S.screen = 'job'; S.jobId = id; A.render(); }", jid); p.wait_for_timeout(500)
    p.evaluate("document.getElementById('veh-fold') && (document.getElementById('veh-fold').open = true)"); p.wait_for_timeout(200)   # (« Véhicule et fiche technique » unfolded)
def card(p): return txt(p, '#speccard')

with sync_playwright() as pl:
    b = pl.chromium.launch()
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1300, 'height': 900}); login(op, 'hassan@garage.test', pw['hassan'])

    # ---------- 1. the booking form ----------
    op.goto(BASE + '#agenda'); op.wait_for_timeout(600)
    op.click('#top [data-act="new"]'); op.wait_for_selector('#cs-q', timeout=8000)
    op.fill('#cs-q', 'Marie'); op.wait_for_timeout(400); op.locator('#cs-results .crow').first.click(); op.wait_for_selector('#f-year', state='attached', timeout=8000)
    op.evaluate("(d) => { const t = document.getElementById('f-date'); t.value = d; t.dispatchEvent(new Event('change', {bubbles:true})); }", D); op.wait_for_timeout(500)
    if op.locator('#blkpick [data-v="pm"]').count(): op.evaluate("document.querySelector('#blkpick [data-v=\"pm\"]').click()"); op.wait_for_timeout(300)
    rc = ref('Corolla', 2018, 1.8)
    op.fill('#f-year', '2018'); op.fill('#f-make', 'Toyota'); op.fill('#f-model', 'Corolla'); op.wait_for_timeout(700)
    sm = txt(op, '#specmsg')
    check('booking: 2018 Toyota Corolla typed → the oil shows at once (%s, %s, filter %s)' % (L(rc['oilL']), rc['oilVisc'], rc['oilFilter']), 'Huile : ' + L(rc['oilL']) + ' · ' + rc['oilVisc'] + ' · filtre ' + rc['oilFilter'] in sm and 'liste de référence, à confirmer' in sm and '1,8 L 4 cyl.' in sm, sm)
    op.fill('#f-make', 'Honda'); op.fill('#f-model', 'Civic'); op.wait_for_timeout(700)
    chips = op.evaluate("[...document.querySelectorAll('#specmsg [data-act=\"form-eng\"]')].map(b => b.textContent.replace(/\\s+/g, ' ').trim())")
    check('booking: 2018 Honda Civic → « Quel moteur ? » (1,5 L turbo · 2,0 L · 2,0 L turbo Type R), each with its oil', 'Quel moteur ?' in txt(op, '#specmsg') and len(chips) == 3 and any(x.startswith('1,5 L 4 cyl. turbo') and '3,5 L' in x for x in chips) and any(x.startswith('2,0 L 4 cyl. ·') for x in chips), chips)
    op.locator('#specmsg [data-act="form-eng"]', has_text='1,5 L 4 cyl. turbo').click(); op.wait_for_timeout(400)
    sm = txt(op, '#specmsg')
    check('…tap « 1,5 L turbo » → its oil: 3,5 L · 0W-20', 'Huile : 3,5 L · 0W-20' in sm and '1,5 L 4 cyl. turbo' in sm, sm)
    op.screenshot(path=os.path.join(SC, 'specref_form.png'))
    op.evaluate("document.getElementById('jobform').requestSubmit()"); op.wait_for_timeout(3500)
    nj = json.loads(psql("select coalesce(json_agg(data->'vehicle'), '[]') from public.docs where path like 'jobs/%%' and data->>'date' = '%s'" % D))
    check('…saved with the job (real base): engine 1,5 L turbo', len(nj) == 1 and nj[0].get('displL') == 1.5 and nj[0].get('turbo') is True and nj[0].get('engine') == '1,5 L 4 cyl. turbo', nj)
    # not in the list
    op.click('#top [data-act="new"]'); op.wait_for_selector('#cs-q', timeout=8000)
    op.fill('#cs-q', 'Marie'); op.wait_for_timeout(400); op.locator('#cs-results .crow').first.click(); op.wait_for_selector('#f-year', state='attached', timeout=8000)
    op.fill('#f-year', '2015'); op.fill('#f-make', 'Lada'); op.fill('#f-model', 'Niva'); op.wait_for_timeout(700)
    check('a vehicle not in the list: said plainly (the sheet is filled once, at the job)', 'Pas dans la liste de référence' in txt(op, '#specmsg'), txt(op, '#specmsg'))
    op.evaluate("document.querySelector('#sheet [data-act=\"sheet-close\"]') && document.querySelector('#sheet [data-act=\"sheet-close\"]').click()"); op.wait_for_timeout(500)

    # ---------- 2. the job page ----------
    open_job(op, 'v4')
    c4 = card(op)
    check('job page, 2016 Corolla (one engine that year): the sheet is already filled, « à confirmer »', 'Huile : ' + L(rc['oilL']) in c4 and 'liste de référence' in c4 and 'Un seul moteur' in c4, c4)
    open_job(op, 'v1')
    ch1 = op.evaluate("[...document.querySelectorAll('#speccard [data-act=\"spec-eng\"]')].map(b => b.textContent.replace(/\\s+/g, ' ').trim())")
    check('job page, 2017 Ford F-150: « Quel moteur ? » with its engines', 'Quel moteur ?' in card(op) and len(ch1) >= 3 and any(x.startswith('5,0 L 8 cyl.') for x in ch1), ch1)
    rf = ref('F-150', 2017, 5.0)
    op.locator('#speccard [data-act="spec-eng"]', has_text='5,0 L 8 cyl.').click(); op.wait_for_timeout(1500)
    v1 = veh('v1')
    check('…tap « 5,0 L V8 » → saved on the job (real base)', v1.get('displL') == 5.0 and v1.get('cyl') == 8 and v1.get('engine') == '5,0 L 8 cyl.', v1)
    c1 = card(op)
    check('…the sheet shows its oil (%s, %s)' % (L(rf['oilL']), rf['oilVisc']), 'Huile : ' + L(rf['oilL']) + ' · ' + rf['oilVisc'] in c1 and 'à confirmer' in c1, c1)
    op.click('#speccard [data-act="spec-edit"]'); op.wait_for_selector('#specform', timeout=8000)
    check('« Confirmer pour ce moteur » : the form is already filled from the list (oil, viscosity, filter)', op.input_value('#sp-oilL') == str(rf['oilL']).replace('.', ',') and op.input_value('#sp-oilVisc') == rf['oilVisc'] and op.input_value('#sp-oilFilter') == rf['oilFilter'] and 'liste de référence' in txt(op, '#sheet'), (op.input_value('#sp-oilL'), op.input_value('#sp-oilVisc'), op.input_value('#sp-oilFilter')))
    op.click('#sp-save'); toast_has(op, 'Fiche technique enregistrée'); op.wait_for_timeout(1200)
    sp = json.loads(psql("select coalesce(json_agg(data), '[]') from public.docs where col = 'specs'") or '[]')
    check('…saved as the garage\'s sheet (real base, confirmed by Hassan)', len(sp) == 1 and sp[0].get('oilL') == rf['oilL'] and sp[0].get('displL') == 5.0 and sp[0].get('by'), sp)
    open_job(op, 'v1')
    check('…the card now says « Confirmé par »', 'Confirmé par' in card(op) and 'liste de référence' not in card(op), card(op))

    # ---------- 3. the VIN gives the exact engine: the sheet follows ----------
    open_job(op, 'v2')
    op.locator('#speccard [data-act="spec-eng"]', has_text='1,5 L 4 cyl. turbo').click(); op.wait_for_timeout(1500)
    check('2018 Civic set to « 1,5 L turbo » by hand: oil 3,5 L', 'Huile : 3,5 L' in card(op) and veh('v2').get('turbo') is True, card(op))
    op.click('[data-act="scan-job"]'); op.wait_for_selector('#scan-body'); op.wait_for_timeout(500)
    op.click('[data-act="scan-type"]'); op.fill('#scan-in', CIV); op.click('[data-act="scan-typed"]')
    op.wait_for_selector('#scan-body .vehsum', timeout=12000)
    r2 = ref('Civic', 2018, 2.0, turbo=False)
    check('the VIN says 2,0 L: the scan summary already shows its oil (%s)' % L(r2['oilL']), 'Huile : ' + L(r2['oilL']) in txt(op, '#scan-body'), txt(op, '#scan-body'))
    op.click('[data-act="scan-use"]')
    check('« Mettre sur la job » : « Véhicule mis à jour · fiche technique : 2,0 L 4 cyl. »', toast_has(op, 'fiche technique : 2,0 L 4 cyl.'))
    op.wait_for_timeout(1000)
    v2 = veh('v2')
    check('…saved: the VIN\'s engine replaces the one chosen by hand (no more turbo)', v2.get('vin') == CIV and v2.get('displL') == 2 and not v2.get('turbo') and not v2.get('refVar') and v2.get('engine') == '2,0 L 4 cyl.', v2)
    check('…the sheet follows: %s' % L(r2['oilL']), 'Huile : ' + L(r2['oilL']) in card(op), card(op))

    # ---------- 4. two versions of an engine (front / all-wheel drive) ----------
    open_job(op, 'v3')
    ch3 = op.evaluate("[...document.querySelectorAll('#speccard [data-act=\"spec-eng\"]')].map(b => b.textContent.replace(/\\s+/g, ' ').trim())")
    check('2019 Equinox: the 1,5 L turbo in front-wheel and all-wheel drive are two choices (not the same oil)', any('1,5 L 4 cyl. turbo' in x and 'FWD' in x for x in ch3) and any('1,5 L 4 cyl. turbo' in x and 'AWD' in x for x in ch3), ch3)
    ra = ref('Equinox', 2019, 1.5, turbo=True, code='AWD')
    op.locator('#speccard [data-act="spec-eng"]', has_text='AWD').first.click(); op.wait_for_timeout(1500)
    check('…tap the all-wheel drive one → its oil (%s)' % L(ra['oilL']), 'Huile : ' + L(ra['oilL']) in card(op) and veh('v3').get('refVar'), (card(op), veh('v3')))
    check('computer: no errors', not ERRS, ERRS[:3])

    # ---------- the phone ----------
    pc = ctx(b, phone=True); pp = page(pc, 'saleh-phone'); login(pp, 'saleh@garage.test', pw['saleh'])
    doc_set(otok, 'jobs/v5', {'date': T0.isoformat(), 'time': '16:00', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'client': snap, 'vehicle': {'year': '2018', 'make': 'Honda', 'model': 'Civic'}, 'services': ["Changement d'huile et filtre"], 'status': 'planifie', 'createdAt': 1})
    pp.evaluate('window.__supa.resync(true)'); pp.wait_for_timeout(1200)
    open_job(pp, 'v5')
    pp.evaluate("document.getElementById('veh-fold') && (document.getElementById('veh-fold').open = true)"); pp.wait_for_timeout(300)
    check('phone (mechanic): the engine choice is there on his job', pp.locator('#speccard [data-act="spec-eng"]').count() == 3, card(pp))
    check('phone: no sideways scroll', no_hscroll(pp))
    pp.screenshot(path=os.path.join(SC, 'specref_phone.png'), full_page=True)
    check('phone: no errors', not ERRS, ERRS[:3])
    b.close()
summary()
