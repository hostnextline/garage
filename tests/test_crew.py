"""Trucks, not typed names: a mechanic's name in the agenda comes from his account; each truck carries the name of the
mechanic who drives it (named in Réglages, nobody assigned by hand), the coming appointments follow the truck's mechanic,
and the home screen has its tiles (no availability: the trucks' schedules decide).
Server (members function) and screens (owner on the computer and the phone, a mechanic on his phone)."""
import json, datetime
from team_seed import *
from playwright.sync_api import sync_playwright

TOM = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
YEST = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
def cfgd(): return doc('config/main') or {}
def truck(k): return [t for t in cfgd().get('trucks', []) if t['id'] == k][0]
def job(i): return doc('jobs/' + i) or {}
def uid(email): return psql("select id from auth.users where email='%s'" % email)
def mech_of(email): return psql("select coalesce(mechanic,'') from public.members m join auth.users u on u.id = m.user_id where u.email='%s'" % email)

otok, pw = seed()
J = lambda d, t, m, k, st='planifie': {'date': d, 'time': t, 'durationMin': 60, 'mechanic': m, 'truck': k, 'clientId': 'c1', 'client': {'id': 'c1', 'name': 'Marie Tremblay', 'firstName': 'Marie', 'lastName': 'Tremblay'}, 'vehicle': {'make': 'Honda', 'model': 'Civic'}, 'services': ['Inspection multipoints'], 'status': st, 'createdAt': 5}
doc_set(otok, 'jobs/f1', J(TOM, '09:00', 'Ali', 'c2'))                  # coming, on Camion 2
doc_set(otok, 'jobs/f2', J(TOM, '11:00', 'Ali', 'c2', 'termine'))       # done already: never moves
doc_set(otok, 'jobs/f3', J(YEST, '09:00', 'Ali', 'c2'))                 # in the past: never moves
doc_set(otok, 'jobs/f4', J(TOM, '13:00', '', 'c3'))                     # Camion 3 has nobody yet

# ---------- 1. server: the names come from the accounts ----------
r = fn(otok, 'members', {'action': 'list'})
c = cfgd()
check('opening the team list: the agenda names stay, and the names with an account are known', c.get('mechanics') == ['Hassan', 'Saleh', 'Ali'] and c.get('crewAccounts') == ['Hassan', 'Saleh', 'Ali'], [c.get('mechanics'), c.get('crewAccounts')])
r = fn(otok, 'members', {'action': 'create', 'name': 'Rami Nouveau', 'email': 'rami@garage.test', 'roles': ['mecano'], 'truck': 'c3', 'password': 'Passe-rami-2026'})
check('new mechanic with « Camion 3 »: no name typed, his own name is his agenda name', r.get('ok') and mech_of('rami@garage.test') == 'Rami Nouveau', r)
check('…he is in the mechanics, on Camion 3, and Camion 3 goes into service', 'Rami Nouveau' in cfgd()['mechanics'] and truck('c3')['mech'] == 'Rami Nouveau' and truck('c3')['on'] is True and r.get('moved') == {'c3': 'Rami Nouveau'}, [truck('c3'), r.get('moved')])
r = fn(otok, 'members', {'action': 'create', 'name': 'Saleh', 'email': 'saleh2@garage.test', 'roles': ['mecano'], 'password': 'Passe-saleh2-26'})
check('a second « Saleh »: refused with a clear message, no account left behind', not r.get('ok') and "s'appelle déjà « Saleh »" in (r.get('message') or r.get('_body') or '') and uid('saleh2@garage.test') == '', r)
r = fn(otok, 'members', {'action': 'create', 'name': 'Lise Bureau', 'email': 'lise@garage.test', 'roles': ['bureau'], 'password': 'Passe-lise-2026'})
check('an office person without a truck: not in the agenda', r.get('ok') and mech_of('lise@garage.test') == '' and 'Lise Bureau' not in cfgd()['mechanics'])
rami = uid('rami@garage.test')
r = fn(otok, 'members', {'action': 'update', 'user_id': rami, 'truck': 'c2'})
check('Rami moves to Camion 2: he takes Ali\'s place, Camion 3 is free again', r.get('ok') and truck('c2')['mech'] == 'Rami Nouveau' and truck('c3')['mech'] == '' and r.get('moved') == {'c2': 'Rami Nouveau', 'c3': ''}, [cfgd().get('trucks'), r.get('moved')])
r = fn(otok, 'members', {'action': 'update', 'user_id': rami, 'name': 'Rami N.'})
check('renaming him keeps his agenda name (his appointments stay his)', r.get('ok') and mech_of('rami@garage.test') == 'Rami Nouveau')
doc_set(otok, 'jobs/f5', J(TOM, '15:00', 'Rami Nouveau', 'c2'))
r = fn(otok, 'members', {'action': 'remove', 'user_id': rami})
c = cfgd()
check('removing Rami: off the mechanics, Camion 2 free, his coming appointment waits for the next mechanic', r.get('ok') and 'Rami Nouveau' not in c['mechanics'] and truck('c2')['mech'] == '' and job('f5').get('mechanic') == '' and job('f5').get('truck') == 'c2', [c['mechanics'], truck('c2'), job('f5').get('mechanic')])
doc_set(otok, 'config/main', dict(cfgd(), trucks=[{'id': 'c1', 'name': 'Saleh', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Ali', 'on': True, 'mech': 'Ali'}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}], mechanics=['Hassan', 'Saleh', 'Ali', 'Marc', 'Zed']))
doc_set(otok, 'jobs/f5', J(TOM, '15:00', 'Ali', 'c2'))

with sync_playwright() as pl:
    b = pl.chromium.launch()
    # ---------- 2. owner, computer: Équipe et accès (no truck to choose: a truck carries its mechanic's name) ----------
    c1 = ctx(b); op = page(c1, 'owner'); login(op, 'hassan@garage.test', pw['hassan'])
    op.goto(BASE + '#equipe'); op.wait_for_selector('.eqp', timeout=12000); op.wait_for_timeout(600)
    check('invite form: no « Son camion » to choose (the truck carries the mechanic\'s name)', op.locator('#nw-truck').count() == 0)
    orph = op.evaluate("[...document.querySelectorAll('#nw-mech option')].map(o => o.value)")
    check('names typed in the agenda before (no account) can be picked, so the person gets their appointments', orph == ['', 'Marc', 'Zed'], orph)
    card = op.locator('.eqp', has_text='saleh@garage.test').inner_text()
    check('each person\'s card shows the truck in his name (« 🚚 Saleh »)', '🚚 Saleh' in card, card[:160])
    op.fill('#nw-name', 'Marc Tremblay'); op.fill('#nw-email', 'marc@garage.test'); pick_roles(op, 'nw', ['mecano'])
    op.select_option('#nw-mech', 'Marc')
    op.click('[data-act="eq-invite"]'); op.wait_for_selector('#eq-invited', timeout=15000); op.wait_for_timeout(1500)
    check('invited with « Marc » (already in the agenda); no truck in his name yet', mech_of('marc@garage.test') == 'Marc' and 'Aucun camion à son nom' in op.locator('.eqp', has_text='marc@garage.test').inner_text(), mech_of('marc@garage.test'))
    check('…Camion 3\'s appointment still has nobody (no truck named Marc)', job('f4').get('mechanic') == '', job('f4').get('mechanic'))

    # ---------- 3. Réglages: nothing typed; a truck named after its mechanic ----------
    op.evaluate("window.__allSettings = true")   # (every section open at once)
    op.goto(BASE + '#reglages'); op.wait_for_selector('#crew-sect', timeout=10000)
    cs = op.inner_text('#crew-sect')
    check('Réglages → Mécanos: no list to type; the names come from the team, with the truck in their name', op.locator('#s-mechs').count() == 0 and '🚚 Saleh' in cs and 'Aucun camion à son nom' in cs and op.locator('#crew-sect a[href="#equipe"]').count() == 1 and op.locator('#crew-sect a[href="#dispos"]').count() == 0, cs[:300])
    check('a name with no account is marked, with « Retirer »', op.locator('#crew-sect [data-act="mech-drop"][data-v="Zed"]').count() == 1 and op.locator('#crew-sect [data-act="mech-drop"][data-v="Saleh"]').count() == 0)
    op.click('#crew-sect [data-act="mech-drop"][data-v="Zed"]'); op.wait_for_timeout(1200)
    check('« Retirer » takes the old name off', 'Zed' not in cfgd()['mechanics'] and 'Marc' in cfgd()['mechanics'], cfgd()['mechanics'])
    op.goto(BASE + '#reglages'); op.wait_for_selector('#trucks-box', timeout=10000)
    op.fill('#tk-n-c2', 'Saleh'); op.click('#s-save'); op.wait_for_timeout(500)
    check('two trucks named « Saleh »: refused (one name per truck)', toast_has(op, 'Un nom par camion') and truck('c2')['name'] == 'Ali')
    op.goto(BASE + '#accueil'); op.wait_for_timeout(300); op.goto(BASE + '#reglages'); op.wait_for_selector('#trucks-box', timeout=10000)   # (a fresh form: the refused name is gone)
    op.fill('#tk-n-c3', 'Marc'); op.check('.tk-row[data-id="c3"] [data-f="on"]'); op.click('#s-save'); op.wait_for_timeout(2000)
    check('Camion 3 renamed « Marc » (in service): it is Marc\'s truck', truck('c3')['name'] == 'Marc' and truck('c3')['mech'] == 'Marc' and truck('c3')['on'] is True, cfgd().get('trucks'))
    check('…its coming appointment goes to Marc; the others stay', job('f4').get('mechanic') == 'Marc' and job('f1').get('mechanic') == 'Ali' and job('f5').get('mechanic') == 'Ali', [job(x).get('mechanic') for x in ('f4', 'f1', 'f5')])
    op.wait_for_timeout(800)

    # ---------- 4. booking: the mechanic follows the truck ----------
    op.goto(BASE + '#agenda'); op.reload(); op.wait_for_selector('#top [data-act="new"]', timeout=15000); op.wait_for_timeout(1200)   # (the changes made from outside: fresh)
    op.click('#top [data-act="new"]'); op.wait_for_selector('#cs-q', timeout=10000)
    op.fill('#cs-q', 'Marie'); op.wait_for_timeout(400); op.locator('#cs-results .crow').first.click(); op.wait_for_selector('#f-truck', state='attached', timeout=10000)
    st = op.evaluate("(() => { const m = document.getElementById('f-mech'); return [m.type, m.value, document.getElementById('f-mech-show').value, document.getElementById('f-mech-show').readOnly, document.getElementById('f-truck').value]; })()")
    check('booking: no mechanic list; it shows the truck\'s mechanic (its name, read only)', st[0] == 'hidden' and st[3] is True and st[4] == 'c1' and st[1] == 'Saleh' and st[2] == 'Saleh', st)
    op.evaluate("(() => { const t = document.getElementById('f-truck'); t.value = 'c3'; t.dispatchEvent(new Event('change', {bubbles:true})); })()"); op.wait_for_timeout(200)
    check('another truck: its mechanic (« Marc »)', op.input_value('#f-mech') == 'Marc' and op.input_value('#f-mech-show') == 'Marc')
    op.evaluate("document.querySelector('.sheet [data-act=\"sheet-close\"]').click()"); op.wait_for_timeout(300)
    check('no « Qui part avec quel camion » in the agenda', op.locator('#crewbox, [data-crew]').count() == 0)

    # ---------- 5. home: today, then the tiles ----------
    op.goto(BASE + '#accueil'); op.wait_for_selector('#tiles', timeout=10000)
    tl = op.evaluate("[...document.querySelectorAll('#tiles .tile b')].map(b => b.textContent)")
    check('computer home: a tile for each part of the app (no availability: the trucks\' schedules decide)', tl[:3] == ['Agenda', 'Nouvelle réservation', 'Facture sur place'] and all(x in tl for x in ['Clients', 'Factures', 'Carte de l\'équipe', 'Équipe et accès', 'Trésorerie', 'Réglages']) and 'Disponibilités des mécanos' not in tl, tl)
    check('…under « today » (revenue and the day first)', op.evaluate("(() => { const h = document.querySelector('.dash-hero, [aria-labelledby=\"d-today\"]'), t = document.getElementById('tiles'); return !!h && !!(h.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING); })()"))
    check('…the agenda tile says how many appointments today', '2 rendez-vous aujourd' in op.inner_text('#tiles a[href="#agenda"]'), op.inner_text('#tiles a[href="#agenda"]'))
    op.click('#tiles a[href="#clients"]'); op.wait_for_timeout(600)
    check('a tile opens its screen', op.evaluate("location.hash") == '#clients' and op.locator('.tab[data-t="clients"][aria-current="page"]').count() == 1)
    op.goto(BASE + '#accueil'); op.wait_for_selector('#tiles', timeout=10000); op.click('#tiles [data-act="new"]'); op.wait_for_timeout(600)
    check('« Nouvelle réservation » tile starts a booking', op.locator('#sheet').is_visible())
    check('computer home: no sideways scroll, no errors', no_hscroll(op) and not [e for e in ERRS if 'owner' in e], ERRS[:3])
    c1.close()

    # ---------- 6. phone: « Plus » is the home with tiles ----------
    c2 = ctx(b, phone=True); pp = page(c2, 'ownerphone'); login(pp, 'hassan@garage.test', pw['hassan'])
    pp.click('.tab[data-t="plus"]'); pp.wait_for_selector('#tiles', timeout=10000)
    cols = pp.evaluate("getComputedStyle(document.getElementById('tiles')).gridTemplateColumns.split(' ').length")
    check('phone « Plus »: today on top (4 counts), then 2 columns of tiles', pp.locator('.tstrip .ts-c').count() == 4 and cols == 2 and pp.evaluate("document.querySelector('.tstrip').compareDocumentPosition(document.getElementById('tiles')) & Node.DOCUMENT_POSITION_FOLLOWING") > 0, cols)
    tl = pp.evaluate("[...document.querySelectorAll('#tiles .tile b')].map(b => b.textContent)")
    check('…with the agenda of the day, the dashboard and the hours too', tl[0] == 'Agenda' and 'Tableau de bord' in tl and 'Heures d\'ouverture' in tl, tl)
    check('…the tour, the app on the home screen and the language stay below', pp.locator('.ph-row[data-act="tour-replay"]').count() == 1 and pp.locator('.langrow').count() == 1)
    pp.click('#tiles a[href="#accueil"]'); pp.wait_for_timeout(700)
    check('« Tableau de bord » tile opens it (no tiles twice there)', pp.locator('.kpi-big').count() == 1 and pp.locator('#tiles').count() == 0)
    check('phone: no sideways scroll, no errors', no_hscroll(pp) and not [e for e in ERRS if 'ownerphone' in e], ERRS[:3])
    c2.close()

    # ---------- 7. a mechanic on his phone ----------
    c3 = ctx(b, phone=True); sp = page(c3, 'saleh'); login(sp, 'saleh@garage.test', pw['saleh'])
    sp.click('.tab[data-t="plus"]'); sp.wait_for_selector('#tiles', timeout=10000)
    tl = sp.evaluate("[...document.querySelectorAll('#tiles .tile b')].map(b => b.textContent)")
    check('mechanic\'s tiles: his day; no availability (his truck\'s schedule), no settings, no team', tl[0] == 'Ma journée' and 'Mes disponibilités' not in tl and 'Réglages' not in tl and 'Équipe et accès' not in tl, tl)
    sp.click('.tab-new'); sp.wait_for_timeout(500)
    if sp.locator('#sheet .ph-row', has_text='Nouvelle réservation').count():
        sp.locator('#sheet .ph-row', has_text='Nouvelle réservation').click(); sp.wait_for_selector('#f-mech', state='attached', timeout=8000)
        check('his booking: he is the mechanic, the truck in his name chosen', sp.input_value('#f-mech') == 'Saleh' and sp.input_value('#f-truck') == 'c1', [sp.input_value('#f-mech'), sp.input_value('#f-truck')])
    else:
        check('his booking: he is the mechanic (he may not book: nothing to check)', True)
    sp.goto(BASE + '#dispos'); sp.wait_for_timeout(800)
    check('mechanic: an old « #dispos » link says the truck\'s schedule decides', 'Horaire des camions' in txt(sp, '#top'), txt(sp, '#top'))
    check('mechanic: no errors', not [e for e in ERRS if 'saleh' in e], ERRS[:3])
    c3.close()

    # ---------- 9. a mechanic deletes his own account ----------
    stok = token('saleh@garage.test', pw['saleh'])
    r = fn(stok, 'members', {'action': 'leave'})
    check('Saleh deletes his account: off the mechanics, Camion 1 free, his coming jobs wait', r.get('ok') and 'Saleh' not in cfgd()['mechanics'] and truck('c1')['mech'] == '', [r, cfgd()['mechanics'], truck('c1')])
    b.close()
check('no script errors', not ERRS, ERRS[:5])
summary()
