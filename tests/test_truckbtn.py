"""Bouton Ouvrir / Fermer sur chaque camion (copie locale de Supabase, vraies écritures) :
1. ordi : en haut de chaque colonne de camion, « Ouvrir » (camion fermé) ou « Horaire » + « Fermer » ;
2. « Ouvrir » ouvre l'horaire du camion ; « Ouvrir le camion » le remet en service ;
3. « Fermer » demande d'abord (« Êtes-vous sûr ? », combien de rendez-vous) : non → rien ne change ;
   seulement ce jour-là → ses rendez-vous de ce jour vont dans un autre camion ; jusqu'à nouvel ordre → fermé ;
4. l'horaire propre d'un camion (en permanence) compte pour réserver ;
5. téléphone : la même chose sous les puces des camions ; page Heures : l'interrupteur demande avant de fermer ;
6. le bureau ne voit pas ces boutons."""
import time, re, os, datetime, json
from team_seed import *
from playwright.sync_api import sync_playwright

T0 = datetime.date.today()
def nday(start, ok):
    d = T0 + datetime.timedelta(days=start)
    while not ok(d): d += datetime.timedelta(days=1)
    return d
DD = nday(2, lambda d: d.weekday() < 5); D = DD.isoformat()
def cfgd(): return doc('config/main') or {}
def truck(i): return [t for t in cfgd().get('trucks', []) if t['id'] == i][0]
def hrs(i): return doc('hours/' + i) or {}   # (each truck's schedule: its own document)

otok, pw = seed()
c = cfgd(); c.pop('bookMode', None); c['homePostal'] = 'H4P 2B5'
c['hours'] = {str(x): {'open': True, 'start': '08:00', 'end': '20:00'} for x in range(7)}
c['trucks'] = [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Camion 2', 'on': True, 'mech': 'Ali'}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]
doc_set(otok, 'config/main', c)
snapc = lambda n: {'id': 'c1', 'name': n, 'firstName': n, 'lastName': '', 'postal': 'H4P 2B5', 'phone': '514 555-0101'}
for i in range(2):   # (put in Camion 2 by hand: the route planner keeps them there)
    doc_set(otok, 'jobs/k%d' % i, {'date': D, 'time': '08:00', 'block': 'am', 'durationMin': 60, 'mechanic': 'Ali', 'truck': 'c2', 'pin': True, 'clientId': 'c1', 'client': snapc('Client %d' % i), 'services': ['Inspection'], 'status': 'planifie', 'createdAt': 5})

def show_day(p, d):
    p.goto(BASE + '#agenda'); p.wait_for_timeout(500)
    p.evaluate("(d) => { const A = window.__garageApi, S = A.S; S.day = d; S.view = 'grid'; S.mech = ''; A.render(); }", d); p.wait_for_timeout(500)
def head(p, k): return txt(p, '.colh[data-truck="%s"]' % k)

with sync_playwright() as pl:
    b = pl.chromium.launch()
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1300, 'height': 900}); login(op, 'hassan@garage.test', pw['hassan'])
    show_day(op, D)
    check('computer: a closed truck says « Fermé » with an « Ouvrir » button', 'Fermé' in head(op, 'c3') and op.locator('.colh[data-truck="c3"] [data-act="truck-open"]').count() == 1 and op.locator('.colh[data-truck="c3"] [data-act="truck-close"]').count() == 0, head(op, 'c3'))
    check('computer: an open truck has « Horaire » and « Fermer »', all(op.locator('.colh[data-truck="%s"] [data-act="truck-close"]' % k).count() == 1 and 'Horaire' in head(op, k) for k in ('c1', 'c2')), [head(op, k) for k in ('c1', 'c2')])
    op.screenshot(path=os.path.join(SC, 'truckbtn_pc.png'))

    # ---------- 2. « Ouvrir » : the truck's schedule, then « Ouvrir le camion » ----------
    op.click('.colh[data-truck="c3"] [data-act="truck-open"]'); op.wait_for_selector('#sched .sch-win', timeout=8000)
    check('« Ouvrir » opens the truck\'s schedule (« Horaire de Camion 3 »), saying it is closed', txt(op, '#sch-t') == 'Horaire de Camion 3' and 'Camion 3 est fermé' in txt(op, '#sched'), (txt(op, '#sch-t'), txt(op, '#sched .sch-open')))
    check('…its hours start from the garage\'s (8 h to 20 h)', '8 h à 20 h' in txt(op, '#sched .sch-sum[data-d="%s"]' % D), txt(op, '#sched .sch-sum[data-d="%s"]' % D))
    check('…the button says « Ouvrir le camion »', txt(op, '#sched [data-act="sc-save"]') == 'Ouvrir le camion')
    op.screenshot(path=os.path.join(SC, 'truckbtn_open_sched.png'))
    op.click('#sched [data-act="sc-save"]')
    check('opened: « Camion 3 est ouvert »', toast_has(op, 'Camion 3 est ouvert'))
    op.wait_for_timeout(800)
    check('…saved in service on the server', truck('c3').get('on') is True, truck('c3'))
    show_day(op, D)
    check('…its column now has « Horaire » and « Fermer »', op.locator('.colh[data-truck="c3"] [data-act="truck-close"]').count() == 1, head(op, 'c3'))

    # ---------- 3. « Fermer » asks first ----------
    op.click('.colh[data-truck="c2"] [data-act="truck-close"]'); op.wait_for_selector('#sheet:not([hidden]) [data-act="truck-close-go"]', timeout=8000)
    sh = txt(op, '#sheet')
    check('« Fermer » asks first: « Êtes-vous sûr de vouloir fermer Camion 2 ? »', 'Êtes-vous sûr de vouloir fermer Camion 2' in sh, sh[:200])
    check('…says how many appointments are in it and where they go', '2 rendez-vous à venir sont dans ce camion' in sh and 'autre camion' in sh and 'pas avisés' in sh, sh[:400])
    check('…two choices: only that day, or until opened again', op.locator('#sheet [data-act="truck-close-go"][data-v="day"]').count() == 1 and op.locator('#sheet [data-act="truck-close-go"][data-v="all"]').count() == 1)
    op.screenshot(path=os.path.join(SC, 'truckbtn_close_ask.png'))
    op.click('#sheet [data-act="sheet-close"][data-v="keep"]'); op.wait_for_timeout(800)
    check('« Non, le laisser ouvert » : nothing changes', truck('c2').get('on') is True and not hrs('c2'), (truck('c2'), hrs('c2')))
    op.click('.colh[data-truck="c2"] [data-act="truck-close"]'); op.wait_for_selector('#sheet:not([hidden]) [data-act="truck-close-go"]', timeout=8000)
    op.click('#sheet [data-act="truck-close-go"][data-v="day"]')
    check('only that day: « Camion 2 fermé … »', toast_has(op, 'Camion 2 fermé'))
    ok = False
    for _ in range(30):
        tk = [psql("select data->>'truck' from public.docs where path='jobs/k%d'" % i) for i in range(2)]
        if (hrs('c2').get('dates') or {}).get(D) == {'on': False} and all(t and t != 'c2' for t in tk): ok = True; break
        time.sleep(0.5)
    check('…closed that day only (still in service), its 2 appointments of that day moved to another truck', ok and truck('c2').get('on') is True, (truck('c2'), hrs('c2'), tk))
    show_day(op, D)
    check('…that day its column says « Fermé ce jour-là » with « Ouvrir »', 'Fermé ce jour-là' in head(op, 'c2') and op.locator('.colh[data-truck="c2"] [data-act="truck-open"]').count() == 1, head(op, 'c2'))
    other = (DD + datetime.timedelta(days=7)).isoformat()
    show_day(op, other)
    check('…another day it is open as usual', 'Fermé' not in head(op, 'c2') and op.locator('.colh[data-truck="c2"] [data-act="truck-close"]').count() == 1, head(op, 'c2'))
    # open it again for that day from its schedule
    show_day(op, D)
    op.click('.colh[data-truck="c2"] [data-act="truck-open"]'); op.wait_for_selector('#sched .sch-win', timeout=8000)
    check('« Ouvrir » on a day it is closed: its schedule with that day « Fermé »', txt(op, '#sch-t') == 'Horaire de Camion 2' and txt(op, '#sched .sch-sum[data-d="%s"]' % D) == 'Fermé' and txt(op, '#sched [data-act="sc-save"]') == 'Enregistrer', txt(op, '#sched .sch-sum[data-d="%s"]' % D))
    op.click('#sched .sch-dh [data-act="sc-col"][data-v="%s"]' % D); op.wait_for_timeout(200)
    op.click('#sched [data-act="sc-save"]'); op.wait_for_timeout(1200)
    check('…painted open and saved: open that day again (8 h to 17 h)', (hrs('c2').get('dates') or {}).get(D, {}).get('on') is True and hrs('c2')['dates'][D].get('start') == '08:00' and hrs('c2')['dates'][D].get('end') == '17:00', hrs('c2'))

    # ---------- 4. a truck's own hours count for booking (permanent: Camion 3 never on Sundays) ----------
    op.click('.colh[data-truck="c3"] [data-act="truck-open"]'); op.wait_for_selector('#sched .sch-win', timeout=8000)
    sun = op.evaluate("[...document.querySelectorAll('#sched .sch-sum')].map(e => e.dataset.d)[0]")
    op.click('#sched .sch-dh [data-act="sc-col"][data-v="%s"]' % sun); op.wait_for_timeout(200)
    op.click('#sched input[data-v="forever"]'); op.wait_for_timeout(200)
    op.click('#sched [data-act="sc-save"]'); op.wait_for_timeout(1200)
    w = hrs('c3').get('week') or {}
    check('permanent hours of a truck: Camion 3 closed every Sunday, other days the garage\'s hours', w.get('0', {}).get('on') is False and w.get('3', {}).get('on') is True and w.get('3', {}).get('start') == '08:00', w)
    nsun = nday(8, lambda d: d.weekday() == 6).isoformat()
    show_day(op, nsun)
    check('…a later Sunday: its column says « Fermé ce jour-là »', 'Fermé ce jour-là' in head(op, 'c3'), head(op, 'c3'))
    sl = op.evaluate("[document.querySelectorAll('.slot.open[data-c=\"c3\"]').length, document.querySelectorAll('.slot.open[data-c=\"c2\"]').length]")
    check('…and nobody can book in it that day (no open case in its column; Camion 2 has some)', sl[0] == 0 and sl[1] > 0, sl)

    # ---------- closed until opened again ----------
    show_day(op, D)
    op.click('.colh[data-truck="c1"] [data-act="truck-close"]'); op.wait_for_selector('#sheet:not([hidden]) [data-act="truck-close-go"]', timeout=8000)
    op.click('#sheet [data-act="truck-close-go"][data-v="all"]')
    check('« jusqu\'à ce que je le rouvre » : Camion 1 out of service', toast_has(op, 'Camion 1 fermé') and wait_for(op, '() => true') and (time.sleep(1.0) or truck('c1').get('on') is False), truck('c1'))
    show_day(op, D)
    check('…the truck chip says « fermé »', 'fermé' in txt(op, '[data-act="mech"][data-v="c1"]'), txt(op, '[data-act="mech"][data-v="c1"]'))
    check('computer: no errors', not ERRS, ERRS[:3])

    # ---------- 5. phone + the hours page ----------
    pc = ctx(b, phone=True); pp = page(pc, 'owner-phone'); login(pp, 'hassan@garage.test', pw['hassan'])
    pp.evaluate("(d) => { const A = window.__garageApi, S = A.S; S.day = d; S.mech = 'c2'; S.tab = 'jour'; A.render(); }", other); pp.wait_for_timeout(600)
    if pp.locator('.tkbar').count() == 0:
        pp.goto(BASE + '#agenda'); pp.wait_for_timeout(500); pp.evaluate("(d) => { const A = window.__garageApi, S = A.S; S.day = d; S.mech = 'c2'; A.render(); }", other); pp.wait_for_timeout(600)
    check('phone: under the truck chips, « Camion 2 · ouvert » with « Horaire » and « Fermer »', 'Camion 2 · ouvert' in txt(pp, '.tkbar') and pp.locator('.tkbar [data-act="truck-close"]').count() == 1, txt(pp, '.tkbar'))
    check('phone: no sideways scroll', no_hscroll(pp))
    pp.screenshot(path=os.path.join(SC, 'truckbtn_phone.png'))
    pp.click('.tkbar [data-act="truck-close"]'); pp.wait_for_selector('#sheet:not([hidden]) [data-act="truck-close-go"]', timeout=8000)
    check('phone: « Fermer » asks first too', 'Êtes-vous sûr' in txt(pp, '#sheet'))
    pp.click('#sheet [data-act="sheet-close"][data-v="keep"]'); pp.wait_for_timeout(500)
    pp.evaluate("(d) => { const A = window.__garageApi, S = A.S; S.mech = 'c1'; A.render(); }", other); pp.wait_for_timeout(500)
    check('phone: a closed truck: « fermé » with « Ouvrir »', 'Camion 1 · fermé' in txt(pp, '.tkbar') and pp.locator('.tkbar [data-act="truck-open"]').count() == 1, txt(pp, '.tkbar'))
    pp.click('.tkbar [data-act="truck-open"]'); pp.wait_for_selector('#sched .sch-win', timeout=8000)
    check('phone: « Ouvrir » opens its schedule', txt(pp, '#sch-t') == 'Horaire de Camion 1' and txt(pp, '#sched [data-act="sc-save"]') == 'Ouvrir le camion')
    pp.click('#sched .sch-foot [data-act="sc-close"]'); pp.wait_for_timeout(400)
    pp.goto(BASE + '#heures'); pp.wait_for_timeout(800)
    if pp.locator('#hz-trucks').count():
        pp.click('#hz-trucks [data-act="truck-toggle"][data-v="c2"]')
        asked = wait_for(pp, "() => !!document.querySelector('#sheet:not([hidden]) [data-act=\"truck-close-go\"]')", 6000)
        check('hours page: the switch of an open truck asks before closing (nothing closed yet)', asked and truck('c2').get('on') is True, (txt(pp, '#sheet')[:120], pp.locator('#sched').count(), truck('c2')))
        pp.click('#sheet [data-act="sheet-close"][data-v="keep"]'); pp.wait_for_timeout(400)
        pp.click('#hz-trucks [data-act="truck-toggle"][data-v="c1"]'); pp.wait_for_timeout(600)
        check('hours page: the switch of a closed truck opens its schedule', pp.locator('#sched .sch-win').count() == 1 and txt(pp, '#sch-t') == 'Horaire de Camion 1')
        pp.click('#sched .sch-foot [data-act="sc-close"]'); pp.wait_for_timeout(300)
    else:
        check('hours page reachable', False, 'no #hz-trucks')
    check('phone: no errors', not ERRS, ERRS[:3])

    # ---------- 7. one schedule per truck: « Modifier l'horaire » ----------
    D1 = (DD + datetime.timedelta(days=1)).isoformat()
    c1_before = truck('c1')
    show_day(op, D)
    op.click('[data-act="sched"][data-v="garage"]'); op.wait_for_selector('#sched .sch-win', timeout=8000)
    tabs = op.evaluate("[...document.querySelectorAll('#sched .sch-tabs .chip')].map(b => b.textContent.trim())")
    check('« Modifier l\'horaire » : one schedule per truck (a tab each) + the base hours', txt(op, '#sch-t').startswith('Horaire de Camion') and len(tabs) == 4 and tabs[-1].startswith('De base'), (txt(op, '#sch-t'), tabs))
    op.click('#sched .sch-tabs [data-v="truck:c2"]'); op.wait_for_timeout(300)
    check('tab Camion 2 → « Horaire de Camion 2 »', txt(op, '#sch-t') == 'Horaire de Camion 2')
    op.click('#sched .sch-dh [data-act="sc-col"][data-v="%s"]' % D); op.wait_for_timeout(200)
    op.click('#sched .sch-tabs [data-v="truck:c3"]'); op.wait_for_timeout(300)
    check('switching to Camion 3 keeps Camion 2\'s change (« • » on its tab, said under the grid)', '•' in txt(op, '#sched .sch-tabs [data-v="truck:c2"]') and 'Aussi changé : Camion 2' in txt(op, '#sch-count'), (txt(op, '#sched .sch-tabs'), txt(op, '#sch-count')))
    op.click('#sched .sch-dh [data-act="sc-col"][data-v="%s"]' % D1); op.wait_for_timeout(200)
    op.click('#sched [data-act="sc-save"]')
    check('one « Enregistrer » saves both (« 2 horaires »)', toast_has(op, '2 horaires'))
    op.wait_for_timeout(1200)
    check('…Camion 2 closed on %s, Camion 3 closed on %s: each its own, the third one untouched' % (D, D1), (hrs('c2').get('dates') or {}).get(D) == {'on': False} and (hrs('c3').get('dates') or {}).get(D1) == {'on': False} and D1 not in (hrs('c2').get('dates') or {}) and truck('c1') == c1_before, (hrs('c2'), hrs('c3'), truck('c1')))

    # ---------- 6. the office ----------
    lc = ctx(b); lp = page(lc, 'lina'); lp.set_viewport_size({'width': 1300, 'height': 900}); login(lp, 'lina@garage.test', pw['lina'])
    show_day(lp, D)
    check('the office (it may change the hours): « Horaire / Fermer » on the trucks in service, no « Ouvrir » for the one out of service (owner)', lp.locator('.colh[data-truck="c3"] [data-act="truck-close"]').count() == 1 and lp.locator('.colh[data-truck="c1"] [data-act="truck-open"]').count() == 0, [txt(lp, '.colh[data-truck="%s"]' % k) for k in ('c1', 'c2', 'c3')])
    b.close()
summary()
