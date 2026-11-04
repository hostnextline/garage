"""Personne n'assigne les mécanos : le matin, chaque mécano choisit dans son app « Je conduis : … » (copie locale de Supabase, vraies écritures) :
1. le serveur (pick_truck) : son choix va dans l'équipe du jour ; les rendez-vous prévus de ce camion ce jour-là deviennent les
   siens ; un autre qui prend le même camion le remplace ; une job commencée ne bouge pas ; pas un jour passé, pas un camion
   inconnu, pas quelqu'un qui n'est pas mécano ; il ne peut toujours pas écrire l'équipe du jour lui-même ;
2. son app : « Quel camion conduis-tu aujourd'hui ? » → il touche un camion → « Tu conduis … » ; « Changer » ;
   « Je ne conduis pas aujourd'hui » ; un autre jour à venir aussi ;
3. le bureau : rien à assigner ; l'agenda dit qui a pris le camion ; la réservation montre ce mécano ;
4. Réglages → Camions : un nom libre, renommer ne change personne ; « Équipe et accès » : pas de camion à choisir ;
5. en anglais."""
import json, os, time, datetime
from team_seed import *
from playwright.sync_api import sync_playwright
T0 = datetime.date.today(); TODAY = T0.isoformat(); TOM = (T0 + datetime.timedelta(days=1)).isoformat(); YEST = (T0 - datetime.timedelta(days=1)).isoformat()
def cfgd(): return doc('config/main') or {}
def truck(k): return [t for t in cfgd().get('trucks', []) if t['id'] == k][0]
def job(i): return doc('jobs/' + i) or {}
def crew(d): return (doc('days/' + d) or {}).get('crew') or {}
def pick(tok, d, k): return http('POST', API + '/rest/v1/rpc/pick_truck', {'p_date': d, 'p_truck': k}, tok)
def wait_true(f, n=25):
    for _ in range(n):
        if f(): return True
        time.sleep(0.4)
    return False
otok, pw = seed()
c = cfgd(); c['hours'] = {str(x): {'open': True, 'start': '08:00', 'end': '20:00'} for x in range(7)}
c['trucks'] = [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': ''}, {'id': 'c2', 'name': 'Camion 2', 'on': True, 'mech': ''}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]
doc_set(otok, 'config/main', c)
snap = {'id': 'c1', 'name': 'Marie Tremblay', 'firstName': 'Marie', 'lastName': 'Tremblay', 'phone': '514 555-0101', 'postal': 'H2J 2L3'}
J = lambda d, t, k, m='', st='planifie': {'date': d, 'time': t, 'durationMin': 60, 'mechanic': m, 'truck': k, 'clientId': 'c1', 'client': snap, 'services': ['Inspection multipoints'], 'status': st, 'createdAt': 5}
doc_set(otok, 'jobs/j1', J(TODAY, '14:00', 'c1'))                 # today, truck 1, nobody yet
doc_set(otok, 'jobs/j2', J(TODAY, '10:00', 'c2'))                 # today, truck 2, nobody yet
doc_set(otok, 'jobs/r1', J(TODAY, '08:00', 'c1', 'Ali', 'route')) # today, truck 1, Ali already on his way: never moves
doc_set(otok, 'jobs/t1', J(TOM, '09:00', 'c1'))                   # tomorrow, truck 1
stok = token('saleh@garage.test', pw['saleh']); atok = token('ali@garage.test', pw['ali']); ltok = token('lina@garage.test', pw['lina'])

# ---------- 1. the server ----------
r = pick(stok, TODAY, 'c1')
check('Saleh picks Camion 1 today: the day\'s crew says so, the planned job of that truck is his', isinstance(r, dict) and r.get('ok') and crew(TODAY) == {'c1': 'Saleh'} and job('j1').get('mechanic') == 'Saleh' and r.get('mine') == 1, (r, crew(TODAY), job('j1').get('mechanic')))
check('…a job already started in that truck does not move (Ali, on his way), tomorrow\'s job neither', job('r1').get('mechanic') == 'Ali' and job('t1').get('mechanic') == '', (job('r1').get('mechanic'), job('t1').get('mechanic')))
rd = http('GET', API + '/rest/v1/docs?select=path&path=eq.jobs/j1', token=stok)
check('…and he can read it now, through the rules', isinstance(rd, list) and len(rd) == 1, rd)
r = pick(stok, TODAY, 'c2')
check('Saleh changes to Camion 2: Camion 2\'s job is his, Camion 1\'s goes back to nobody', crew(TODAY) == {'c2': 'Saleh'} and job('j2').get('mechanic') == 'Saleh' and job('j1').get('mechanic') == '', (crew(TODAY), job('j1').get('mechanic'), job('j2').get('mechanic')))
r = pick(atok, TODAY, 'c2')
check('Ali picks Camion 2 too: he replaces Saleh there (the job is Ali\'s), Saleh has no truck today', crew(TODAY) == {'c2': 'Ali'} and job('j2').get('mechanic') == 'Ali', (crew(TODAY), job('j2').get('mechanic')))
r = pick(atok, TODAY, '')
check('« Je ne conduis pas » : Ali leaves, his planned job goes back to nobody', crew(TODAY) == {} and job('j2').get('mechanic') == '' and job('r1').get('mechanic') == 'Ali', (crew(TODAY), job('j2').get('mechanic')))
r = pick(stok, YEST, 'c1')
check('a day already past: refused', isinstance(r, dict) and r.get('_status', 200) >= 400 and 'past_day' in json.dumps(r), r)
r = pick(stok, TODAY, 'c9')
check('a truck that does not exist: refused', isinstance(r, dict) and r.get('_status', 200) >= 400 and 'no_truck' in json.dumps(r), r)
r = pick(ltok, TODAY, 'c1')
check('the office (not a mechanic): refused', isinstance(r, dict) and r.get('_status', 200) >= 400 and 'not_mechanic' in json.dumps(r), r)
r = http('POST', API + '/rest/v1/rpc/pick_truck', {'p_date': TODAY, 'p_truck': 'c1'})
check('without signing in: refused', isinstance(r, dict) and r.get('_status', 200) >= 400, r)
r = doc_set(stok, 'days/' + TODAY, {'date': TODAY, 'crew': {'c1': 'Saleh', 'c2': 'Saleh'}})
check('a mechanic still cannot write the day\'s crew himself', isinstance(r, dict) and r.get('_status', 200) >= 400 and crew(TODAY) == {}, r)

with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- 2. his app ----------
    sc = ctx(b, phone=True); sp = page(sc, 'saleh'); login(sp, 'saleh@garage.test', pw['saleh'])
    sp.goto(BASE + '#jour'); sp.wait_for_selector('#pick', timeout=12000); sp.wait_for_timeout(500)
    check('his day: « Quel camion conduis-tu aujourd\'hui ? » with the trucks running today (not the closed one)', 'Quel camion conduis-tu aujourd' in txt(sp, '#pick') and sp.evaluate("[...document.querySelectorAll('#pick [data-act=\"pick-truck\"]')].map(b => b.dataset.v)") == ['c1', 'c2'], txt(sp, '#pick'))
    sp.screenshot(path=os.path.join(SC, 'pick_phone.png'))
    sp.click('#pick [data-act="pick-truck"][data-v="c1"]')
    check('he touches « Camion 1 »: « Tu conduis Camion 1 aujourd\'hui : 1 rendez-vous est à toi »', toast_has(sp, 'Tu conduis Camion 1 aujourd') and wait_true(lambda: crew(TODAY) == {'c1': 'Saleh'} and job('j1').get('mechanic') == 'Saleh'), (txt(sp, '#toast'), crew(TODAY)))
    check('…his day now shows « 🚚 Tu conduis Camion 1 aujourd\'hui » and Marie\'s job', wait_for(sp, "!!document.querySelector('.pick-on') && [...document.querySelectorAll('[data-id]')].some(e => e.dataset.id === 'j1')", 8000) and 'Tu conduis Camion 1' in txt(sp, '.pick-on'), txt(sp, '#main')[:200])
    sp.click('.pick-on [data-act="pick-change"]'); sp.wait_for_timeout(300)
    check('« Changer » : the trucks again, with « Je ne conduis pas aujourd\'hui » and « Garder Camion 1 »', sp.locator('#pick [data-act="pick-truck"][data-v=""]').count() == 1 and 'Garder Camion 1' in txt(sp, '#pick'))
    sp.click('#pick [data-act="pick-truck"][data-v=""]')
    check('« Je ne conduis pas aujourd\'hui » : nothing is his today any more', toast_has(sp, 'Tu ne conduis pas aujourd') and wait_true(lambda: crew(TODAY) == {} and job('j1').get('mechanic') == ''), crew(TODAY))
    sp.evaluate("(d) => { const A = window.__garageApi; A.S.day = d; A.render(); }", TOM); sp.wait_for_timeout(600)
    check('tomorrow: « Quel camion conduis-tu » for that day too', 'Quel camion conduis-tu' in txt(sp, '#pick') and 'aujourd' not in txt(sp, '#pick h3'), txt(sp, '#pick h3'))
    sp.click('#pick [data-act="pick-truck"][data-v="c1"]')
    check('…he picks Camion 1 tomorrow: tomorrow\'s job is his', wait_true(lambda: crew(TOM) == {'c1': 'Saleh'} and job('t1').get('mechanic') == 'Saleh'), (crew(TOM), job('t1').get('mechanic')))
    check('phone: no sideways scroll, no errors', no_hscroll(sp) and not ERRS, ERRS[:3])
    pick(stok, TODAY, 'c1')
    # ---------- 3. the office ----------
    lc = ctx(b); lp = page(lc, 'lina'); lp.set_viewport_size({'width': 1300, 'height': 1000}); login(lp, 'lina@garage.test', pw['lina'])
    lp.goto(BASE + '#agenda'); lp.wait_for_timeout(600)
    lp.evaluate("(d) => { const A = window.__garageApi, S = A.S; S.day = d; S.view = 'grid'; S.mech = ''; S.screen = null; A.render(); }", TODAY); lp.wait_for_timeout(800)
    h1 = txt(lp, '.colh[data-truck="c1"]'); h2 = txt(lp, '.colh[data-truck="c2"]')
    check('office agenda: « Camion 1 » says Saleh (he picked it), « Camion 2 » nobody yet; nothing to assign', 'Saleh' in h1 and 'Mécano à choisir' not in h2 and lp.locator('#crewbox, [data-crew]').count() == 0 and lp.locator('#pick').count() == 0, (h1, h2))
    lp.click('.col[data-col="c1"] .slot[data-t="16:00"]'); lp.wait_for_selector('#cs-q', timeout=8000)
    lp.fill('#cs-q', 'Marie'); lp.wait_for_timeout(400); lp.locator('#cs-results .crow').first.click(); lp.wait_for_selector('#f-truck', state='attached', timeout=8000)
    check('booking in Camion 1 today: its mechanic is Saleh (read only)', lp.input_value('#f-truck') == 'c1' and lp.input_value('#f-mech') == 'Saleh' and lp.input_value('#f-mech-show') == 'Saleh', [lp.input_value('#f-truck'), lp.input_value('#f-mech')])
    lp.evaluate("(() => { const t = document.getElementById('f-truck'); t.value = 'c2'; t.dispatchEvent(new Event('change', {bubbles:true})); })()"); lp.wait_for_timeout(200)
    check('…Camion 2: nobody yet (« Le mécano choisit son camion le matin »)', lp.input_value('#f-mech') == '' and 'choisit son camion' in (lp.get_attribute('#f-mech-show', 'placeholder') or ''), lp.input_value('#f-mech'))
    lp.evaluate("document.querySelector('.sheet [data-act=\"sheet-close\"]').click()"); lp.wait_for_timeout(300)
    check('office: no errors', not ERRS, ERRS[:3])
    # ---------- 4. owner: Réglages, Équipe ----------
    oc = ctx(b); op = page(oc, 'owner'); op.set_viewport_size({'width': 1300, 'height': 1000}); login(op, 'hassan@garage.test', pw['hassan'])
    op.evaluate("window.__allSettings = true"); op.goto(BASE + '#reglages'); op.wait_for_selector('#trucks-box', timeout=10000); op.wait_for_timeout(300)
    check('Réglages → Camions: a free name (« Nom »), no mechanic anywhere', txt(op, 'label[for="tk-n-c1"]') == 'Nom' and op.locator('#trucks-box [data-f="mech"], .tk-who, #tk-mechs').count() == 0 and 'Personne n\'est assigné' in txt(op, '#main'))
    op.fill('#tk-n-c1', 'Le gros'); op.click('#s-save')
    check('renamed « Le gros »: saved, and nobody\'s appointments change (Saleh keeps today\'s job)', wait_true(lambda: truck('c1').get('name') == 'Le gros') and job('j1').get('mechanic') == 'Saleh' and truck('c1').get('mech') == '', (truck('c1'), job('j1').get('mechanic')))
    op.goto(BASE + '#equipe'); op.wait_for_selector('.eqp', timeout=12000); op.wait_for_timeout(600)
    card = op.locator('.eqp', has_text='saleh@garage.test').inner_text()
    check('« Équipe et accès »: no truck to choose; Saleh\'s card says the truck he picked today', op.locator('#nw-truck, #ed-truck').count() == 0 and '🚚 Le gros aujourd' in card, card[:200])
    check('owner: no errors', not ERRS, ERRS[:3])
    # ---------- 5. English ----------
    pick(stok, TODAY, '')
    ec = ctx(b, phone=True); ec.add_init_script("try { localStorage.setItem('gm.lang', 'en'); } catch(e){}"); ep = page(ec, 'saleh en'); login(ep, 'saleh@garage.test', pw['saleh'])
    ep.goto(BASE + '#jour'); ep.wait_for_selector('#pick', timeout=12000); ep.wait_for_timeout(600)
    check('English: « Which truck are you driving today? »', 'Which truck are you driving today?' in txt(ep, '#pick') and 'conduis' not in txt(ep, '#pick'), txt(ep, '#pick'))
    ep.click('#pick [data-act="pick-truck"][data-v="c2"]')
    check('English: « You\'re driving Camion 2 today »', toast_has(ep, "You're driving") and wait_true(lambda: crew(TODAY) == {'c2': 'Saleh'}), txt(ep, '#toast'))
    check('English: no errors', not ERRS, ERRS[:3])
    b.close()
pick(stok, TODAY, ''); pick(stok, TOM, '')
summary()
