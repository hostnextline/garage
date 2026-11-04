"""Chaque camion porte le nom du mécano qui le conduit, et on n'assigne plus les mécanos (copie locale de Supabase, vraies écritures) :
1. l'agenda : la colonne « Saleh » est la route de Saleh ; plus de « Mécano à choisir », plus de « Qui part avec quel camion » ;
2. Réglages → Camions : un seul nom (la liste des mécanos proposée) ; renommer le camion change le mécano de ses rendez-vous à venir ;
   deux camions du même nom : refusé ;
3. le mécano voit dans son app la route du camion à son nom ;
4. glisser un rendez-vous dans le camion « Ali » : c'est Ali ;
5. seul l'horaire du camion compte : pas de « disponibilités » ; « Équipe et accès » ne choisit plus de camion ;
6. un camion fermé : changer ses heures (ou « Ouvrir le camion ») l'ouvre tout seul ; dans la semaine, une puce dit « fermé »
   seulement s'il ne roule pas de la semaine ;
7. en anglais."""
import json, os, time, datetime
from team_seed import *
from playwright.sync_api import sync_playwright
T0 = datetime.date.today(); TODAY = T0.isoformat(); TOM = (T0 + datetime.timedelta(days=1)).isoformat()
def cfgd(): return doc('config/main') or {}
def truck(k): return [t for t in cfgd().get('trucks', []) if t['id'] == k][0]
def job(i): return doc('jobs/' + i) or {}
def wait_true(f, n=25):
    for _ in range(n):
        if f(): return True
        time.sleep(0.4)
    return False
otok, pw = seed()
c = cfgd(); c['hours'] = {str(x): {'open': True, 'start': '08:00', 'end': '20:00'} for x in range(7)}; doc_set(otok, 'config/main', c)
snap = {'id': 'c1', 'name': 'Marie Tremblay', 'firstName': 'Marie', 'lastName': 'Tremblay', 'phone': '514 555-0101', 'postal': 'H2J 2L3'}
doc_set(otok, 'jobs/t1', {'date': TOM, 'time': '09:00', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'client': snap, 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 5})
def show(p, d, view='grid'):
    p.goto(BASE + '#agenda'); p.wait_for_timeout(500)
    p.evaluate("([d, v]) => { const A = window.__garageApi, S = A.S; S.day = d; S.view = v; S.mech = ''; S.screen = null; A.render(); }", [d, view]); p.wait_for_timeout(700)
def settings(p):
    p.evaluate("window.__allSettings = true"); p.goto(BASE + '#reglages'); p.wait_for_selector('#trucks-box', timeout=10000); p.wait_for_timeout(300)
with sync_playwright() as pl:
    b = pl.chromium.launch()
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1300, 'height': 1100}); login(op, 'hassan@garage.test', pw['hassan'])
    # ---------- 1. the agenda ----------
    show(op, TOM)
    h1 = txt(op, '.colh[data-truck="c1"]')
    check('agenda: the column is « Saleh » (the truck named after him), no « Mécano à choisir », no « Qui part avec quel camion »', h1.startswith('Saleh') and 'Mécano à choisir' not in txt(op, '#main') and op.locator('#crewbox, [data-crew]').count() == 0, h1)
    # ---------- 2. Réglages → Camions ----------
    settings(op)
    check('Réglages → Camions: one name per truck (« le mécano qui le conduit »), no « Mécano habituel » list', op.locator('#tk-m-c1').count() == 0 and op.input_value('#tk-n-c1') == 'Saleh' and 'le mécano qui le conduit' in txt(op, 'label[for="tk-n-c1"]'))
    check('…it says whose route it is (« La route de Saleh »), with the team\'s names to pick from', 'La route de Saleh' in txt(op, '.tk-row[data-id="c1"]') and op.evaluate("[...document.querySelectorAll('#tk-mechs option')].map(o => o.value)") == ['Hassan', 'Saleh', 'Ali'])
    op.fill('#tk-n-c1', 'Camion Rouge'); op.wait_for_timeout(200)
    check('typing a name that is nobody: « Aucun mécano à ce nom. »', 'Aucun mécano à ce nom' in txt(op, '.tk-row[data-id="c1"]'))
    op.click('#s-save')
    check('saved: the truck is « Camion Rouge », nobody\'s route; its coming appointment has no mechanic now', wait_true(lambda: truck('c1').get('name') == 'Camion Rouge' and job('t1').get('mechanic') == ''), (truck('c1'), job('t1').get('mechanic')))
    settings(op); op.fill('#tk-n-c1', 'saleh'); op.wait_for_timeout(200)
    check('typing « saleh » (any case): « La route de Saleh »', 'La route de Saleh' in txt(op, '.tk-row[data-id="c1"]'))
    op.click('#s-save')
    check('saved: his appointment is Saleh\'s again', wait_true(lambda: job('t1').get('mechanic') == 'Saleh'), job('t1').get('mechanic'))
    settings(op); op.fill('#tk-n-c2', 'Saleh'); op.click('#s-save'); op.wait_for_timeout(400)
    check('two trucks with the same name: refused (« Un nom par camion »)', toast_has(op, 'Un nom par camion') and truck('c2').get('name') == 'Ali')
    # ---------- 4. drag into Ali's truck ----------
    show(op, TOM)
    a = op.locator('.appt[data-drag="t1"]'); a.evaluate("e => e.scrollIntoView({block:'center'})"); op.wait_for_timeout(300); ba = a.bounding_box()
    sb = op.locator('.col[data-col="c2"] .slot[data-t="11:00"]').bounding_box()
    op.mouse.move(ba['x'] + ba['width'] / 2, ba['y'] + 5); op.mouse.down(); op.mouse.move(ba['x'] + 30, ba['y'] + 20, steps=4)
    op.mouse.move(sb['x'] + sb['width'] / 2, sb['y'] + 8, steps=10); op.wait_for_timeout(150); op.mouse.move(sb['x'] + sb['width'] / 2, sb['y'] + 9, steps=2); op.mouse.up()
    op.wait_for_selector('#sheet [data-act="drop-yes"]', timeout=6000)
    check('drag into the « Ali » truck: « Après » says Ali', 'Ali' in txt(op, '#sheet').split('Après')[1], txt(op, '#sheet')[:200])
    op.click('#sheet [data-act="drop-yes"]')
    check('…saved: truck Ali, mechanic Ali (from the truck\'s name)', wait_true(lambda: job('t1').get('truck') == 'c2' and job('t1').get('mechanic') == 'Ali'), {k: job('t1').get(k) for k in ('truck', 'mechanic', 'time')})
    # ---------- 6. a closed truck opens by its hours; the week chips ----------
    show(op, TOM)
    op.click('[data-act="sched"][data-v="garage"]'); op.wait_for_selector('#sched .sch-win', timeout=8000)
    op.click('#sched .sch-tabs [data-v="truck:c3"]'); op.wait_for_timeout(300)
    check('closed truck\'s tab: « Camion 3 est fermé… » and the button « Ouvrir le camion »', 'Camion 3 est fermé' in txt(op, '#sched .sch-open') and txt(op, '#sched [data-act="sc-save"]') == 'Ouvrir le camion', txt(op, '#sched .sch-open'))
    op.click('#sched [data-act="sc-save"]')
    check('« Ouvrir le camion » (nothing changed): it opens', toast_has(op, 'Camion 3 est ouvert') and wait_true(lambda: truck('c3').get('on') is True), truck('c3'))
    doc_set(otok, 'config/main', dict(cfgd(), trucks=[dict(t, on=False) if t['id'] == 'c3' else t for t in cfgd()['trucks']])); op.reload(); op.wait_for_timeout(1500)   # (changed from outside: fresh)
    show(op, TOM)
    op.click('[data-act="sched"][data-v="garage"]'); op.wait_for_selector('#sched .sch-win', timeout=8000)
    op.click('#sched .sch-tabs [data-v="truck:c3"]'); op.wait_for_timeout(300)
    op.click('#sched .sch-dh [data-act="sc-col"][data-v="%s"]' % TOM if op.locator('#sched .sch-dh [data-act="sc-col"][data-v="%s"]' % TOM).count() else '#sched .sch-dh [data-act="sc-col"]'); op.wait_for_timeout(200)
    op.click('#sched [data-act="sc-save"]')
    check('a closed truck given hours: it opens by itself (« Camion 3 est ouvert »)', toast_has(op, 'Camion 3 est ouvert') and wait_true(lambda: truck('c3').get('on') is True), truck('c3'))
    doc_set(otok, 'hours/c2', {'week': None, 'dates': {TODAY: {'on': False}}}); op.reload(); op.wait_for_timeout(1500)
    show(op, TODAY, 'week')
    rest = [d for d in [(T0 + datetime.timedelta(days=i)) for i in range(1, 7)] if d.isocalendar()[1] == T0.isocalendar()[1]]
    chip = txt(op, '[data-act="mech"][data-v="c2"]')
    check('week view: « Ali » closed today but open later this week → no « fermé » on its chip', ('fermé' not in chip) if rest else ('fermé' in chip), chip)
    show(op, TODAY, 'grid'); op.wait_for_timeout(300)
    chip = txt(op, '[data-act="mech"][data-v="c2"]')
    check('day view (today): « Ali · fermé »', 'fermé' in chip, chip)
    # ---------- 5. no availability, no truck in « Équipe et accès » ----------
    op.goto(BASE + '#accueil'); op.wait_for_selector('#tiles', timeout=10000)
    tl = op.evaluate("[...document.querySelectorAll('#tiles .tile b')].map(b => b.textContent)")
    check('home: no « Disponibilités des mécanos » (the truck\'s schedule decides)', 'Disponibilités des mécanos' not in tl and 'Agenda' in tl, tl)
    op.goto(BASE + '#dispos'); op.wait_for_timeout(700)
    check('« #dispos » (an old link): « Horaire des camions », the truck\'s schedule decides', 'Horaire des camions' in txt(op, '#top') and 'horaire du camion' in txt(op, '#main'), txt(op, '#main')[:160])
    op.goto(BASE + '#equipe'); op.wait_for_selector('.eqp', timeout=12000); op.wait_for_timeout(500)
    card = op.locator('.eqp', has_text='saleh@garage.test').inner_text()
    check('« Équipe et accès »: Saleh\'s card says « 🚚 saleh » (the truck in his name, as typed)', '🚚 saleh' in card.lower(), card[:200])
    op.locator('.eqp', has_text='saleh@garage.test').locator('[data-act="eq-edit"]').click(); op.wait_for_timeout(300)
    check('…no « Son camion » to choose, on his card or for a new person', op.locator('#ed-truck').count() == 0 and op.locator('#nw-truck').count() == 0)
    check('owner: no errors', not ERRS, ERRS[:3])
    # ---------- 3. the mechanic's app ----------
    doc_set(otok, 'jobs/t2', {'date': TOM, 'time': '13:00', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'client': snap, 'services': ['Inspection multipoints'], 'status': 'planifie', 'createdAt': 6})
    sc = ctx(b, phone=True); sp = page(sc, 'saleh'); login(sp, 'saleh@garage.test', pw['saleh'])
    sp.goto(BASE + '#jour'); sp.wait_for_timeout(800)
    sp.evaluate("(d) => { const A = window.__garageApi; A.S.day = d; A.render(); }", TOM); sp.wait_for_timeout(800)
    ids = sp.evaluate("[...document.querySelectorAll('[data-id]')].map(e => e.dataset.id)")
    check('Saleh\'s app: the route of the truck « Saleh » (his 13 h), not Ali\'s (the job moved to Ali)', 't2' in ids and 't1' not in ids, ids[:10])
    sp.click('.tab[data-t="plus"]'); sp.wait_for_selector('#tiles', timeout=10000)
    tl = sp.evaluate("[...document.querySelectorAll('#tiles .tile b')].map(b => b.textContent)")
    check('…no « Mes disponibilités » for him either', 'Mes disponibilités' not in tl and tl[0] == 'Ma journée', tl)
    check('mechanic: no errors', not ERRS, ERRS[:3])
    # ---------- 7. English ----------
    ec = ctx(b); ec.add_init_script("try { localStorage.setItem('gm.lang', 'en'); } catch(e){}"); ep = page(ec, 'owner en'); ep.set_viewport_size({'width': 1300, 'height': 1000}); login(ep, 'hassan@garage.test', pw['hassan'])
    settings(ep)
    check('English: « Truck name (the mechanic who drives it) », « Saleh\'s route… »', 'Truck name (the mechanic who drives it)' in txt(ep, 'label[for="tk-n-c1"]') and "Saleh's route" in txt(ep, '.tk-row[data-id="c1"]'), (txt(ep, 'label[for="tk-n-c1"]'), txt(ep, '.tk-row[data-id="c1"]')))
    check('English: no errors', not ERRS, ERRS[:3])
    b.close()
summary()
